"""settings_kv 읽기/쓰기. 쓰기 가능한 키 검증은 라우터(settings.py)가 맡는다."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session
from youtube_title.config import Settings

from ytweb.db.models import SettingKV

DEFAULT_DAILY_APPLY_CAP = 10
DEFAULT_SUGGESTIONS_PER_VIDEO = 3


def get_web_setting(session: Session, key: str, default: Any = None) -> Any:
    row = session.get(SettingKV, key)
    return default if row is None else row.value


def set_web_setting(session: Session, key: str, value: Any, *, now: datetime) -> None:
    row = session.get(SettingKV, key)
    if row is None:
        session.add(SettingKV(key=key, value=value, updated_at=now))
    else:
        row.value = value
        row.updated_at = now
    session.flush()


def delete_web_setting(session: Session, key: str) -> None:
    row = session.get(SettingKV, key)
    if row is not None:
        session.delete(row)
        session.flush()


def effective_daily_cap(session: Session, policy: Settings) -> int:
    value = get_web_setting(session, "daily_apply_cap", DEFAULT_DAILY_APPLY_CAP)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20:
        return DEFAULT_DAILY_APPLY_CAP
    return value
