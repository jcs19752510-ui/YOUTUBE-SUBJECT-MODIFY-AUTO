from datetime import datetime, timedelta, timezone

import pytest

from ytitle.errors import ConfigError
from ytitle.timeutil import FixedClock, parse_date, parse_iso, pt_date, utc_iso


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_pt_date_boundary_in_winter_pst():
    """TC-029: 겨울(PST, UTC-8)에는 UTC 08:00에 쿼터 날짜가 바뀐다. [ADR-006, NFR-003]"""
    assert pt_date(utc(2026, 1, 15, 7, 59, 59)).isoformat() == "2026-01-14"
    assert pt_date(utc(2026, 1, 15, 8, 0, 0)).isoformat() == "2026-01-15"


def test_pt_date_boundary_in_summer_pdt():
    """TC-030: 여름(PDT, UTC-7)에는 UTC 07:00에 날짜가 바뀐다. [ADR-006]"""
    assert pt_date(utc(2026, 7, 15, 6, 59, 59)).isoformat() == "2026-07-14"
    assert pt_date(utc(2026, 7, 15, 7, 0, 0)).isoformat() == "2026-07-15"


def test_pt_date_around_dst_switch():
    """TC-031: 서머타임 시작일(2026-03-08) 전후로 날짜 경계가 올바르다. [ADR-006]"""
    assert pt_date(utc(2026, 3, 8, 7, 59, 59)).isoformat() == "2026-03-07"
    assert pt_date(utc(2026, 3, 8, 8, 0, 0)).isoformat() == "2026-03-08"
    assert pt_date(utc(2026, 3, 9, 6, 59, 59)).isoformat() == "2026-03-08"
    assert pt_date(utc(2026, 3, 9, 7, 0, 0)).isoformat() == "2026-03-09"


def test_iso_roundtrip_and_fixed_clock():
    """TC-032: UTC ISO 문자열 변환이 왕복되고, 고정 시계는 시각을 앞으로 보낼 수 있다. [NFR-008]"""
    t = utc(2026, 10, 10, 12, 30, 5)
    assert parse_iso(utc_iso(t)) == t
    c = FixedClock(t)
    c.advance(timedelta(hours=72))
    assert c.now() == utc(2026, 10, 13, 12, 30, 5)
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 1, 1))


def test_parse_date_errors_are_korean():
    """TC-033: 날짜 형식이 틀리면 형식 예시와 함께 ConfigError가 난다. [NFR-007]"""
    assert parse_date("2026-01-31").isoformat() == "2026-01-31"
    for bad in ("2026/01/31", "31-01-2026", "2026-13-01", ""):
        with pytest.raises(ConfigError) as ei:
            parse_date(bad)
        assert "YYYY-MM-DD" in ei.value.next_step
