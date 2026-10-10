"""ORM → API 응답 딕셔너리(WEB_DESIGN §3 스키마). 응답 모델 검증은 schemas.py 가 맡는다."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from ytitle.textsafe import char_count

from ytweb.db.models import Batch, BatchItem, Change, Job, Suggestion, Video


def suggestion_dict(s: Suggestion) -> dict:
    ap = s.approval
    return {
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


def change_dict(c: Change, video_title: str | None, rollbackable: bool) -> dict:
    return {
        "id": c.id,
        "video_id": c.video_id,
        "video_title": video_title,
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
            "video_title": video.title if video else None,
            "previous_title": change.previous_title if change else (video.title if video else ""),
            "new_title": change.new_title if change else (sug.title if sug else ""),
            "seq": it.seq,
            "scheduled_date": it.scheduled_date,
            "status": it.status,
            "skip_reason": it.skip_reason,
            "change_id": it.change_id,
        })
    return out


def batch_dict(session: Session, b: Batch, *, with_items: bool = True) -> dict:
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
        "items": _item_dicts(session, list(b.items)) if with_items else [],
    }
