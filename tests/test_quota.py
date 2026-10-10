from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from ytitle import db
from ytitle.config import load_settings
from ytitle.errors import InputError, QuotaError
from ytitle.quota import QuotaManager
from ytitle.timeutil import FixedClock


def make(project, clock, **overrides):
    settings = replace(load_settings(project, env={}), **overrides)
    conn = db.connect(":memory:")
    db.migrate(conn)
    return QuotaManager(conn, settings, clock), conn


def rows(conn):
    return [tuple(r) for r in conn.execute("SELECT pt_date, method, units, status, run_id FROM quota_usage ORDER BY id")]


def test_reserve_records_before_call_and_counts_reserved(project, clock):
    """TC-200: 예약하면 호출 전에 reserved 행이 남고, 아직 결과 표시가 없어도 오늘 사용량에 포함된다. [FR-015, SEC-002]"""
    q, conn = make(project, clock)
    rid = q.reserve("videos.list", 3, "run1")
    assert isinstance(rid, int)
    assert rows(conn) == [("2026-10-10", "videos.list", 3, "reserved", "run1")]
    assert q.used_today() == 3 and q.remaining() == q.limit - 3


def test_limit_boundary_exact_allowed_then_rejected_without_db_change(project, clock):
    """TC-201: 상한 직전(남은 1)까지는 예약되고, 상한을 채운 뒤의 1 units는 QuotaError이며 DB는 그대로다. [SEC-002, NFR-003, FR-015]"""
    q, conn = make(project, clock, daily_limit_units=10)
    q.reserve("a", 9, None)
    q.reserve("b", 1, None)
    assert q.used_today() == 10 and q.remaining() == 0
    before = rows(conn)
    with pytest.raises(QuotaError) as ei:
        q.reserve("c", 1, None)
    assert ei.value.code == "YT-300"
    assert rows(conn) == before and len(before) == 2


def test_single_reserve_over_limit_rejected_with_reset_guidance(project, clock):
    """TC-202: 남은 양보다 큰 예약은 거부되고 DB에 흔적이 없으며, 태평양 자정·한국 시간 초기화 안내가 나온다. [SEC-002, FR-015, NFR-007]"""
    q, conn = make(project, clock, daily_limit_units=100)
    q.reserve("a", 60, None)
    before = rows(conn)
    with pytest.raises(QuotaError) as ei:
        q.reserve("videos.update", 50, "r")
    err = ei.value
    assert rows(conn) == before
    assert "60" in err.message and "50" in err.message and "100" in err.message
    assert "태평양" in err.next_step and "자정" in err.next_step and "오후 4시" in err.next_step and "오후 5시" in err.next_step
    assert q.used_today() == 60


def test_zero_limit_rejects_everything(project, clock):
    """TC-203: 상한이 0이면 어떤 예약도 거부된다(남은 양은 음수가 되지 않는다). [SEC-002, NFR-003]"""
    q, conn = make(project, clock, daily_limit_units=0)
    with pytest.raises(QuotaError):
        q.reserve("x", 1, None)
    assert rows(conn) == [] and q.remaining() == 0


def test_failed_call_keeps_units_charged(project, clock):
    """TC-204: 호출이 실패(failed)로 표시돼도 units 차감은 유지되고, ok와 failed가 각각 기록된다. [ADR-008, FR-015, SEC-002]"""
    q, conn = make(project, clock, daily_limit_units=100)
    a = q.reserve("a", 5, None)
    b = q.reserve("b", 7, None)
    q.mark(a, "ok")
    q.mark(b, "failed")
    assert [r[3] for r in rows(conn)] == ["ok", "failed"]
    assert q.used_today() == 12 and q.remaining() == 88


def test_mark_rejects_bad_status_unknown_id_and_double_mark(project, clock):
    """TC-205: mark는 잘못된 상태·없는 ID·이미 처리된 예약을 거부하고 기록을 바꾸지 않는다. [FR-015]"""
    q, conn = make(project, clock)
    rid = q.reserve("a", 1, None)
    with pytest.raises(ValueError):
        q.mark(rid, "reserved")
    with pytest.raises(ValueError):
        q.mark(rid, "done")
    with pytest.raises(ValueError):
        q.mark(9999, "ok")
    assert rows(conn)[0][3] == "reserved"
    q.mark(rid, "failed")
    with pytest.raises(ValueError):
        q.mark(rid, "ok")
    assert rows(conn)[0][3] == "failed"


@pytest.mark.parametrize("method,units", [("x", 0), ("x", -5), ("", 1), ("   ", 1), ("x", True), ("x", 1.5), ("x", "3"), (None, 1)])
def test_invalid_method_or_units_rejected(project, clock, method, units):
    """TC-206: units가 0 이하·정수 아님이거나 호출 이름이 비어 있으면 InputError이고 DB에 남기지 않는다. [SEC-002, FR-015]"""
    q, conn = make(project, clock)
    with pytest.raises(InputError) as ei:
        q.reserve(method, units, None)
    assert ei.value.code == "YT-500"
    assert rows(conn) == []


@pytest.mark.parametrize(
    "utc_moment,expected",
    [
        (datetime(2026, 3, 8, 7, 59, 59, tzinfo=timezone.utc), "2026-03-07"),  # 서머타임 시작일 직전: PST 23:59:59
        (datetime(2026, 3, 8, 8, 0, 0, tzinfo=timezone.utc), "2026-03-08"),  # PST 자정
        (datetime(2026, 3, 9, 6, 59, 59, tzinfo=timezone.utc), "2026-03-08"),  # 서머타임 적용 후 PDT 23:59:59
        (datetime(2026, 3, 9, 7, 0, 0, tzinfo=timezone.utc), "2026-03-09"),  # PDT 자정
        (datetime(2026, 11, 2, 7, 59, 59, tzinfo=timezone.utc), "2026-11-01"),  # 서머타임 종료일: PST 23:59:59
        (datetime(2026, 11, 2, 8, 0, 0, tzinfo=timezone.utc), "2026-11-02"),
        (datetime(2026, 10, 10, 6, 59, 59, tzinfo=timezone.utc), "2026-10-09"),  # 한국 시간 10일 15:59는 아직 태평양 9일
    ],
)
def test_pt_date_boundary_stored_on_reserve(project, utc_moment, expected):
    """TC-207: 예약 행의 pt_date가 태평양 시간 날짜이며 서머타임 전후 경계에서도 맞다(UTC 날짜가 아님). [NFR-003, FR-015, SEC-002]"""
    q, conn = make(project, FixedClock(utc_moment))
    q.reserve("a", 1, None)
    assert rows(conn)[0][0] == expected
    assert q.today() == expected


@pytest.mark.parametrize("start", [datetime(2026, 3, 9, 6, 59, 0, tzinfo=timezone.utc), datetime(2026, 11, 2, 7, 59, 0, tzinfo=timezone.utc), datetime(2026, 10, 10, 6, 59, 0, tzinfo=timezone.utc)])
def test_usage_separated_by_pt_day(project, start):
    """TC-208: 태평양 자정을 넘기면 어제 사용량은 오늘 집계에서 빠지고 다시 전체 한도를 쓸 수 있다(날짜별 분리). [NFR-003, FR-015]"""
    clk = FixedClock(start)
    q, conn = make(project, clk, daily_limit_units=10)
    q.reserve("a", 10, None)
    with pytest.raises(QuotaError):
        q.reserve("b", 1, None)
    clk.advance(timedelta(minutes=2))
    assert q.used_today() == 0 and q.remaining() == 10
    q.reserve("c", 4, None)
    days = [r[0] for r in rows(conn)]
    assert days[0] != days[1] and q.used_today() == 4
    clk.advance(timedelta(hours=-1))
    assert q.used_today() == 10


def test_warning_threshold_at_80_percent(project, clock):
    """TC-209: 사용량이 상한의 80% 미만이면 경고가 없고 정확히 80%가 되면 경고를 알린다. [NFR-003, FR-015]"""
    q, _ = make(project, clock, daily_limit_units=100, warn_ratio=0.8)
    q.reserve("a", 79, None)
    assert q.is_warning() is False
    q.reserve("b", 1, None)
    assert q.is_warning() is True
    q.reserve("c", 20, None)
    assert q.is_warning() is True and q.remaining() == 0


def test_warn_ratio_follows_settings(project, clock):
    """TC-210: 경고 비율은 설정값을 따른다(0.5이면 50%에서 경고). [NFR-003]"""
    q, _ = make(project, clock, daily_limit_units=10, warn_ratio=0.5)
    q.reserve("a", 4, None)
    assert q.is_warning() is False
    q.reserve("b", 1, None)
    assert q.is_warning() is True


def test_sql_injection_in_method_is_stored_as_value(project, clock):
    """TC-211: 호출 이름·실행 ID에 SQL 조각이 있어도 값으로만 저장되고 테이블은 멀쩡하다. [SEC-018]"""
    q, conn = make(project, clock)
    evil = "x'); DROP TABLE quota_usage;--"
    q.reserve(evil, 1, evil)
    assert rows(conn) == [("2026-10-10", evil, 1, "reserved", evil)]
    q.mark(1, "ok")
    assert q.used_today() == 1


def test_used_today_counts_all_statuses(project, clock):
    """TC-212: reserved·ok·failed 모두 합산하고 다른 날짜 행은 합산하지 않는다. [FR-015, SEC-002]"""
    q, conn = make(project, clock, daily_limit_units=1000)
    for status, units in (("reserved", 1), ("ok", 2), ("failed", 4)):
        conn.execute("INSERT INTO quota_usage (pt_date, method, units, called_at, run_id, status) VALUES (?,?,?,?,?,?)", ("2026-10-10", "m", units, "2026-10-10T12:00:00Z", None, status))
    conn.execute("INSERT INTO quota_usage (pt_date, method, units, called_at, run_id, status) VALUES ('2026-10-09','m',100,'2026-10-09T12:00:00Z',NULL,'ok')")
    conn.commit()
    assert q.used_today() == 7


def test_database_failure_becomes_database_error(project, clock):
    """TC-213: quota_usage 테이블을 읽거나 쓰지 못하면 한국어 DatabaseError(YT-200)이다. [FR-015, NFR-007]"""
    from ytitle.errors import DatabaseError

    q, conn = make(project, clock)
    rid = q.reserve("a", 1, None)
    conn.execute("DROP TABLE quota_usage")
    for call in (q.used_today, lambda: q.reserve("a", 1, None), lambda: q.mark(rid, "ok")):
        with pytest.raises(DatabaseError) as ei:
            call()
        assert ei.value.code == "YT-200" and ei.value.next_step


def test_remaining_never_negative_when_limit_lowered(project, clock):
    """TC-214: 사용량이 쓰인 뒤 상한 설정을 낮춰 사용량이 상한을 넘어도 남은 양은 0이고 새 예약은 거부된다. [FR-015, SEC-002]"""
    q, conn = make(project, clock, daily_limit_units=100)
    q.reserve("a", 80, None)
    q2 = QuotaManager(conn, replace(q._settings, daily_limit_units=50), clock)
    assert q2.used_today() == 80 and q2.remaining() == 0
    with pytest.raises(QuotaError):
        q2.reserve("b", 1, None)
