"""조회 기간(날짜 from~to, 한국 시간 기준·양 끝 포함)을 UTC 시각 구간 [시작, 끝)으로 바꾼다(2026-10-14 선생님 지시)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ytweb.core.errors import ProblemError

KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")


def kst_range_utc(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    """date_from 00:00:00 KST 이상, date_to 다음날 00:00:00 KST 미만. 한쪽만 주어도 된다. 시작이 끝보다 뒤면 422."""
    if date_from and date_to and date_from > date_to:
        raise ProblemError(422, "date_range_invalid", "조회 기간이 잘못됐습니다.", detail="시작일이 종료일보다 뒤입니다.", hint="시작일을 종료일과 같거나 이전으로 바꾸세요.")
    start = datetime.combine(date_from, time.min, tzinfo=KST).astimezone(UTC) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=KST).astimezone(UTC) if date_to else None
    return start, end


def in_range(value: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    """값이 구간 안인가. 구간 제한이 없으면 항상 True(값이 없어도), 제한이 있는데 값이 없으면 False."""
    if start is None and end is None:
        return True
    if value is None:
        return False
    return (start is None or value >= start) and (end is None or value < end)
