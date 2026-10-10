"""쿠키 세션. 토큰 원문은 쿠키에만 있고 DB 에는 sha256 만 저장한다."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ytweb.db.models import SessionRow

COOKIE_NAME = "ytw_session"
COOKIE_PATH = "/api"
MAX_ACTIVE_SESSIONS = 20


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    csrf_token: str
    expires_at: datetime


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, *, now: datetime, ttl_hours: int) -> tuple[str, SessionInfo]:
    purge_expired(db, now=now)
    active = db.execute(select(SessionRow.id).order_by(SessionRow.created_at.desc())).scalars().all()
    for old in active[MAX_ACTIVE_SESSIONS - 1:]:
        db.execute(delete(SessionRow).where(SessionRow.id == old))
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    row = SessionRow(
        id=hash_token(token), csrf_token=csrf, created_at=now,
        expires_at=now + timedelta(hours=ttl_hours), last_seen=now,
    )
    db.add(row)
    db.flush()
    return token, SessionInfo(row.id, csrf, row.expires_at)


def lookup_session(db: Session, token: str | None, *, now: datetime) -> SessionInfo | None:
    if not token or len(token) > 128:
        return None
    row = db.get(SessionRow, hash_token(token))
    if row is None:
        return None
    if row.expires_at <= now:
        db.delete(row)
        db.flush()
        return None
    row.last_seen = now
    return SessionInfo(row.id, row.csrf_token, row.expires_at)


def delete_session(db: Session, session_id: str) -> None:
    db.execute(delete(SessionRow).where(SessionRow.id == session_id))
    db.flush()


def delete_other_sessions(db: Session, keep_id: str) -> None:
    db.execute(delete(SessionRow).where(SessionRow.id != keep_id))
    db.flush()


def purge_expired(db: Session, *, now: datetime) -> int:
    res = db.execute(delete(SessionRow).where(SessionRow.expires_at <= now))
    return res.rowcount or 0
