"""시간 기준: DB는 UTC, 일일 반영 건수는 KST 날짜, API 쿼터 기준일은 태평양 시간."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")
_PT = ZoneInfo("America/Los_Angeles")


def _aware(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("naive datetime 은 사용할 수 없습니다(tz-aware 필요).")
    return now


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def kst_today(now: datetime) -> date:
    return _aware(now).astimezone(_KST).date()


def pt_date(now: datetime) -> date:
    return _aware(now).astimezone(_PT).date()
