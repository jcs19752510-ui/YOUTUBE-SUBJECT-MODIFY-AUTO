"""ORM → API 응답 딕셔너리(WEB_DESIGN §3 스키마). 응답 모델 검증은 schemas.py 가 맡는다."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from youtube_title.textsafe import char_count

from ytweb.domain.batches import describe_verify
from ytweb.domain.kinds import video_kind
from ytweb.db.models import Batch, BatchItem, Change, Job, Suggestion, Video


def suggestion_kinds(session: Session, suggestions) -> dict[str, str | None]:
    """제안들의 영상 구분(롱폼/쇼츠)을 영상 테이블 한 번의 조회로 구한다(영상 ID → 구분)."""
    ids = {s.video_id for s in suggestions}
    if not ids:
        return {}
    rows = session.execute(select(Video.video_id, Video.is_short, Video.duration_sec).where(Video.video_id.in_(ids))).all()
    return {vid: video_kind(sh, dur) for vid, sh, dur in rows}


def suggestion_dict(s: Suggestion, kinds: dict[str, str | None] | None = None) -> dict:
    ap = s.approval
    return {
        "video_kind": (kinds or {}).get(s.video_id),
        "id": s.id,
        "video_id": s.video_id,
        "title": s.title,
        "evidence": s.evidence,
        "source": s.source,
        "topic": s.topic,
        "strict": s.strict_mode,
        "validation_result": s.validation_result,
        "reasons": list(s.validation_reasons or []),
        "length": char_count(s.title),
        "match_ratio": s.match_ratio,
        "status": s.status,
        "plan_hash": s.plan_hash,
        "approval": {"approver": ap.approver, "approved_at": ap.approved_at, "expires_at": ap.expires_at} if ap is not None else None,
        "created_at": s.created_at,
    }


def change_dict(c: Change, video_title: str | None, rollbackable: bool, video_kind: str | None = None) -> dict:
    return {
        "id": c.id,
        "video_id": c.video_id,
        "video_title": video_title,
        "video_kind": video_kind,
        "change_type": c.change_type,
        "previous_title": c.previous_title,
        "new_title": c.new_title,
        "result": c.result,
        "mode": c.mode,
        "approver": c.approver,
        "applied_at": c.applied_at,
        "verified_at": c.verified_at,
        "error_code": c.error_code,
        "rollbackable": rollbackable,
        "batch_id": c.batch_id,
    }


def job_dict(j: Job) -> dict:
    return {"id": j.id, "type": j.type, "status": j.status, "progress": j.progress, "total": j.total, "error": j.error, "result": j.result}


def _failure_reason(it: BatchItem, change: Change | None) -> str | None:
    """반영 후 검증 실패는 저장된 검증 결과로 달라진 항목(길이 포함)을 풀어서 보여 준다. 옛 기록(항목 이름이 없던 때)도 같은 방식으로 풀린다."""
    if it.status == "failed" and (it.skip_reason or "").startswith("[verify_failed]") and change is not None and change.verify_result:
        names = describe_verify(change.verify_result, detail=True)
        if names:
            return f"[verify_failed] 반영은 됐지만 반영 전후 비교에서 달라진 항목: {names}. 이력에서 롤백을 검토하세요."
    return it.skip_reason


def _item_dicts(session: Session, items: list[BatchItem]) -> list[dict]:
    if not items:
        return []
    sugs = {s.id: s for s in session.execute(select(Suggestion).where(Suggestion.id.in_({i.suggestion_id for i in items}))).scalars()}
    vids = {v.video_id: v for v in session.execute(select(Video).where(Video.video_id.in_({i.video_id for i in items}))).scalars()}
    changes = {c.id: c for c in session.execute(select(Change).where(Change.id.in_({i.change_id for i in items if i.change_id}))).scalars()} if any(i.change_id for i in items) else {}
    out = []
    for it in items:
        sug, video, change = sugs.get(it.suggestion_id), vids.get(it.video_id), changes.get(it.change_id) if it.change_id else None
        out.append({
            "id": it.id,
            "suggestion_id": it.suggestion_id,
            "video_id": it.video_id,
            "video_kind": video_kind(video.is_short, video.duration_sec) if video else None,
            "video_title": video.title if video else None,
            "previous_title": change.previous_title if change else (video.title if video else ""),
            "new_title": change.new_title if change else (sug.title if sug else ""),
            "seq": it.seq,
            "scheduled_date": it.scheduled_date,
            "status": it.status,
            "skip_reason": _failure_reason(it, change),
            "change_id": it.change_id,
            "processed_at": it.updated_at if it.status in ("success", "failed", "skipped", "cancelled") else None,
        })
    return out


def kind_counts_for(session: Session, batches: list[Batch]) -> dict[int, dict[str, int]]:
    """배치별 롱폼/쇼츠/불명 개수. 영상 정보는 전체 배치를 한 번에 조회한다(N+1 방지)."""
    out = {b.id: {"long": 0, "short": 0, "unknown": 0} for b in batches}
    if not batches:
        return out
    rows = session.execute(select(BatchItem.batch_id, Video.is_short, Video.duration_sec).select_from(BatchItem).outerjoin(Video, Video.video_id == BatchItem.video_id).where(BatchItem.batch_id.in_(list(out)))).all()
    for bid, is_short, dur in rows:
        out[bid][video_kind(is_short, dur) or "unknown"] += 1
    return out


def batch_dict(session: Session, b: Batch, *, with_items: bool = True, kind_counts: dict[str, int] | None = None) -> dict:
    counts = {k: 0 for k in ("pending", "running", "success", "failed", "skipped", "cancelled")}
    for it in b.items:
        counts[it.status] += 1
    return {
        "id": b.id,
        "status": b.status,
        "note": b.note,
        "created_at": b.created_at,
        "executed_at": b.executed_at,
        "counts": counts,
        "kind_counts": kind_counts if kind_counts is not None else kind_counts_for(session, [b])[b.id],
        "items": _item_dicts(session, list(b.items)) if with_items else [],
        "precheck": b.precheck if with_items else None,  # 생성 시 저장한 사전 점검(새로고침 후 복구용)
    }
