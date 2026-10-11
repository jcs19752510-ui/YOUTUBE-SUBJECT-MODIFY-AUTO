"""시간 처리. 쿼터의 '하루'는 태평양 시간 기준이다(ADR-006)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from youtube_title.errors import ConfigError


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    def __init__(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("시각에는 시간대가 필요합니다")
        self._moment = moment.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._moment

    def advance(self, delta) -> None:
        self._moment = self._moment + delta


def utc_iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def pt_zone():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/Los_Angeles")
    except Exception as exc:  # tzdata 미설치 등
        raise ConfigError(
            "태평양 시간대 정보를 찾을 수 없습니다.",
            "가상환경이 켜진 상태에서 `pip install tzdata`를 실행하세요.",
            cause=type(exc).__name__,
        ) from exc


def pt_date(moment: datetime) -> date:
    """쿼터 집계용 태평양 시간 날짜."""
    return moment.astimezone(pt_zone()).date()


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ConfigError(f"날짜 형식이 올바르지 않습니다: {value}", "YYYY-MM-DD 형식으로 입력하세요. 예: 2026-01-31") from exc
