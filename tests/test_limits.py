from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from wu4_support import NOW, VID, add_change, add_metric, make_settings, open_db

from ytitle.errors import DatabaseError
from ytitle.limits import COUNT, DAILY, IMPRESSIONS, INTERVAL, LimitFacts, _pt_day_bounds, check_limits, evaluate_limits, format_kst, gather_facts

NEXT_DAY = datetime(2026, 10, 11, 7, 0, tzinfo=timezone.utc)


@pytest.fixture
def s(project):
    return make_settings(project)


@pytest.fixture
def conn(tmp_path):
    c = open_db(tmp_path / "t.sqlite3")
    yield c
    c.close()


def facts(last=None, count=0, imp=None, today=0):
    return LimitFacts(last, count, imp, today, NEXT_DAY)


def by_code(report):
    return {c.code: c for c in report.checks}


def test_interval_boundary_72_hours(s):
    """TC-400: 직전 변경 후 정확히 72시간이면 통과, 1초 모자라면 차단되고 가능한 시각을 알려 준다. [FR-014, SEC-004]"""
    ok = evaluate_limits(facts(NOW - timedelta(hours=72), 1, 1000), s, NOW)
    assert by_code(ok)[INTERVAL].passed
    early = by_code(evaluate_limits(facts(NOW - timedelta(hours=72) + timedelta(seconds=1), 1, 1000), s, NOW))[INTERVAL]
    assert not early.passed and early.retry_at == NOW + timedelta(seconds=1) and "(한국 시간)" in early.message


def test_interval_uses_configured_hours(s):
    """TC-401: 간격은 설정값(cadence.min_interval_hours)을 따른다. [FR-014, 설계 5-3]"""
    s2 = replace(s, min_interval_hours=1)
    assert by_code(evaluate_limits(facts(NOW - timedelta(hours=1), 1, 5000), s2, NOW))[INTERVAL].passed
    assert not by_code(evaluate_limits(facts(NOW - timedelta(minutes=59), 1, 5000), s2, NOW))[INTERVAL].passed


def test_first_change_has_no_history_limits(s):
    """TC-402: 한 번도 바꾸지 않은 영상은 간격·횟수·노출수 조건에 걸리지 않는다. [FR-014]"""
    r = evaluate_limits(facts(), s, NOW)
    assert r.passed and r.failures == () and len(r.checks) == 4


def test_count_boundary_three_changes(s):
    """TC-403: 변경 2회까지는 통과, 이미 3회면 차단되며 시간이 지나도 풀리지 않는다(재시도 시각 없음). [FR-014, SEC-004]"""
    old = NOW - timedelta(days=30)
    assert by_code(evaluate_limits(facts(old, 2, 5000), s, NOW))[COUNT].passed
    c = by_code(evaluate_limits(facts(old, 3, 5000), s, NOW))[COUNT]
    assert not c.passed and c.retry_at is None and "3회" in c.message
    assert not by_code(evaluate_limits(facts(old, 4, 5000), s, NOW))[COUNT].passed


def test_count_uses_configured_cap(s):
    """TC-404: 횟수 상한은 설정값을 따른다. [FR-014]"""
    s2 = replace(s, max_changes_per_video=1)
    assert not by_code(evaluate_limits(facts(NOW - timedelta(days=30), 1, 5000), s2, NOW))[COUNT].passed


def test_impressions_boundary_1000(s):
    """TC-405: 재변경 시 변경 이후 노출수 999는 차단, 1000은 통과한다. [FR-014, SEC-004]"""
    old = NOW - timedelta(days=30)
    assert not by_code(evaluate_limits(facts(old, 1, 999), s, NOW))[IMPRESSIONS].passed
    assert by_code(evaluate_limits(facts(old, 1, 1000), s, NOW))[IMPRESSIONS].passed


def test_unknown_impressions_rejected_with_reason(s):
    """TC-406: 노출수를 모르면(기록 없음·API 미제공) 안전을 위해 거부하고 지표를 가져오는 방법을 안내한다. [FR-014, FR-007]"""
    c = by_code(evaluate_limits(facts(NOW - timedelta(days=30), 1, None), s, NOW))[IMPRESSIONS]
    assert not c.passed and "안전을 위해 거부" in c.message and "fetch --metrics" in c.message and "CSV" in c.message


def test_zero_threshold_disables_impressions_check(s):
    """TC-407: 최소 노출수를 0으로 설정하면 노출수를 몰라도 통과한다(조건 끔). [FR-014, 설계 5-3]"""
    s0 = replace(s, min_impressions_before_rechange=0)
    assert by_code(evaluate_limits(facts(NOW - timedelta(days=30), 1, None), s0, NOW))[IMPRESSIONS].passed


def test_daily_cap_boundary(s):
    """TC-408: 오늘 적용 2건까지는 통과, 3건이면 차단되고 다음 태평양 자정이 가능 시각이다. [SEC-020, 설계 5-3]"""
    assert by_code(evaluate_limits(facts(today=2), s, NOW))[DAILY].passed
    d = by_code(evaluate_limits(facts(today=3), s, NOW))[DAILY]
    assert not d.passed and d.retry_at == NEXT_DAY and "2026-10-11 16:00" in d.message


def test_report_fails_if_any_check_fails(s):
    """TC-409: 하나라도 실패하면 보고서 전체가 실패이고 실패 항목만 failures에 나온다. [FR-014]"""
    r = evaluate_limits(facts(NOW - timedelta(hours=1), 1, 5000, today=0), s, NOW)
    assert not r.passed and [c.code for c in r.failures] == [INTERVAL]


def test_format_kst():
    """TC-410: 사용자 화면의 시각은 한국 시간(UTC+9)으로 표시한다. [UX 설계 3장]"""
    assert format_kst(datetime(2026, 10, 10, 15, 30, tzinfo=timezone.utc)) == "2026-10-11 00:30 (한국 시간)"


def test_gather_counts_success_and_planned_only(conn, s):
    """TC-411: 변경 횟수는 success·planned(미확정)만 세고 failed·aborted·다른 영상은 세지 않는다. [FR-014, SEC-004]"""
    for res in ("success", "planned", "failed", "aborted"):
        add_change(conn, result=res, at=NOW - timedelta(days=10))
    add_change(conn, "zzzzzzzzzzz", at=NOW - timedelta(days=10))
    f = gather_facts(conn, VID, NOW)
    assert f.change_count == 2


def test_gather_last_change_time_uses_latest(conn):
    """TC-412: 직전 변경 시각은 가장 최근 행(applied_at, 없으면 created_at)이다. [FR-014]"""
    add_change(conn, at=NOW - timedelta(days=9))
    add_change(conn, at=NOW - timedelta(days=5))
    add_change(conn, result="planned", at=NOW - timedelta(days=7))
    f = gather_facts(conn, VID, NOW)
    assert f.last_change_at == NOW - timedelta(days=5)
    assert gather_facts(conn, "zzzzzzzzzzz", NOW).last_change_at is None


def test_gather_impressions_only_after_change(conn):
    """TC-413: 노출수는 변경 '이후에 시작하는' after/periodic 기간만 인정한다(이전·같은 날 시작·before 단계·NULL·CSV 시작일 없음 제외, 최댓값 사용). [FR-014]"""
    change_at = NOW - timedelta(days=10)          # 2026-09-30 12:00Z
    add_change(conn, at=change_at)
    add_metric(conn, impressions=9000, period_start="2026-09-29")                 # 변경 전에 시작: 제외
    add_metric(conn, impressions=9001, period_start="2026-09-30")                 # 변경과 같은 날 시작: 제외(보수적)
    add_metric(conn, impressions=9002, period_start="2026-10-01", phase="before")  # 단계 before: 제외
    add_metric(conn, impressions=9003, period_start="2026-10-02", taken_at=change_at - timedelta(days=1))  # 변경 전에 가져온 값: 제외
    add_metric(conn, impressions=None, period_start="2026-10-02")                  # 노출수 NULL: 제외
    add_metric(conn, impressions=777, period_start="2026-10-01")
    add_metric(conn, impressions=1234, period_start="2026-10-02", phase="periodic")
    conn.execute("INSERT INTO metrics_snapshots (video_id,taken_at,phase,source,impressions) VALUES (?,?,?,?,?)", (VID, NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "after", "csv", 99999))
    conn.commit()
    assert gather_facts(conn, VID, NOW).impressions_since_change == 1234


def test_gather_impressions_none_when_no_usable_metrics(conn, s):
    """TC-414: 쓸 수 있는 지표가 하나도 없으면 None이고, 재변경은 거부된다. [FR-014]"""
    add_change(conn, at=NOW - timedelta(days=10))
    add_metric(conn, impressions=5000, period_start="2026-09-01")
    f = gather_facts(conn, VID, NOW)
    assert f.impressions_since_change is None and not evaluate_limits(f, s, NOW).passed


def test_daily_count_pt_day_boundary(conn):
    """TC-415: '하루'는 태평양 시간 날짜다: PT 자정(UTC 07:00) 직전 변경은 어제, 정각 변경은 오늘이다. 롤백 행은 세지 않는다. [SEC-020, ADR-006]"""
    add_change(conn, "aaaaaaaaaaa", at=datetime(2026, 10, 10, 6, 59, 59, tzinfo=timezone.utc))   # 어제(PT 10-09 23:59:59)
    add_change(conn, "bbbbbbbbbbb", at=datetime(2026, 10, 10, 7, 0, 0, tzinfo=timezone.utc))     # 오늘 첫 순간
    add_change(conn, "ccccccccccc", at=NOW)
    add_change(conn, "ddddddddddd", change_type="rollback", at=NOW)
    add_change(conn, "eeeeeeeeeee", result="failed", at=NOW)
    assert gather_facts(conn, VID, NOW).changes_today == 2
    assert gather_facts(conn, VID, NOW).next_day_start == NEXT_DAY


def test_pt_day_bounds_dst_fall_back():
    """TC-416: 서머타임이 끝나는 날(2026-11-01)은 25시간이고 경계가 정확하다. [ADR-006, NFR-003]"""
    start, end = _pt_day_bounds(datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc))
    assert start == datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc) and end == datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)


def test_bad_timestamp_in_history_fails_closed(conn):
    """TC-417: 이력의 시각 형식이 깨져 있으면 추측하지 않고 DatabaseError로 거부한다. [FR-014, NFR-007]"""
    add_change(conn, at=NOW)
    conn.execute("UPDATE title_changes SET applied_at = 'garbage'")
    conn.commit()
    with pytest.raises(DatabaseError):
        gather_facts(conn, VID, NOW)


def test_sql_injection_in_video_id_is_inert(conn):
    """TC-418: 영상 ID에 SQL 조각이 있어도 값으로만 쓰여 다른 행을 건드리지 않고 테이블이 유지된다. [SEC-018, T-12]"""
    add_change(conn, at=NOW - timedelta(days=1))
    f = gather_facts(conn, "x' OR '1'='1'; DROP TABLE title_changes;--", NOW)
    assert f.change_count == 0 and f.last_change_at is None
    assert conn.execute("SELECT COUNT(*) FROM title_changes").fetchone()[0] == 1


def test_check_limits_end_to_end_and_read_only(conn, s):
    """TC-419: DB 이력으로 4가지를 함께 판정하고, 판정 중 DB를 전혀 바꾸지 않는다. [FR-014, SEC-004, SEC-006]"""
    for d in (30, 20, 10):
        add_change(conn, at=NOW - timedelta(days=d))
    before = conn.total_changes
    r = check_limits(conn, s, VID, NOW)
    assert [c.code for c in r.failures] == [COUNT, IMPRESSIONS]
    assert conn.total_changes == before and not conn.in_transaction


def test_db_error_becomes_database_error(conn, s):
    """TC-420: 이력 테이블을 읽을 수 없으면 DatabaseError(한국어 안내)로 변환한다. [NFR-007]"""
    conn.execute("DROP TABLE title_changes")
    with pytest.raises(DatabaseError) as exc:
        check_limits(conn, s, VID, NOW)
    assert "이력" in exc.value.message and exc.value.next_step


def test_daily_count_when_utc_and_pt_dates_differ(conn):
    """TC-456: UTC 날짜와 태평양 날짜가 다른 시각(UTC 10-10 03:00 = PT 10-09 20:00)에도 '하루'는 PT 기준(10-09 07:00Z ~ 10-10 07:00Z)으로 센다. [SEC-020, ADR-006]"""
    now = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)
    add_change(conn, "aaaaaaaaaaa", at=datetime(2026, 10, 9, 6, 59, 59, tzinfo=timezone.utc))   # 어제(PT 10-08): 제외
    add_change(conn, "bbbbbbbbbbb", at=datetime(2026, 10, 9, 7, 0, 0, tzinfo=timezone.utc))     # PT 10-09 시작: 포함
    add_change(conn, "ccccccccccc", at=datetime(2026, 10, 10, 2, 0, 0, tzinfo=timezone.utc))    # 포함(UTC로는 10-10)
    add_change(conn, "ddddddddddd", at=datetime(2026, 10, 10, 7, 0, 0, tzinfo=timezone.utc))    # 다음 PT 날: 제외
    f = gather_facts(conn, VID, now)
    assert f.changes_today == 2 and f.next_day_start == datetime(2026, 10, 10, 7, 0, tzinfo=timezone.utc)
