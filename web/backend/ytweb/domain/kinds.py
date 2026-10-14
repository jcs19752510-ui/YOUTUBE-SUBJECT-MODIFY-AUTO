"""영상 구분(롱폼/쇼츠): 쇼츠 = 영상의 is_short(길이가 쇼츠 기준 이하), 롱폼 = 길이를 알고 쇼츠 기준을 넘는 영상, 길이를 모르면 구분 없음(None)."""
from __future__ import annotations

from sqlalchemy import and_

from ytweb.db.models import Video


def video_kind(is_short: bool | None, duration_sec: int | None) -> str | None:
    if is_short:
        return "short"
    return "long" if duration_sec is not None else None


def kind_clause(kind: str):
    """Video 테이블 조건식(kind 는 'long' 또는 'short')."""
    if kind == "short":
        return Video.is_short.is_(True)
    return and_(Video.is_short.is_(False), Video.duration_sec.is_not(None))
