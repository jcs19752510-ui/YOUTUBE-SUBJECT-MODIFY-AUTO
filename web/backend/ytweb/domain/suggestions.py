"""제안 생성·사람 수정·승인·반려(WEB_DESIGN §4-1,2). 승인은 plan_hash 에 묶이고 TTL 이 지나면 만료되며 HMAC 으로 변조를 탐지한다."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from youtube_title.candidates import Candidate, CandidateFile
from youtube_title.timeutil import utc_iso
from youtube_title.updater import canonical_json, compute_plan_hash
from youtube_title.validator import CandidateResult, FileResult, validate_file

from ytweb.ai.base import SuggestionDraft, TitleSuggester, TitleSuggestionError, VideoBrief
from ytweb.ai.rule import RuleSuggester
from ytweb.ai.guard import MAX_TITLE_CHARS, build_summary, clean_text, sanitize_drafts
from ytweb.core import audit
from ytweb.core.errors import ProblemError
from ytweb.db.models import AiRun, Approval, Suggestion, Video
from ytweb.domain.common import Env, clamp_page, clean_approver, lock_rows
from ytweb.domain.exclusions import exclusion_reasons

KEY_FILE = "approval_hmac.key"
KEY_BYTES = 32
MAX_COUNT = 5
EDITABLE = ("candidate", "blocked", "approved", "expired", "rejected")
REJECTABLE = ("candidate", "blocked", "approved", "expired")
ACTOR = "web"


class ApprovalInvalid(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ───────────── HMAC 키·승인 인증값 ─────────────

def _key_path(secrets_dir: Path) -> Path:
    return Path(secrets_dir) / KEY_FILE


def _load_key(secrets_dir: Path, *, create: bool) -> bytes:
    path = _key_path(secrets_dir)
    if path.exists():
        try:
            key = bytes.fromhex(path.read_text(encoding="ascii").strip())
        except (ValueError, OSError, UnicodeDecodeError):
            raise ApprovalInvalid("approval_key_unreadable", "승인 인증 키 파일을 읽을 수 없습니다.") from None
        if len(key) != KEY_BYTES:
            raise ApprovalInvalid("approval_key_unreadable", "승인 인증 키 파일의 길이가 올바르지 않습니다.")
        return key
    if not create:
        raise ApprovalInvalid("approval_key_missing", "승인 인증 키가 없어 승인을 믿을 수 없습니다.")
    key = secrets.token_bytes(KEY_BYTES)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # 동시에 다른 프로세스가 먼저 만든 경우 그 키를 쓴다
        return _load_key(secrets_dir, create=False)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(key.hex())
    return key


def compute_mac(key: bytes, *, suggestion_id: int, video_id: str, plan_hash: str, approver: str, approved_at: datetime, expires_at: datetime) -> str:
    payload = {
        "v": 1, "suggestion_id": suggestion_id, "video_id": video_id, "plan_hash": plan_hash, "approver": approver,
        "approved_at": utc_iso(approved_at), "expires_at": utc_iso(expires_at),
    }
    return hmac.new(key, canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def plan_hash_for(sug: Suggestion, video: Video, snippet: dict | None = None) -> str:
    snap = video.snippet if snippet is None else snippet
    return compute_plan_hash(video.video_id, sug.id, snap["title"], sug.title, snap)


def check_approval(sug: Suggestion, video: Video, env: Env, ref_time: datetime, *, snippet: dict | None = None) -> None:
    """승인이 지금 쓸 수 있는지 확인한다. 쓸 수 없으면 ApprovalInvalid(코드). ref_time 은 만료 판정 기준 시각."""
    ap = sug.approval
    if ap is None:
        raise ApprovalInvalid("approval_missing", "승인 기록이 없습니다.")
    try:
        key = _load_key(env.secrets_dir, create=False)
    except ApprovalInvalid as exc:
        raise ApprovalInvalid("approval_tampered", exc.message) from None
    expected = compute_mac(key, suggestion_id=sug.id, video_id=sug.video_id, plan_hash=ap.plan_hash, approver=ap.approver, approved_at=ap.approved_at, expires_at=ap.expires_at)
    if not hmac.compare_digest(expected, ap.mac):
        raise ApprovalInvalid("approval_tampered", "승인 기록의 인증값이 맞지 않아 변조되었을 수 있습니다.")
    if ap.used_at is not None:
        raise ApprovalInvalid("approval_used", "이미 사용된 승인입니다(승인은 1회용).")
    if ref_time >= ap.expires_at:
        raise ApprovalInvalid("approval_expired", "승인 유효 시간이 지났습니다.")
    snap = video.snippet if snippet is None else snippet
    if not isinstance(snap, dict) or not isinstance(snap.get("title"), str):
        raise ApprovalInvalid("plan_mismatch", "영상 정보가 올바르지 않습니다.")
    if sug.plan_hash != ap.plan_hash or plan_hash_for(sug, video, snap) != ap.plan_hash:
        raise ApprovalInvalid("plan_mismatch", "승인한 뒤 영상 정보나 제목이 바뀌어 승인이 무효입니다(계획 해시 불일치).")


# ───────────── 검증 연동 ─────────────

def validate_title(env: Env, video: Video, title: str, evidence: str, topic: str | None) -> tuple[CandidateResult, FileResult]:
    summary = video.description_excerpt or video.title
    cf = CandidateFile(
        video_id=video.video_id, current_title=video.title, topic=topic, summary=summary, source="web", description_excerpt=None,
        candidates=(Candidate(title, evidence),), sha256=hashlib.sha256(title.encode("utf-8")).hexdigest(), file_name=f"{video.video_id}.json",
    )
    file_result = validate_file(cf, env.dictionary, env.policy)
    return file_result.results[0], file_result


def _apply_validation(sug: Suggestion, res: CandidateResult, fr: FileResult, now: datetime) -> None:
    sug.validation_result = res.result
    sug.validation_reasons = [{"code": f.code, "severity": f.severity, "message": f.message} for f in res.findings]
    sug.match_ratio = res.match_ratio
    sug.strict_mode = res.strict
    sug.dictionary_hash = fr.dictionary_hash
    sug.updated_at = now


def is_blocking(sug: Suggestion) -> bool:
    return sug.validation_result == "block" or (sug.strict_mode and sug.validation_result != "pass")


def get_suggestion(session: Session, suggestion_id: int, *, lock: bool = False) -> Suggestion:
    stmt = select(Suggestion).where(Suggestion.id == suggestion_id)
    sug = session.execute(lock_rows(stmt, session) if lock else stmt).scalar_one_or_none()
    if sug is None:
        raise ProblemError(404, "suggestion_not_found", "제안을 찾을 수 없습니다.", hint="목록을 새로고침해 다시 선택하세요.")
    return sug


def _get_video(session: Session, video_id: str) -> Video:
    video = session.get(Video, video_id)
    if video is None:
        raise ProblemError(404, "video_not_found", "영상을 찾을 수 없습니다.", hint="영상 목록을 새로고침하세요.")
    return video


# ───────────── 생성 ─────────────

def generate_for_video(session: Session, video_id: str, *, count: int, tone: str, now: datetime, env: Env, suggester: TitleSuggester, actor: str = ACTOR) -> list[Suggestion]:
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_COUNT:
        raise ProblemError(422, "count_invalid", f"후보 수는 1~{MAX_COUNT}개여야 합니다.", hint="후보 수를 고쳐 다시 요청하세요.")
    video = _get_video(session, video_id)
    reasons = exclusion_reasons(video, env.policy)
    if reasons:
        raise ProblemError(409, "video_excluded", "제외 대상 영상이라 제안을 만들지 않습니다.", detail=", ".join(reasons), hint="공개 상태의 일반(롱폼) 영상에서 시도하세요.")
    brief = VideoBrief(video.video_id, clean_text(video.title, 300), build_summary(video.description_excerpt))
    if suggester.name == "mock" and video.source != "demo":  # 실제 영상에는 시연용 차단 후보를 섞는 모의 제안기를 쓰지 않는다
        suggester = RuleSuggester()
    prompt_hash = hashlib.sha256(canonical_json({"v": brief.video_id, "t": brief.title, "s": brief.summary, "n": count, "tone": tone}).encode("utf-8")).hexdigest()
    run = AiRun(
        video_id=video_id, provider=suggester.name, model=suggester.model, params={"count": count, "tone": tone}, prompt_hash=prompt_hash,
        input_chars=len(brief.title) + len(brief.summary), status="ok", created_at=now,
    )
    session.add(run)
    try:
        raw = suggester.suggest(brief, count=count, tone=tone)
    except Exception as exc:  # noqa: BLE001 - 외부 어댑터 경계: 어떤 오류든 실행 기록을 남기고 사용자에게 한국어로 알린다
        run.status, run.error = "failed", type(exc).__name__ if not isinstance(exc, TitleSuggestionError) else str(exc)[:300]
        audit.record(session, actor=actor, action="suggestion.generate_failed", target_type="video", target_id=video_id, detail={"error": type(exc).__name__}, now=now)
        session.commit()  # 요청이 실패로 끝나도 실패 기록은 남긴다
        raise ProblemError(502, "ai_unavailable", "AI 제안기가 응답하지 못했습니다.", hint="잠시 후 다시 시도하거나, 제목을 직접 수정해 사용하세요.") from exc
    guarded = sanitize_drafts(raw, max_count=count)
    run.params = {"count": count, "tone": tone, "returned": len(raw) if hasattr(raw, "__len__") else None, "dropped": [list(d) for d in guarded.dropped]}
    session.flush()
    if not guarded.drafts:
        run.status, run.error = "failed", "no_valid_candidates"
        session.commit()
        raise ProblemError(502, "ai_no_candidates", "AI 응답에서 쓸 수 있는 후보가 없었습니다.", hint="다시 생성하거나 제목을 직접 수정해 사용하세요.")
    result: list[Suggestion] = []
    created = reused = 0
    for draft in guarded.drafts:
        existing = session.execute(select(Suggestion).where(Suggestion.video_id == video_id, Suggestion.title == draft.title)).scalar_one_or_none()
        if existing is not None:
            result.append(existing)
            reused += 1
            continue
        sug = _new_suggestion(env, video, draft, run, f"ai:{suggester.name}", now)
        session.add(sug)
        result.append(sug)
        created += 1
    session.flush()
    audit.record(session, actor=actor, action="suggestion.generate", target_type="video", target_id=video_id, detail={"count": count, "created": created, "reused": reused, "dropped": len(guarded.dropped), "ai_run_id": run.id}, now=now)
    return result


def _new_suggestion(env: Env, video: Video, draft: SuggestionDraft, run: AiRun, source: str, now: datetime) -> Suggestion:
    res, fr = validate_title(env, video, draft.title, draft.evidence, draft.topic)
    sug = Suggestion(video_id=video.video_id, title=draft.title, evidence=draft.evidence, source=source, ai_run_id=run.id, topic=draft.topic, created_at=now, updated_at=now)
    _apply_validation(sug, res, fr, now)
    sug.status = "blocked" if res.result == "block" else "candidate"
    return sug


# ───────────── 수정·반려 ─────────────

def _drop_approval(session: Session, sug: Suggestion) -> bool:
    if sug.approval is None:
        return False
    session.delete(sug.approval)
    sug.approval = None
    sug.plan_hash = None
    session.flush()
    return True


def edit_title(session: Session, suggestion_id: int, new_title: str, *, now: datetime, env: Env, actor: str = ACTOR) -> Suggestion:
    sug = get_suggestion(session, suggestion_id, lock=True)
    if sug.status not in EDITABLE:
        raise ProblemError(409, "suggestion_state", f"현재 상태({sug.status})에서는 제목을 수정할 수 없습니다.", hint="배치에 담겼거나 이미 반영된 제안은 수정할 수 없습니다.")
    if not isinstance(new_title, str):
        raise ProblemError(422, "title_invalid", "제목이 올바르지 않습니다.", hint="제목을 문자열로 입력하세요.")
    title = clean_text(new_title)
    if not title:
        raise ProblemError(422, "title_empty", "제목이 비어 있습니다.", hint="제목을 입력하세요.")
    if len(title) > MAX_TITLE_CHARS:
        raise ProblemError(422, "title_too_long", f"제목이 너무 깁니다({MAX_TITLE_CHARS}자 이하).", hint="제목을 줄여 다시 입력하세요.")
    if title == sug.title:
        return sug
    dup = session.execute(select(Suggestion.id).where(Suggestion.video_id == sug.video_id, Suggestion.title == title, Suggestion.id != sug.id)).first()
    if dup is not None:
        raise ProblemError(409, "duplicate_suggestion", "이 영상에 같은 제목의 제안이 이미 있습니다.", hint="기존 제안을 선택하세요.")
    video = _get_video(session, sug.video_id)
    invalidated = _drop_approval(session, sug)
    old = sug.title
    sug.title = title
    if sug.source != "manual" and not sug.source.endswith("+edited"):
        sug.source = f"{sug.source}+edited"[:40]  # AI 원문을 사람이 고친 제안임을 구분한다(규칙 J, 원문 출처는 접두에 남는다)
    res, fr = validate_title(env, video, title, sug.evidence or "", sug.topic)
    _apply_validation(sug, res, fr, now)
    sug.status = "blocked" if res.result == "block" else "candidate"
    session.flush()
    audit.record(session, actor=actor, action="suggestion.edit", target_type="suggestion", target_id=str(sug.id), detail={"from": old[:100], "to": title[:100], "result": res.result, "approval_invalidated": invalidated}, now=now)
    return sug


def reject(session: Session, suggestion_id: int, *, now: datetime, actor: str = ACTOR) -> Suggestion:
    sug = get_suggestion(session, suggestion_id, lock=True)
    if sug.status not in REJECTABLE:
        raise ProblemError(409, "suggestion_state", f"현재 상태({sug.status})에서는 반려할 수 없습니다.", hint="배치에 담긴 제안은 배치를 중지한 뒤 반려하세요.")
    invalidated = _drop_approval(session, sug)
    sug.status, sug.updated_at = "rejected", now
    session.flush()
    audit.record(session, actor=actor, action="suggestion.reject", target_type="suggestion", target_id=str(sug.id), detail={"approval_invalidated": invalidated}, now=now)
    return sug


# ───────────── 승인 ─────────────

def approve(session: Session, suggestion_id: int, approver: str, *, now: datetime, env: Env, actor: str = ACTOR) -> Suggestion:
    name = clean_approver(approver)
    sug = get_suggestion(session, suggestion_id, lock=True)
    if sug.status not in ("candidate", "expired"):
        code = "suggestion_blocked" if sug.status == "blocked" else "suggestion_state"
        raise ProblemError(409, code, "차단 판정이라 승인할 수 없습니다." if code == "suggestion_blocked" else f"현재 상태({sug.status})에서는 승인할 수 없습니다.",
                           detail="; ".join(r["message"] for r in sug.validation_reasons if r.get("severity") == "block") if code == "suggestion_blocked" else "",
                           hint="제목을 수정해 다시 검증하거나 다른 후보를 선택하세요." if code == "suggestion_blocked" else "목록을 새로고침해 상태를 확인하세요.")
    video = _get_video(session, sug.video_id)
    reasons = exclusion_reasons(video, env.policy)
    if reasons:
        raise ProblemError(409, "video_excluded", "제외 대상 영상이라 승인할 수 없습니다.", detail=", ".join(reasons), hint="공개 상태의 일반(롱폼) 영상만 반영할 수 있습니다.")
    res, fr = validate_title(env, video, sug.title, sug.evidence or "", sug.topic)  # 사전·영상이 바뀌었을 수 있어 승인 시점에 다시 검증(fail-closed)
    _apply_validation(sug, res, fr, now)
    if is_blocking(sug):
        raise ProblemError(409, "suggestion_blocked", "다시 검증한 결과 차단 판정이라 승인할 수 없습니다." if res.result == "block" else "엄격 모드(건강·금융)에서는 경고도 승인할 수 없습니다.",
                           detail="; ".join(f.message for f in res.findings), hint="제목을 수정해 다시 검증하세요.")
    if not isinstance(video.snippet, dict) or video.snippet.get("title") != video.title:
        raise ProblemError(409, "video_inconsistent", "저장된 영상 정보가 서로 맞지 않습니다.", hint="영상 목록을 새로고침(동기화)한 뒤 다시 시도하세요.")
    if sug.title == video.title:
        raise ProblemError(409, "same_as_current", "현재 제목과 같아 바꿀 내용이 없습니다.", hint="다른 제목을 선택하세요.")
    ttl = timedelta(hours=env.policy.approval_ttl_hours)
    sug.plan_hash = plan_hash_for(sug, video)
    try:
        key = _load_key(env.secrets_dir, create=True)
    except ApprovalInvalid as exc:  # 키 파일이 깨져 있으면 새 키로 덮어쓰지 않고(기존 승인 전부 무효화 방지) 승인을 거부한다
        raise ProblemError(500, exc.code, "승인 인증 키를 사용할 수 없어 승인할 수 없습니다.", detail=exc.message, hint="관리자에게 알리세요. 비밀 폴더의 approval_hmac.key 파일 상태를 확인해야 합니다.") from None
    expires = now + ttl
    mac = compute_mac(key, suggestion_id=sug.id, video_id=sug.video_id, plan_hash=sug.plan_hash, approver=name, approved_at=now, expires_at=expires)
    if sug.approval is not None:  # 만료/사용된 이전 승인을 새 승인으로 교체
        session.delete(sug.approval)
        session.flush()
    sug.approval = Approval(suggestion_id=sug.id, plan_hash=sug.plan_hash, approver=name, approved_at=now, expires_at=expires, mac=mac)
    sug.status, sug.updated_at = "approved", now
    session.flush()
    audit.record(session, actor=actor, action="suggestion.approve", target_type="suggestion", target_id=str(sug.id), detail={"approver": name, "result": sug.validation_result, "plan_hash": sug.plan_hash[:12], "expires_at": utc_iso(expires)}, now=now)
    return sug


# ───────────── 만료·반환 ─────────────

def expire_stale_approvals(session: Session, now: datetime) -> int:
    """승인 대기(approved) 중 유효 시간이 지난 제안을 expired 로 바꾼다. 배치에 담긴(queued) 제안은 건드리지 않는다."""
    rows = session.execute(select(Suggestion).join(Approval, Approval.suggestion_id == Suggestion.id).where(Suggestion.status == "approved", Approval.expires_at <= now)).scalars().all()
    for sug in rows:
        sug.status, sug.updated_at = "expired", now
    if rows:
        session.flush()
    return len(rows)


def release_after_item(sug: Suggestion, video: Video | None, env: Env, now: datetime, ref_time: datetime) -> None:
    """배치 항목이 반영 없이 끝났을 때(건너뜀·취소·실패) 제안을 되돌린다: 승인이 아직 쓸 수 있으면 approved, 아니면 expired."""
    if sug.status != "queued":
        return
    try:
        if video is None:
            raise ApprovalInvalid("video_missing", "영상이 없습니다.")
        check_approval(sug, video, env, ref_time)
        sug.status = "approved"
    except ApprovalInvalid:
        sug.status = "expired"
    sug.updated_at = now


# ───────────── 조회 ─────────────

def list_suggestions(session: Session, *, video_id: str | None, status: str | None, result: str | None, page: int, page_size: int, now: datetime) -> tuple[list[Suggestion], int]:
    expire_stale_approvals(session, now)
    page, page_size = clamp_page(page, page_size)
    conds = []
    if video_id:
        conds.append(Suggestion.video_id == video_id)
    if status:
        conds.append(Suggestion.status == status)
    if result:
        conds.append(Suggestion.validation_result == result)
    total = int(session.execute(select(func.count()).select_from(Suggestion).where(*conds)).scalar_one())
    rows = session.execute(select(Suggestion).where(*conds).order_by(Suggestion.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return list(rows), total
