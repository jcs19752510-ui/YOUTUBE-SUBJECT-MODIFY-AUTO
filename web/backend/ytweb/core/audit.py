"""추가 전용 감사 로그 + 해시 체인: hash = sha256(prev_hash + canonical_json(ts,actor,action,target,detail))."""
from __future__ import annotations

import math
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ytweb.core.canonical import canonical_json, sha256_hex
from ytweb.db.models import AuditLog

GENESIS_HASH = "0" * 64
_ADVISORY_LOCK_KEY = 7_340_001  # 동시 기록 시 체인이 갈라지지 않게 PostgreSQL 트랜잭션 락으로 직렬화


def _ts_text(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat(timespec="microseconds")


def compute_hash(prev_hash: str, *, ts: datetime, actor: str, action: str, target_type: str | None, target_id: str | None, detail: dict) -> str:
    body = canonical_json(
        {
            "ts": _ts_text(ts),
            "actor": actor,
            "action": action,
            "target": {"type": target_type, "id": target_id},
            "detail": detail,
        }
    )
    return sha256_hex(prev_hash + body)


def _reject_floats(value: object) -> None:
    """JSONB 는 지수 표기 큰 수(1e22 -> 정수 표기)와 -0.0(-> 0.0)을 정규화해 읽은 값의 해시가 달라지므로, 이런 float 는 기록 전에 거부한다."""
    if isinstance(value, float) and ("e+" in repr(value) or (value == 0 and math.copysign(1.0, value) < 0)):
        raise ValueError("감사 detail 에는 지수 표기 큰 float·-0.0 을 넣을 수 없습니다(정수·문자열로 변환).")
    if isinstance(value, dict):
        for v in value.values():
            _reject_floats(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _reject_floats(v)


def record(
    session: Session,
    *,
    actor: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
    now: datetime,
) -> AuditLog:
    if now.tzinfo is None:
        raise ValueError("now 는 tz-aware 여야 합니다.")
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
    detail = detail or {}
    _reject_floats(detail)
    last = session.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
    prev = last or GENESIS_HASH
    digest = compute_hash(prev, ts=now, actor=actor, action=action, target_type=target_type, target_id=target_id, detail=detail)
    row = AuditLog(
        ts=now, actor=actor, action=action, target_type=target_type, target_id=target_id,
        detail=detail, prev_hash=prev, hash=digest,
    )
    session.add(row)
    session.flush()
    return row


def verify_chain(session: Session) -> bool:
    prev = GENESIS_HASH
    stmt = select(AuditLog).order_by(AuditLog.id.asc()).execution_options(yield_per=500)
    for row in session.execute(stmt).scalars():
        if row.prev_hash != prev:
            return False
        expected = compute_hash(
            prev, ts=row.ts, actor=row.actor, action=row.action,
            target_type=row.target_type, target_id=row.target_id, detail=row.detail,
        )
        if row.hash != expected:
            return False
        prev = row.hash
    return True
