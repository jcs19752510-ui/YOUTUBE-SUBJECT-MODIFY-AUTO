"""변경 이력 조회와 롤백(WEB_DESIGN §4-5). 규칙은 youtube_title.history.plan_rollback 과 같다.

- 성공한 적용(apply)만 되돌릴 수 있다. 대상 영상 ID 를 직접 입력해야 한다(typed_video_id).
- 그 변경 이후 같은 영상에 다른 변경(success/planned)이 있으면 거부한다(오래된 제목으로 최신 제목을 덮는 사고·이중 롤백 방지).
- 복원 본문은 백업 snippet 전체다(반영 중 설명 등이 사라졌더라도 되살린다). 복원 뒤 재조회로 제목과 보존 항목을 검증한다.
- 교체 한도(72시간·횟수·노출수·하루 상한)는 사고 복구가 막히지 않도록 롤백에 적용하지 않는다. 쿼터는 쓴다.
"""
from __future__ import annotations

import copy
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from youtube_title.errors import YtError
from youtube_title.updater import compute_plan_hash, validate_new_title

from ytweb.core import audit
from ytweb.core.errors import ProblemError
from ytweb.db.models import Change, Suggestion, Video
from ytweb.domain import live_gateway
from ytweb.domain.batches import verify_snippet
from ytweb.domain.common import Env, StepFailure, clamp_page, clean_approver, lock_rows
from ytweb.domain.limits_quota import COUNTED_RESULTS, mark_call, release_unused, reserve_calls
from ytweb.youtube.base import GatewayError, YouTubeGateway


def get_change(session: Session, change_id: int, *, lock: bool = False) -> Change:
    stmt = select(Change).where(Change.id == change_id)
    change = session.execute(lock_rows(stmt, session) if lock else stmt).scalar_one_or_none()
    if change is None:
        raise ProblemError(404, "change_not_found", "변경 기록을 찾을 수 없습니다.", hint="이력 목록을 새로고침하세요.")
    return change


def rollbackable_map(session: Session, changes: list[Change]) -> dict[int, bool]:
    """각 변경이 지금 롤백 가능한지: 성공한 적용이고 백업이 있으며 그 영상의 가장 마지막 변경(success/planned)일 때."""
    ids = {c.video_id for c in changes}
    latest: dict[str, int] = {}
    if ids:
        rows = session.execute(select(Change.video_id, func.max(Change.id)).where(Change.video_id.in_(ids), Change.result.in_(COUNTED_RESULTS)).group_by(Change.video_id)).all()
        latest = {v: m for v, m in rows}
    return {
        c.id: bool(c.change_type == "apply" and c.result == "success" and isinstance(c.backup_snippet, dict) and latest.get(c.video_id) == c.id)
        for c in changes
    }


def list_changes(session: Session, *, video_id: str | None, batch_id: int | None, result: str | None, page: int, page_size: int) -> tuple[list[tuple[Change, str | None]], dict[int, bool], int]:
    page, page_size = clamp_page(page, page_size)
    conds = []
    if video_id:
        conds.append(Change.video_id == video_id)
    if batch_id is not None:
        conds.append(Change.batch_id == batch_id)
    if result:
        conds.append(Change.result == result)
    total = int(session.execute(select(func.count()).select_from(Change).where(*conds)).scalar_one())
    rows = session.execute(
        select(Change, Video.title).join(Video, Video.video_id == Change.video_id).where(*conds).order_by(Change.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    pairs = [(c, t) for c, t in rows]
    return pairs, rollbackable_map(session, [c for c, _ in pairs]), total


def rollback_change(session: Session, change_id: int, typed_video_id: str, approver: str, *, now: datetime, env: Env, gateway: YouTubeGateway, actor: str = "web") -> Change:
    name = clean_approver(approver)
    target = get_change(session, change_id, lock=True)
    if target.change_type != "apply" or target.result != "success":
        raise ProblemError(409, "not_rollbackable", "성공한 제목 변경만 되돌릴 수 있습니다.", detail=f"변경 #{target.id}: {target.change_type}/{target.result}", hint="되돌릴 변경(적용 성공)을 선택하세요.")
    if typed_video_id != target.video_id:
        raise ProblemError(422, "typed_video_id_mismatch", "입력한 영상 ID가 대상과 다릅니다.", hint="화면에 표시된 영상 ID를 그대로 입력하세요.")
    later = session.execute(select(Change.id).where(Change.video_id == target.video_id, Change.id > target.id, Change.result.in_(COUNTED_RESULTS)).order_by(Change.id).limit(1)).scalar_one_or_none()
    if later is not None:
        raise ProblemError(409, "later_change_exists", f"이 변경 이후 같은 영상의 다른 변경(#{later})이 있어 되돌릴 수 없습니다.", hint="가장 최근 변경부터 확인하세요. 이미 되돌렸다면 더 할 일이 없습니다.")
    backup = target.backup_snippet
    if not isinstance(backup, dict) or backup.get("title") != target.previous_title or not isinstance(backup.get("categoryId"), str) or not backup["categoryId"]:
        raise ProblemError(409, "backup_invalid", "백업 정보가 없거나 이력과 맞지 않아 되돌릴 수 없습니다.", hint="유튜브 Studio에서 직접 되돌리세요.")
    video = session.get(Video, target.video_id)
    if video is None:
        raise ProblemError(404, "video_not_found", "영상을 찾을 수 없습니다.", hint="영상 목록을 새로고침하세요.")
    restore_title = backup["title"]
    try:
        validate_new_title(restore_title, env.policy, check_length=False)
    except YtError as exc:
        raise ProblemError(409, "backup_invalid", f"복원할 제목이 규격에 맞지 않습니다: {exc.message}", hint="유튜브 Studio에서 직접 되돌리세요.") from None
    not_allowed = live_gateway.not_allowed_reason(video.video_id, env.secrets_dir)
    if not_allowed:
        raise ProblemError(409, "live_not_allowed", "실제 수정 허용 영상이 아니어서 되돌리지 않았습니다.", detail=not_allowed, hint="유튜브 Studio에서 직접 되돌리거나 허용 목록에 영상 ID를 추가하세요.")
    policy = env.policy
    try:
        r_read, r_update, r_verify = reserve_calls(session, now, policy, [("videos.list", policy.read_cost), ("videos.update", policy.update_cost), ("videos.list", policy.read_cost)])
    except StepFailure as exc:
        raise ProblemError(429, "quota_exhausted", "오늘 API 쿼터가 부족해 롤백하지 못했습니다.", detail=exc.message, hint="쿼터는 태평양 시간 자정(한국 시간 오후 4~5시)에 초기화됩니다.") from None
    reserved = [r_read, r_update, r_verify]
    try:
        current = gateway.read_snippet(video.video_id)
        mark_call(session, r_read, "ok")
    except GatewayError as exc:
        mark_call(session, r_read, "failed")
        release_unused(session, reserved)
        session.commit()
        raise ProblemError(502, "gateway_error", "영상을 다시 조회하지 못했습니다.", detail=exc.message, hint="잠시 후 다시 시도하세요.") from None
    if current is None:
        release_unused(session, reserved)
        session.commit()
        raise ProblemError(404, "video_not_found", "유튜브에서 영상을 찾을 수 없습니다.", hint="영상이 삭제되었거나 비공개 처리되었는지 확인하세요.")
    if current.get("title") == restore_title:
        release_unused(session, reserved)
        session.commit()
        raise ProblemError(409, "already_restored", "현재 제목이 이미 원래 제목과 같아 되돌릴 내용이 없습니다.", hint="영상 목록을 새로고침해 최신 상태를 확인하세요.")
    body = {"id": video.video_id, "snippet": copy.deepcopy(backup)}
    plan_hash = compute_plan_hash(video.video_id, target.suggestion_id, current["title"], restore_title, current, kind="rollback", change_id=target.id)
    rb = Change(
        video_id=video.video_id, suggestion_id=target.suggestion_id, batch_id=None, change_type="rollback", previous_title=current["title"], new_title=restore_title,
        backup_snippet=copy.deepcopy(current), reason=f"롤백 대상 변경 #{target.id}", approver=name, approved_at=now, plan_hash=plan_hash, result="planned", mode="live" if live_gateway.is_live(gateway) else "demo", created_at=now,
    )
    try:
        with session.begin_nested():
            session.add(rb)
            session.flush()
    except IntegrityError:
        release_unused(session, reserved)
        session.commit()
        raise ProblemError(409, "pending_change_exists", "이 영상에 진행 중인 변경이 있어 롤백할 수 없습니다.", hint="진행 중인 반영이 끝난 뒤 다시 시도하세요.") from None
    session.commit()
    try:
        gateway.update_snippet(video.video_id, body)
        mark_call(session, r_update, "ok")
    except GatewayError as exc:
        mark_call(session, r_update, "failed")
        release_unused(session, reserved)
        rb.result, rb.error_code = ("failed", exc.code[:60]) if exc.definite else ("planned", None)
        audit.record(session, actor=actor, action="change.rollback_failed", target_type="change", target_id=str(target.id), detail={"code": exc.code, "definite": exc.definite}, now=now)
        session.commit()
        raise ProblemError(502, "gateway_error", "유튜브가 롤백 요청을 처리하지 못했습니다." if exc.definite else "롤백 결과를 확인하지 못했습니다.", detail=exc.message,
                           hint="잠시 후 다시 시도하세요." if exc.definite else "유튜브 Studio에서 현재 제목을 확인하세요.") from None
    try:
        after = gateway.read_snippet(video.video_id)
        mark_call(session, r_verify, "ok")
    except GatewayError:
        mark_call(session, r_verify, "failed")
        after = None
    verify = verify_snippet(backup, after, restore_title)
    verify["changed_since_backup"] = sorted(k for k in set(backup) | set(current) if k != "title" and backup.get(k) != current.get(k))
    rb.result, rb.applied_at, rb.verified_at, rb.verify_result = "success", now, now, verify
    if not verify["ok"]:
        rb.error_code = "verify_failed"
    sug = session.get(Suggestion, target.suggestion_id) if target.suggestion_id else None
    if sug is not None and sug.status == "applied":
        sug.status, sug.updated_at = "rolled_back", now
    session.flush()
    audit.record(session, actor=actor, action="change.rollback", target_type="change", target_id=str(rb.id), detail={"target_change": target.id, "video_id": video.video_id, "approver": name, "verify_ok": verify["ok"]}, now=now)
    return rb
