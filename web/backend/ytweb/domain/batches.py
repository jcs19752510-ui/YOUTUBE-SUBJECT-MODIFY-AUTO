"""배치: 초안+사전 점검, 실행 확정, 취소, 워커 틱, 항목 1건 반영(WEB_DESIGN §4-3,4).

안전 규칙 요약
- 하루 반영 상한(daily_apply_cap)과 배치당 최대 50건 두 겹. 상한을 넘는 분량은 다음 날 이후로 예약한다.
- 워커 틱은 `scheduled_date <= 오늘(KST)` 인 pending 항목을 "오늘 남은 상한" 안에서만, 쿼터 한도 안에서만 처리한다.
  PC 가 꺼져 있던 동안 놓친 예약도 오늘의 상한을 공유하므로 몰아서 실행되지 않는다.
- 항목은 compare-and-set(pending→running)으로 가져가 중복 처리가 불가능하고, 반영 직전 planned 기록(영상당 1개 고유 인덱스)으로 이중 반영을 막는다.
- 승인은 사람이 실행을 확정한 시각(batch.executed_at) 기준으로 유효해야 한다. 여러 날에 걸친 배치가 24시간 TTL 때문에 둘째 날부터 전부 건너뛰는 것을 막되,
  승인이 1회용·변조 탐지·계획 해시(영상 변경 시 무효)에 묶인 점은 그대로다.

데모 게이트 ↔ live_guard 14단계 대응은 docs/harness/units/web-WU-BE-B-note.md 참고.
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from youtube_title.errors import YtError
from youtube_title.updater import build_update_body, validate_new_title

from ytweb.core import audit, jobs
from ytweb.core.clock import kst_today
from ytweb.core.errors import ProblemError
from ytweb.core.settings_store import effective_daily_cap
from ytweb.db.models import Batch, BatchItem, Change, Job, Suggestion, Video
from ytweb.domain.common import MAX_BATCH_ITEMS, Env, StepFailure, clamp_page, default_env, lock_rows, single_line
from ytweb.domain.exclusions import exclusion_reasons
from ytweb.domain.notices import DISCLAIMER
from ytweb.domain.limits_quota import (
    applied_today, check_video_limits, mark_call, quota_state, release_unused, reserve_calls, units_per_apply,
)
from ytweb.domain.suggestions import ApprovalInvalid, check_approval, expire_stale_approvals, is_blocking, plan_hash_for, release_after_item
from ytweb.youtube.base import GatewayError, YouTubeGateway
from ytweb.youtube.mock import MockYouTubeGateway
from ytweb.domain import live_gateway

log = logging.getLogger("ytweb.batches")

WORKER = "worker"
STALE_RUNNING = timedelta(minutes=10)
_APPLY_LOCK_KEY = 7_340_003  # 한도 검사~planned 기록~커밋을 워커 사이에 한 줄로 세우는 PostgreSQL 트랜잭션 락
VERIFY_PRESERVED_FIELDS = ("description", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage")  # live_guard.VERIFY_PRESERVED_FIELDS 와 같다
_MISSING = object()
GatewayFactory = Callable[[Session, datetime], YouTubeGateway]


def mock_gateway_factory(session: Session, now: datetime) -> YouTubeGateway:
    """이름은 유지하지만 live 쓰기 조건(M3)이 모두 맞으면 실제 게이트웨이를 돌려준다. 기본은 모의."""
    from ytweb.domain.live_gateway import select_gateway
    return select_gateway(session, now)


# ───────────── 적격성·일정 ─────────────

def _eligibility(session: Session, sug: Suggestion | None, video: Video | None, env: Env, now: datetime, cap: int) -> tuple[str, str] | None:
    """배치에 담을 수 있는지(사전 점검·실행 확정 공통). 막히면 (코드, 한국어 사유). 하루 상한은 일정으로 풀므로 여기서 보지 않는다."""
    if sug is None:
        return "suggestion_not_found", "제안을 찾을 수 없습니다."
    if sug.status != "approved":
        return "not_approved", f"승인된 제안이 아닙니다(현재 상태: {sug.status})."
    if video is None:
        return "video_not_found", "영상을 찾을 수 없습니다."
    try:
        check_approval(sug, video, env, now)
    except ApprovalInvalid as exc:
        return exc.code, exc.message
    reasons = exclusion_reasons(video, env.policy)
    if reasons:
        return "video_excluded", "제외 대상 영상입니다: " + ", ".join(reasons)
    if is_blocking(sug):
        return "suggestion_blocked", "검증에서 차단된 제안입니다."
    not_allowed = live_gateway.not_allowed_reason(video.video_id, env.secrets_dir)  # 실제 모드: 허용 영상만(쿼터·기록 전에 먼저 막는다)
    if not_allowed:
        return "live_not_allowed", not_allowed
    report = check_video_limits(session, video.video_id, now, env.limits_policy, cap)
    failures = [c for c in report.failures if c.code != "DAILY"]
    if failures:
        return "limit_" + failures[0].code.lower(), " / ".join(c.message for c in failures)
    return None


def _active_holder(session: Session, suggestion_id: int) -> tuple[int, str] | None:
    """이 제안을 지금 담고 있는 배치(번호, 상태). 초안 배치도 제안을 붙잡으므로(부분 고유 인덱스) 사유에 번호를 알려 버릴 수 있게 한다."""
    return session.execute(
        select(Batch.id, Batch.status).join(BatchItem, BatchItem.batch_id == Batch.id)
        .where(BatchItem.suggestion_id == suggestion_id, BatchItem.status.in_(("pending", "running"))).limit(1)
    ).first()


def _holder_reason(batch_id: int, status: str) -> str:
    if status == "draft":
        return f"초안 배치 #{batch_id}에 이미 담겨 있습니다. 그 초안을 버리거나 실행한 뒤 다시 담을 수 있습니다."
    return f"배치 #{batch_id}(진행 중)에 이미 담겨 있습니다."


def assign_dates(session: Session, n: int, now: datetime, cap: int, *, exclude_batch_id: int | None = None) -> list[date]:
    """n건에 반영 예정일을 배정한다. 오늘은 (오늘 이미 반영한 수 + 오늘까지 밀린 예약 수)를 뺀 만큼만, 이후 날짜는 그날 예약 수를 뺀 만큼."""
    today = kst_today(now)
    active = (Batch.status.in_(("queued", "running")), BatchItem.status == "pending")
    if exclude_batch_id is not None:
        active += (BatchItem.batch_id != exclude_batch_id,)
    rows = session.execute(
        select(BatchItem.scheduled_date, func.count()).join(Batch, Batch.id == BatchItem.batch_id).where(*active, BatchItem.scheduled_date.is_not(None)).group_by(BatchItem.scheduled_date)
    ).all()
    overdue = sum(c for d, c in rows if d <= today)
    future = {d: c for d, c in rows if d > today}
    dates: list[date] = []
    offset = 0
    while len(dates) < n:
        if offset > 400:
            raise ProblemError(409, "schedule_overflow", "예약할 수 있는 날짜 범위를 넘었습니다.", hint="배치 크기를 줄이거나 하루 반영 상한을 늘리세요.")
        day = today + timedelta(days=offset)
        used = (applied_today(session, now) + overdue) if offset == 0 else future.get(day, 0)
        dates.extend([day] * min(max(0, cap - used), n - len(dates)))
        offset += 1
    return dates


def _schedule_summary(dates: list[date]) -> list[dict]:
    out: dict[str, int] = {}
    for d in dates:
        out[d.isoformat()] = out.get(d.isoformat(), 0) + 1
    return [{"date": k, "count": v} for k, v in out.items()]


# ───────────── 초안·사전 점검 ─────────────

def create_draft(session: Session, suggestion_ids: list[int], note: str | None, *, now: datetime, env: Env, actor: str = "web") -> tuple[Batch, dict]:
    if not suggestion_ids:
        raise ProblemError(422, "batch_empty", "배치에 담을 제안을 선택하세요.", hint="승인된 제안을 1개 이상 선택하세요.")
    if len(suggestion_ids) > MAX_BATCH_ITEMS:
        raise ProblemError(422, "batch_too_large", f"배치는 최대 {MAX_BATCH_ITEMS}건까지 만들 수 있습니다(선택 {len(suggestion_ids)}건).", hint="나눠서 여러 배치로 만드세요.")
    dups = sorted({i for i in suggestion_ids if suggestion_ids.count(i) > 1})
    if dups:
        raise ProblemError(422, "duplicate_suggestion", "같은 제안이 두 번 선택되었습니다.", detail=", ".join(map(str, dups)), hint="중복 선택을 풀고 다시 시도하세요.")
    expire_stale_approvals(session, now)
    cap = effective_daily_cap(session, env.policy)
    eligible: list[tuple[Suggestion, Video]] = []
    blocked: list[dict] = []
    seen_videos: set[str] = set()
    for sid in suggestion_ids:
        sug = session.get(Suggestion, sid)
        video = session.get(Video, sug.video_id) if sug is not None else None
        problem = _eligibility(session, sug, video, env, now, cap)
        holder = _active_holder(session, sid) if problem is None else None
        if holder is not None:
            problem = ("already_in_batch", _holder_reason(*holder))
            blocked.append({"suggestion_id": sid, "reason": problem[1], "code": problem[0], "batch_id": holder[0]})
            continue
        if problem is None and video.video_id in seen_videos:
            problem = ("duplicate_video", "같은 영상의 다른 제안이 이미 이 배치에 있습니다(영상당 한 번에 한 제목만).")
        if problem is not None:
            blocked.append({"suggestion_id": sid, "reason": problem[1], "code": problem[0]})
            continue
        seen_videos.add(video.video_id)
        eligible.append((sug, video))
    if not eligible:
        raise ProblemError(422, "batch_empty", "배치에 담을 수 있는 제안이 없습니다.", detail="; ".join(f"#{b['suggestion_id']}: {b['reason']}" for b in blocked[:5]), hint="승인 상태·제외 사유·교체 한도를 확인하세요.")
    batch = Batch(status="draft", note=single_line(note, 200) if note else None, created_at=now, updated_at=now)
    session.add(batch)
    session.flush()
    for seq, (sug, video) in enumerate(eligible, 1):
        batch.items.append(BatchItem(suggestion_id=sug.id, video_id=video.video_id, seq=seq, status="pending", updated_at=now))
    try:
        session.flush()
    except IntegrityError:
        raise ProblemError(409, "already_in_batch", "선택한 제안 중 일부가 방금 다른 배치에 담겼습니다.", hint="목록을 새로고침해 다시 선택하세요.") from None
    precheck = build_precheck(session, batch, eligible, blocked, now=now, env=env, cap=cap)
    batch.precheck = precheck
    session.flush()
    audit.record(session, actor=actor, action="batch.create", target_type="batch", target_id=str(batch.id), detail={"items": len(eligible), "blocked": len(blocked)}, now=now)
    return batch, precheck


def build_precheck(session: Session, batch: Batch, eligible: list[tuple[Suggestion, Video]], blocked: list[dict], *, now: datetime, env: Env, cap: int) -> dict:
    n = len(eligible)
    dates = assign_dates(session, n, now, cap, exclude_batch_id=batch.id)
    qs = quota_state(session, now, env.policy)
    per = units_per_apply(env.policy)
    today = kst_today(now)
    today_count = sum(1 for d in dates if d == today)
    warnings: list[str] = []
    done_today = applied_today(session, now)
    if done_today >= cap:
        warnings.append(f"오늘 반영 상한({cap}건)에 이미 도달해 모두 내일 이후로 예약됩니다.")
    elif len(set(dates)) > 1:
        warnings.append(f"{n}건을 {len(set(dates))}일에 나눠 반영합니다(하루 최대 {cap}건, 오늘 {done_today}건 반영됨).")
    if today_count * per > qs.remaining:
        warnings.append(f"오늘 분량({today_count}건, 약 {today_count * per}단위)이 남은 쿼터({qs.remaining}단위)를 넘어 일부는 쿼터가 초기화된 뒤 처리됩니다.")
    elif qs.warning:
        warnings.append(f"오늘 쿼터 사용량이 경고 비율({int(env.policy.warn_ratio * 100)}%) 이상입니다.")
    warn_count = sum(1 for s, _ in eligible if s.validation_result == "warn")
    if warn_count:
        warnings.append(f"경고 판정 제안이 {warn_count}건 포함되어 있습니다. 승인 전에 사유를 확인했는지 다시 보세요.")
    warnings.append("Studio에서 해당 영상의 제목 A/B 테스트가 진행 중이 아닌지 확인하세요.")
    live = live_gateway.live_mode(env.secrets_dir)
    if live:
        warnings.insert(0, f"실제 모드입니다. 실행하면 허용된 영상 {n}개의 제목이 실제 유튜브에서 바뀝니다. 확인 문구도 \"{live_gateway.confirm_text(n, True)}\" 로 다릅니다.")
    return {
        "item_count": n,
        "estimated_units": n * per,
        "daily_cap": cap,
        "quota_remaining_units": qs.remaining,
        "schedule": _schedule_summary(dates),
        "warnings": warnings,
        "blocked": blocked,
        "confirm_text": live_gateway.confirm_text(n, live),
        "notice": DISCLAIMER,
    }


# ───────────── 조회 ─────────────

def get_batch(session: Session, batch_id: int, *, lock: bool = False) -> Batch:
    stmt = select(Batch).where(Batch.id == batch_id)
    batch = session.execute(lock_rows(stmt, session) if lock else stmt).scalar_one_or_none()
    if batch is None:
        raise ProblemError(404, "batch_not_found", "배치를 찾을 수 없습니다.", hint="배치 목록을 새로고침하세요.")
    return batch


def list_batches(session: Session, *, page: int, page_size: int) -> tuple[list[Batch], int]:
    page, page_size = clamp_page(page, page_size)
    total = int(session.execute(select(func.count()).select_from(Batch)).scalar_one())
    rows = session.execute(select(Batch).order_by(Batch.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return list(rows), total


def item_counts(batch: Batch) -> dict[str, int]:
    counts = {k: 0 for k in ("pending", "running", "success", "failed", "skipped", "cancelled")}
    for it in batch.items:
        counts[it.status] += 1
    return counts


def refresh_batch_status(batch: Batch, now: datetime) -> None:
    if batch.status in ("cancelled", "draft"):
        return
    c = item_counts(batch)
    if c["pending"] == 0 and c["running"] == 0:
        new = "done"
    elif c["running"] > 0:
        new = "running"   # 실제로 처리 중인 항목이 있을 때만(미래 예약만 남았으면 queued 유지 — 프런트 폴링 기준)
    else:
        new = "queued"
    if new != batch.status:
        batch.status, batch.updated_at = new, now


# ───────────── 실행 확정·취소 ─────────────

def execute_batch(session: Session, batch_id: int, confirm_text: str, *, now: datetime, env: Env, actor: str = "web") -> tuple[Batch, Job]:
    batch = get_batch(session, batch_id, lock=True)
    if batch.status != "draft":
        raise ProblemError(409, "batch_not_draft", f"이미 실행했거나 취소된 배치입니다(상태: {batch.status}).", hint="새 배치를 만들어 실행하세요.")
    items = [it for it in batch.items if it.status == "pending"]
    expected = live_gateway.confirm_text(len(items), live_gateway.live_mode(env.secrets_dir))
    if confirm_text != expected:
        raise ProblemError(422, "confirm_text_mismatch", "확인 문구가 일치하지 않습니다.", detail=f"정확히 '{expected}' 라고 입력해야 합니다.", hint="사전 점검 화면에 표시된 확인 문구를 그대로 입력하세요.")
    expire_stale_approvals(session, now)
    cap = effective_daily_cap(session, env.policy)
    stale: list[str] = []
    pairs: list[tuple[BatchItem, Suggestion, Video]] = []
    for it in items:
        sug = session.get(Suggestion, it.suggestion_id)
        video = session.get(Video, it.video_id)
        problem = _eligibility(session, sug, video, env, now, cap)
        if problem is not None:
            stale.append(f"#{it.suggestion_id}: {problem[1]}")
        else:
            pairs.append((it, sug, video))
    if stale:
        raise ProblemError(409, "precheck_stale", "사전 점검 이후 상태가 바뀐 항목이 있어 실행하지 않았습니다.", detail="; ".join(stale[:5]), hint="이 배치를 취소하고 새로 사전 점검을 하세요.")
    dates = assign_dates(session, len(items), now, cap, exclude_batch_id=batch.id)
    for (it, sug, _), day in zip(pairs, dates):
        it.scheduled_date, it.updated_at = day, now
        sug.status, sug.updated_at = "queued", now
    batch.status, batch.executed_at, batch.updated_at = "queued", now, now
    today_count = sum(1 for d in dates if d == kst_today(now))
    job = jobs.enqueue(session, type="batch.execute", payload={"batch_id": batch.id}, total=today_count, now=now)
    session.flush()
    audit.record(session, actor=actor, action="batch.execute", target_type="batch", target_id=str(batch.id), detail={"items": len(items), "job_id": job.id, "schedule": _schedule_summary(dates)}, now=now)
    return batch, job


def cancel_batch(session: Session, batch_id: int, *, now: datetime, env: Env, actor: str = "web") -> Batch:
    batch = get_batch(session, batch_id, lock=True)
    if batch.status in ("cancelled", "done"):
        raise ProblemError(409, "batch_not_cancellable", f"이미 끝났거나 취소된 배치입니다(상태: {batch.status}).", hint="진행 중인 배치만 중지할 수 있습니다.")
    was_draft = batch.status == "draft"
    cancelled = 0
    for it in batch.items:
        if it.status != "pending":
            continue  # 진행 중(running) 항목은 완료까지 둔다
        it.status, it.skip_reason, it.updated_at = "cancelled", ("[cancelled] 사용자가 초안을 버렸습니다." if was_draft else "[cancelled] 사용자가 배치를 중지했습니다."), now
        sug = session.get(Suggestion, it.suggestion_id)
        if sug is not None:
            release_after_item(sug, session.get(Video, it.video_id), env, now, batch.executed_at or now)
        cancelled += 1
    batch.status, batch.updated_at = "cancelled", now
    session.flush()
    audit.record(session, actor=actor, action="batch.cancel", target_type="batch", target_id=str(batch.id), detail={"cancelled_items": cancelled, "was_draft": was_draft}, now=now)
    return batch


# ───────────── 항목 1건 반영 ─────────────

@dataclass(frozen=True)
class ItemOutcome:
    item_id: int
    status: str            # success | failed | skipped | not_pending | deferred(오늘 몫 소진, 다음 날로 이월)
    code: str | None
    change_id: int | None


@dataclass
class _State:
    reserved: list[int]
    change: Change | None = None
    keep_planned: bool = False


def verify_snippet(before: dict, after: dict | None, expected_title: str) -> dict:
    """제목 반영과 설명·태그·카테고리·언어 보존을 비교한다(live_guard.compare_after 와 같은 규칙, SEC-010)."""
    if after is None:
        return {"ok": False, "checked": False, "reason": "재조회에 실패해 제목 반영과 보존을 확인하지 못함"}
    preserved = {k: before.get(k, _MISSING) == after.get(k, _MISSING) for k in VERIFY_PRESERVED_FIELDS}
    other = sorted(k for k in (set(before) | set(after)) if k not in VERIFY_PRESERVED_FIELDS and k not in ("title", "localized") and before.get(k, _MISSING) != after.get(k, _MISSING))
    title_ok = after.get("title") == expected_title
    return {"ok": bool(title_ok and all(preserved.values())), "checked": True, "title_ok": title_ok, "preserved": preserved, "other_changed": other}


def _check_body(body: dict, video_id: str, fresh: dict, new_title: str) -> None:
    sent = body.get("snippet") if isinstance(body, dict) else None
    if not isinstance(sent, dict) or set(body) != {"id", "snippet"} or body["id"] != video_id or sent.get("title") != new_title:
        raise StepFailure("body_invalid", "요청 본문의 구조나 제목이 올바르지 않아 중단했습니다.", kind="failed")
    if {k: v for k, v in sent.items() if k != "title"} != {k: v for k, v in fresh.items() if k != "title"}:
        raise StepFailure("body_invalid", "요청 본문이 재조회한 영상 정보를 전부 보존하지 않아 중단했습니다.", kind="failed")


def _claim(session: Session, item_id: int, now: datetime) -> bool:
    res = session.execute(update(BatchItem).where(BatchItem.id == item_id, BatchItem.status == "pending").values(status="running", updated_at=now))
    session.commit()  # 선점을 바로 확정해 다른 처리자가 같은 항목을 가져가지 못하게 한다
    return res.rowcount == 1


def apply_one(session: Session, item_id: int, *, now: datetime, env: Env, gateway: YouTubeGateway, actor: str = WORKER, job_id: str | None = None) -> ItemOutcome:
    """배치 항목 1건을 반영한다. 어느 단계에서 실패하든 이 항목만 failed/skipped 로 끝나고 이중 반영은 일어나지 않는다."""
    if not _claim(session, item_id, now):
        item = session.get(BatchItem, item_id)
        return ItemOutcome(item_id, "not_pending", "not_pending", item.change_id if item else None)
    item = session.get(BatchItem, item_id)
    state = _State([])
    try:
        return _apply(session, item, now, env, gateway, actor, job_id, state)
    except StepFailure as sf:
        return _finish_failure(session, item_id, sf, state, now, env, actor)
    except Exception as exc:  # noqa: BLE001 - 예상 밖 오류도 이 항목만 failed 로 닫고 틱은 계속한다(로그에는 남긴다)
        log.exception("batch item %s failed unexpectedly", item_id)
        planned_id = state.change.id if state.change is not None else None
        session.rollback()
        state = _State([], keep_planned=True) if planned_id else _State([])
        state.change = session.get(Change, planned_id) if planned_id else None
        return _finish_failure(session, item_id, StepFailure("internal_error", f"예상하지 못한 오류({type(exc).__name__})로 중단했습니다.", kind="failed"), state, now, env, actor)


def _apply(session: Session, item: BatchItem, now: datetime, env: Env, gateway: YouTubeGateway, actor: str, job_id: str | None, state: _State) -> ItemOutcome:
    policy = env.policy
    batch = session.get(Batch, item.batch_id)
    sug = session.get(Suggestion, item.suggestion_id)
    video = session.get(Video, item.video_id)
    if batch is None or batch.status not in ("queued", "running"):
        raise StepFailure("batch_not_active", "실행 확정된 배치가 아니어서 반영하지 않았습니다.")
    if sug is None or video is None:
        raise StepFailure("suggestion_missing", "제안 또는 영상 정보를 찾을 수 없습니다.")
    ref_time = batch.executed_at or now
    # 1) 승인 유효·해시 일치
    try:
        check_approval(sug, video, env, ref_time)
    except ApprovalInvalid as exc:
        raise StepFailure(exc.code, exc.message) from None
    if session.get_bind().dialect.name == "postgresql":  # 같은 하루 상한·같은 영상을 두 워커가 동시에 통과하지 못하게 한다(커밋 때 풀림)
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _APPLY_LOCK_KEY})
    # 2) 제안 상태·제목 규격·제외 사유·진행 중 변경
    if sug.status != "queued":
        raise StepFailure("suggestion_state", f"제안이 대기열 상태가 아닙니다(현재 {sug.status}).")
    if is_blocking(sug):
        raise StepFailure("suggestion_blocked", "검증에서 차단된 제안은 반영하지 않습니다.")
    try:
        validate_new_title(sug.title, policy)
    except YtError as exc:
        raise StepFailure("title_invalid", exc.message) from None
    if sug.title == video.title:
        raise StepFailure("same_as_current", "새 제목이 현재 제목과 같아 바꿀 내용이 없습니다.")
    reasons = exclusion_reasons(video, policy)
    if reasons:
        raise StepFailure("video_excluded", "제외 대상 영상입니다: " + ", ".join(reasons))
    not_allowed = live_gateway.not_allowed_reason(video.video_id, env.secrets_dir)  # 방어: 기록·쿼터 전에 한 번 더
    if not_allowed:
        raise StepFailure("live_not_allowed", not_allowed)
    stale = session.execute(select(Change.id).where(Change.video_id == video.video_id, Change.result == "planned").limit(1)).first()
    if stale is not None:
        raise StepFailure("pending_change_exists", f"이 영상에 결과가 확정되지 않은 변경 기록(#{stale[0]})이 있어 중단했습니다.")
    # 3) 한도
    cap = effective_daily_cap(session, policy)
    report = check_video_limits(session, video.video_id, now, env.limits_policy, cap)
    if not report.passed:
        if all(c.code == "DAILY" for c in report.failures):
            # 오늘 몫만 찬 것이라 건너뛰지 않고 다음 날로 이월한다(W-008: 초과분은 다음 날 자동 예약). 실패 기록·쿼터 소비 없음.
            item.status, item.scheduled_date, item.updated_at = "pending", kst_today(now) + timedelta(days=1), now
            refresh_after_item(session, batch, now)
            audit.record(session, actor=actor, action="batch.item.deferred", target_type="batch_item", target_id=str(item.id), detail={"batch_id": batch.id, "code": "limit_daily"}, now=now)
            session.commit()
            return ItemOutcome(item.id, "deferred", "limit_daily", None)
        raise StepFailure("limit_" + report.failures[0].code.lower(), " / ".join(c.message for c in report.failures))
    # 4) 쿼터 선예약(재조회·갱신·검증 재조회를 한꺼번에: 쓰기 뒤 검증할 쿼터가 없는 상황을 막는다)
    state.reserved = reserve_calls(session, now, policy, [("videos.list", policy.read_cost), ("videos.update", policy.update_cost), ("videos.list", policy.read_cost)], job_id)
    r_read, r_update, r_verify = state.reserved
    # 5) 실행 직전 재조회
    try:
        fresh = gateway.read_snippet(video.video_id)
    except GatewayError as exc:
        mark_call(session, r_read, "failed")
        raise StepFailure("read_failed", f"영상을 다시 조회하지 못했습니다: {exc.message}", kind="failed") from None
    mark_call(session, r_read, "ok")
    if fresh is None:
        raise StepFailure("video_not_found", "유튜브에서 영상을 찾을 수 없습니다(삭제·비공개 처리 가능).", kind="failed")
    if not isinstance(fresh.get("title"), str) or not isinstance(fresh.get("categoryId"), str) or not fresh["categoryId"]:
        raise StepFailure("snippet_invalid", "재조회한 영상 정보에 제목 또는 categoryId 가 없어 중단했습니다.", kind="failed")
    if fresh["title"] != video.title:
        raise StepFailure("title_changed", "승인한 뒤 유튜브의 제목이 바뀌어 덮어쓰지 않고 중단했습니다.")
    ap = sug.approval
    if sug.plan_hash != ap.plan_hash or plan_hash_for(sug, video, fresh) != ap.plan_hash:
        raise StepFailure("video_changed", "승인한 뒤 영상 정보(설명·태그 등)가 바뀌어 중단했습니다. 다시 승인이 필요합니다.")
    # 6) 요청 본문(snippet 전체 + 제목만 교체)과 planned 기록, 승인 소진
    body = build_update_body(video.video_id, fresh, sug.title)
    _check_body(body, video.video_id, fresh, sug.title)
    change = Change(
        video_id=video.video_id, suggestion_id=sug.id, batch_id=batch.id, change_type="apply", previous_title=video.title, new_title=sug.title,
        backup_snippet=copy.deepcopy(fresh), reason=f"제안 #{sug.id} 적용", approver=ap.approver, approved_at=ap.approved_at, plan_hash=ap.plan_hash,
        result="planned", mode="live" if live_gateway.is_live(gateway) else "demo", created_at=now,
    )
    try:
        with session.begin_nested():
            session.add(change)
            session.flush()
    except IntegrityError:
        raise StepFailure("pending_change_exists", "이 영상에 진행 중인 변경이 있어 이중 반영을 막기 위해 중단했습니다.") from None
    state.change = change
    ap.used_at = now
    item.change_id = change.id
    session.commit()  # 쓰기 전에 planned 기록·쿼터 예약·승인 소진을 확정한다(중간에 끊겨도 재시작 후 재조회로 확정 가능)
    # 7) 갱신(모의)
    try:
        gateway.update_snippet(video.video_id, body)
        mark_call(session, r_update, "ok")
    except GatewayError as exc:
        mark_call(session, r_update, "failed")
        if exc.definite:
            raise StepFailure("update_failed", f"유튜브가 제목 변경을 처리하지 않았습니다: {exc.message}", kind="failed") from None
        _confirm_indeterminate(session, gateway, video.video_id, sug.title, state)
    session.commit()
    # 8) 재조회 검증 → changes 기록
    try:
        after = gateway.read_snippet(video.video_id)
        mark_call(session, r_verify, "ok")
    except GatewayError:
        mark_call(session, r_verify, "failed")
        after = None
    verify = verify_snippet(fresh, after, sug.title)
    change.result, change.applied_at, change.verified_at, change.verify_result = "success", now, now, verify
    if not verify["ok"]:
        change.error_code = "verify_failed"  # 반영은 일어났으므로 success 로 남기고(한도에 산입·롤백 가능), 항목은 failed 로 알린다
    sug.status, sug.updated_at = "applied", now
    item.status, item.updated_at = ("success" if verify["ok"] else "failed"), now
    item.skip_reason = None if verify["ok"] else "[verify_failed] 반영 후 재조회 검증에서 제목 또는 보존 항목이 맞지 않습니다. 이력에서 롤백을 검토하세요."
    refresh_after_item(session, batch, now)
    audit.record(session, actor=actor, action="change.apply", target_type="change", target_id=str(change.id), detail={"batch_id": batch.id, "video_id": video.video_id, "suggestion_id": sug.id, "verify_ok": verify["ok"]}, now=now)
    session.commit()
    return ItemOutcome(item.id, item.status, None if verify["ok"] else "verify_failed", change.id)


def _confirm_indeterminate(session: Session, gateway: YouTubeGateway, video_id: str, new_title: str, state: _State) -> None:
    """갱신 결과를 알 수 없을 때 한 번 재조회한다. 새 제목이 확인되면 계속하고, 아니면 planned 를 남긴 채 중단한다(자동 정리 없음)."""
    try:
        snap = gateway.read_snippet(video_id)
    except GatewayError:
        snap = None
    if snap is None or snap.get("title") != new_title:
        state.keep_planned = True
        raise StepFailure("result_unknown", "갱신 결과를 확인하지 못했습니다(반영됐을 수도 있습니다). 유튜브에서 현재 제목을 확인하세요.", kind="failed")


def refresh_after_item(session: Session, batch: Batch, now: datetime) -> None:
    session.flush()
    session.refresh(batch)
    refresh_batch_status(batch, now)


def _finish_failure(session: Session, item_id: int, sf: StepFailure, state: _State, now: datetime, env: Env, actor: str) -> ItemOutcome:
    item = session.get(BatchItem, item_id)
    release_unused(session, state.reserved)
    change = state.change
    if change is not None and change.result == "planned" and not state.keep_planned:
        change.result, change.error_code, change.applied_at = "failed", sf.code[:60], None
    item.status, item.updated_at = sf.kind, now
    item.skip_reason = f"[{sf.code}] {sf.message}"[:200]
    sug = session.get(Suggestion, item.suggestion_id)
    batch = session.get(Batch, item.batch_id)
    if sug is not None:
        release_after_item(sug, session.get(Video, item.video_id), env, now, (batch.executed_at if batch else None) or now)
    if batch is not None:
        refresh_after_item(session, batch, now)
    audit.record(session, actor=actor, action=f"batch.item.{sf.kind}", target_type="batch_item", target_id=str(item_id), detail={"batch_id": item.batch_id, "code": sf.code, "change_id": item.change_id}, now=now)
    session.commit()
    return ItemOutcome(item_id, sf.kind, sf.code, item.change_id)


# ───────────── 재시작 복구 ─────────────

def recover_running_items(factory: sessionmaker, now: datetime, env: Env | None = None, *, gateway_factory: GatewayFactory = mock_gateway_factory, stale_after: timedelta = STALE_RUNNING) -> int:
    """비정상 종료로 running 에 남은 항목을 재조회로 확정해 정리한다. 워커 기동 직후에는 stale_after=0 으로 부르면 된다."""
    env = env or default_env()
    fixed = 0
    with factory() as s:
        ids = s.execute(select(BatchItem.id).where(BatchItem.status == "running", BatchItem.updated_at <= now - stale_after)).scalars().all()
    for item_id in ids:
        with factory() as s:
            if _recover_one(s, item_id, now, env, gateway_factory(s, now)):
                fixed += 1
            s.commit()
    return fixed


def _recover_one(s: Session, item_id: int, now: datetime, env: Env, gateway: YouTubeGateway) -> bool:
    item = s.execute(lock_rows(select(BatchItem).where(BatchItem.id == item_id, BatchItem.status == "running"), s)).scalar_one_or_none()
    if item is None:
        return False
    batch, sug, video = s.get(Batch, item.batch_id), s.get(Suggestion, item.suggestion_id), s.get(Video, item.video_id)
    change = s.get(Change, item.change_id) if item.change_id else None
    if change is None:  # planned 기록 전에 끊김: 아무것도 쓰지 않았으므로 처음부터 다시 처리
        item.status, item.updated_at = "pending", now
    elif change.result != "planned":
        item.status = "success" if change.result == "success" and not change.error_code else "failed"
        item.skip_reason = None if item.status == "success" else f"[{change.error_code or change.result}] 재시작 후 정리"
        item.updated_at = now
    else:
        snap = gateway.read_snippet(change.video_id)
        if snap is not None and snap.get("title") == change.new_title:
            verify = verify_snippet(change.backup_snippet or {}, snap, change.new_title)
            change.result, change.applied_at, change.verified_at, change.verify_result = "success", now, now, {**verify, "note": "재시작 후 재조회로 확정"}
            if not verify["ok"]:
                change.error_code = "verify_failed"
            if sug is not None:
                sug.status, sug.updated_at = "applied", now
            item.status, item.updated_at = ("success" if verify["ok"] else "failed"), now
            item.skip_reason = None if verify["ok"] else "[verify_failed] 재시작 후 검증에서 보존 항목이 맞지 않습니다."
            # 정상 경로와 같은 추적성: 변경·영상·제안 ID 가 추가 전용 감사에 남아야 한다(changes 표만으로는 복원할 수 없다, DEF-7B-002)
            audit.record(s, actor=WORKER, action="change.apply", target_type="change", target_id=str(change.id),
                         detail={"batch_id": item.batch_id, "video_id": change.video_id, "suggestion_id": change.suggestion_id, "verify_ok": verify["ok"], "recovered": True, "reason": "restart_recovery"}, now=now)
        elif snap is not None and snap.get("title") == change.previous_title:
            change.result, change.error_code = "aborted", "interrupted"
            item.status, item.skip_reason, item.updated_at = "failed", "[interrupted] 반영 도중 중단되어 제목은 바뀌지 않았습니다.", now
            if sug is not None:
                release_after_item(sug, video, env, now, (batch.executed_at if batch else None) or now)
        else:
            item.status, item.skip_reason, item.updated_at = "failed", "[result_unknown] 재시작 후에도 결과를 확정하지 못했습니다. 유튜브에서 제목을 확인하세요.", now
    if batch is not None:
        refresh_after_item(s, batch, now)
    audit.record(s, actor=WORKER, action="batch.item.recovered", target_type="batch_item", target_id=str(item.id),
                 detail={"status": item.status, "batch_id": item.batch_id, "video_id": item.video_id, "change_id": item.change_id}, now=now)
    return True


# ───────────── 워커 틱 ─────────────

@dataclass
class TickResult:
    processed: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    stopped_by: str | None = None  # None(할 일 없음) | cap_reached | quota_exhausted

    def add(self, outcome: ItemOutcome) -> None:
        if outcome.status in ("not_pending", "deferred"):
            return
        self.processed += 1
        setattr(self, outcome.status, getattr(self, outcome.status) + 1)


def _next_due_item(s: Session, today: date, batch_id: int | None) -> BatchItem | None:
    stmt = (
        select(BatchItem).join(Batch, Batch.id == BatchItem.batch_id)
        .where(BatchItem.status == "pending", BatchItem.scheduled_date.is_not(None), BatchItem.scheduled_date <= today, Batch.status.in_(("queued", "running")))
        .order_by(BatchItem.scheduled_date, BatchItem.batch_id, BatchItem.seq).limit(1)
    )
    if batch_id is not None:
        stmt = stmt.where(BatchItem.batch_id == batch_id)
    if s.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True, of=BatchItem)
    return s.execute(stmt).scalar_one_or_none()


def run_due_items(factory: sessionmaker, now: datetime, env: Env | None = None, *, batch_id: int | None = None, gateway_factory: GatewayFactory = mock_gateway_factory,
                  on_progress: Callable[[int], None] | None = None, job_id: str | None = None) -> TickResult:
    """워커 틱. 오늘 남은 상한과 쿼터 안에서 도래한 항목만 처리한다(놓친 예약을 몰아서 실행하지 않음)."""
    env = env or default_env()
    result = TickResult()
    with factory() as s:
        expire_stale_approvals(s, now)
        s.commit()
    recover_running_items(factory, now, env, gateway_factory=gateway_factory)
    today = kst_today(now)
    for _ in range(MAX_BATCH_ITEMS * 40):  # 무한 반복 방지용 상한
        with factory() as s:
            remaining = effective_daily_cap(s, env.policy) - applied_today(s, now)
            if remaining <= 0:
                result.stopped_by = "cap_reached" if _next_due_item(s, today, batch_id) is not None else None
                break
            if quota_state(s, now, env.policy).remaining < units_per_apply(env.policy):
                result.stopped_by = "quota_exhausted" if _next_due_item(s, today, batch_id) is not None else None
                break
            item = _next_due_item(s, today, batch_id)
            if item is None:
                break
            outcome = apply_one(s, item.id, now=now, env=env, gateway=gateway_factory(s, now), job_id=job_id)
        result.add(outcome)
        if on_progress is not None and outcome.status not in ("not_pending", "deferred"):
            on_progress(result.processed)
    return result
