"""감사 로그 조회(읽기 전용)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ytweb.core import audit as audit_core
from ytweb.core.deps import get_session, require_session
from ytweb.db.models import AuditLog

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("", dependencies=[Depends(require_session)])
def list_audit(
    page: int = Query(1, ge=1, le=1_000_000),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_session),
) -> dict:
    total = db.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    rows = db.execute(
        select(AuditLog).order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return {
        "items": [
            {"id": r.id, "ts": r.ts.isoformat(), "actor": r.actor, "action": r.action, "target_type": r.target_type,
             "target_id": r.target_id, "detail": r.detail, "prev_hash": r.prev_hash, "hash": r.hash}
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "chain_ok": audit_core.verify_chain(db),
    }
