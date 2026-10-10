import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ytitle import db
from ytitle import report as rp
from ytitle.report import Change, Rules, Snapshot, build_report

RULES = Rules(min_impressions=1000, min_period_days=7, evaluation_window_days=14)
APPLIED = "2026-09-01T03:00:00Z"  # 변경 시각(UTC), 날짜 2026-09-01
VID = "abc123DEF45"


def snap(id=1, phase="before", start="2026-08-04", end="2026-08-31", imp=28000, ctr=3.0, views=2800, wm=5600.0, taken="2026-09-01T02:00:00Z", source="api"):
    return Snapshot(id, taken, phase, source, start, end, imp, ctr, views, wm)


def after(id=2, **kw):
    base = dict(phase="after", start="2026-09-02", end="2026-09-29", imp=56000, ctr=4.5, views=5600, wm=11200.0, taken="2026-09-30T02:00:00Z")
    base.update(kw)
    return snap(id, **base)


def chg(id=1, type="apply", at=APPLIED, result="success"):
    return Change(id, type, "이전 제목", "새 제목", at, result, "me")


def rep(snaps, changes=None, rules=RULES):
    return build_report(VID, "제목", [chg()] if changes is None else changes, snaps, rules)


def test_sufficient_data_compares_per_day_rates():
    """TC-630: 자료가 충분하면 하루 평균(노출·조회·시청 시간)과 클릭률의 전후 차이·변화율을 계산한다. [FR-018, SCR-008]"""
    r = rep([snap(), after()])
    assert r.status == "ok" and r.reasons == () and r.baseline_missing is False and r.expected_after_date is None
    m = {x.key: x for x in r.metrics}
    assert (m["impressions"].before, m["impressions"].after, m["impressions"].delta, m["impressions"].pct) == (1000.0, 2000.0, 1000.0, 100.0)
    assert (m["ctr"].before, m["ctr"].after, m["ctr"].delta, m["ctr"].pct) == (3.0, 4.5, 1.5, 50.0)
    assert (m["views"].before, m["views"].after) == (100.0, 200.0) and (m["watch_minutes"].before, m["watch_minutes"].after) == (200.0, 400.0)


def test_different_period_lengths_are_normalized_per_day():
    """TC-631: 전·후 집계 기간 길이가 달라도 하루 평균으로 비교한다(합계 직접 비교 금지). [FR-018]"""
    r = rep([snap(imp=14000, start="2026-08-18"), after(imp=14000, end="2026-09-15")])  # 14일 vs 14일(같은 총합이지만 아래서 달라짐)
    m = {x.key: x for x in r.metrics}
    assert m["impressions"].before == 1000.0 and m["impressions"].after == 1000.0 and m["impressions"].pct == 0.0
    r2 = rep([snap(imp=14000, start="2026-08-18"), after(imp=14000)])  # 14일 vs 28일
    assert {x.key: x for x in r2.metrics}["impressions"].after == 500.0


@pytest.mark.parametrize(
    "imp,ok",
    [(999, False), (1000, True), (1001, True), (0, False)],
)
def test_min_impressions_boundary_both_sides(imp, ok):
    """TC-632: 노출수 최소 기준(1,000) 경계: 999 미달, 1,000 충족. 변경 전·후 각각 적용한다. [FR-018, 경계값]"""
    b = rep([snap(imp=imp, start="2026-08-25"), after(imp=50000)])
    a = rep([snap(imp=50000), after(imp=imp, end="2026-09-08")])
    assert (b.status == "ok") is ok and (a.status == "ok") is ok
    if not ok:
        assert any("노출수" in x and "최소 기준 1,000회" in x for x in b.reasons) and any("변경 후 노출수" in x for x in a.reasons)
        assert b.metrics == () and a.metrics == ()


@pytest.mark.parametrize("bstart,aend,ok", [("2026-08-26", "2026-09-07", False), ("2026-08-25", "2026-09-08", True), ("2026-08-24", "2026-09-09", True)])
def test_min_period_days_boundary(bstart, aend, ok):
    """TC-633: 집계 기간 최소 7일 경계: 6일 부족, 7일 충족(양끝 포함 계산). 변경 전·후 각각 적용한다. [FR-018, 경계값]"""
    b = rep([snap(start=bstart), after()])
    a = rep([snap(), after(end=aend)])
    assert (b.status == "ok") is ok and (a.status == "ok") is ok
    if not ok:
        assert any("변경 전 집계 기간 6일" in x and "7일" in x for x in b.reasons) and any("변경 후 집계 기간 6일" in x for x in a.reasons)


def test_missing_baseline_is_insufficient_not_a_conclusion():
    """TC-634: 변경 전 지표(기준선)가 없으면 '데이터 부족'이며 비교 수치를 만들지 않고 신뢰도 낮음 표시를 켠다. [FR-012, FR-018, SCR-008]"""
    r = rep([after()])
    assert r.status == "insufficient" and r.baseline_missing is True and r.metrics == () and r.before is None
    assert "변경 전 지표(기준선)가 없습니다." in r.reasons and r.expected_after_date is None


def test_missing_after_gives_expected_collection_date():
    """TC-635: 변경 후 지표가 없으면 데이터 부족이며 수집 예정일(변경일 + 평가 기간)을 알려 준다. [SCR-008, FR-019]"""
    r = rep([snap()])
    assert r.status == "insufficient" and r.baseline_missing is False and r.metrics == ()
    assert r.reasons == ("변경 후 지표가 아직 없습니다.",) and r.expected_after_date == "2026-09-15"
    r2 = rep([snap()], rules=replace(RULES, evaluation_window_days=1))
    assert r2.expected_after_date == "2026-09-02"


def test_no_snapshots_at_all_collects_both_reasons():
    """TC-636: 지표가 하나도 없으면 사유를 한 번에 모두 알린다(기준선 없음 + 변경 후 없음). [규칙 B, SCR-008]"""
    r = rep([])
    assert r.status == "insufficient" and len(r.reasons) == 2 and r.baseline_missing is True and r.expected_after_date == "2026-09-15"


@pytest.mark.parametrize("end,ok", [("2026-08-31", True), ("2026-09-01", False), ("2026-09-02", False)])
def test_before_period_must_end_before_change_day(end, ok):
    """TC-637: 변경 전 자료의 집계 종료일은 변경일보다 앞서야 한다(당일분 제외). 겹치면 기준선으로 쓰지 않는다. [FR-018, 경계값]"""
    r = rep([snap(end=end, start="2026-08-01"), after()])
    assert (r.status == "ok") is ok
    if not ok:
        assert r.baseline_missing is True and any("겹치거나" in x for x in r.reasons)


@pytest.mark.parametrize("start,ok", [("2026-09-02", True), ("2026-09-01", False), ("2026-08-20", False)])
def test_after_period_must_start_after_change_day(start, ok):
    """TC-638: 변경 후 자료의 집계 시작일은 변경일보다 뒤여야 한다. 변경 이전과 겹치면 쓰지 않는다. [FR-018, 경계값]"""
    r = rep([snap(), after(start=start, end="2026-09-30")])
    assert (r.status == "ok") is ok
    if not ok:
        assert any("변경 이전과 겹쳐" in x for x in r.reasons) and r.expected_after_date == "2026-09-15"


def test_snapshot_without_period_falls_back_to_taken_time_but_is_insufficient():
    """TC-639: 기간 정보가 없으면 수집 시각으로 전·후를 가리되, 기간을 모르므로 데이터 부족으로 처리한다. [FR-018, SEC-016]"""
    r = rep([snap(start=None, end=None), after(start=None, end=None)])
    assert r.status == "insufficient" and sum("기간 정보가 없어" in x for x in r.reasons) == 2 and r.before is not None and r.after is not None
    late_before = rep([snap(start=None, end=None, taken="2026-09-05T00:00:00Z"), after()])
    assert late_before.baseline_missing is True and any("변경 뒤에 수집" in x for x in late_before.reasons)
    early_after = rep([snap(), after(start=None, end=None, taken="2026-08-30T00:00:00Z")])
    assert early_after.after is None and early_after.status == "insufficient"
    same_moment = rep([snap(start=None, end=None, taken=APPLIED), after(start=None, end=None, taken=APPLIED)])
    assert same_moment.before is not None and same_moment.after is not None  # 변경과 같은 시각은 양쪽 모두 허용(경계)


def test_missing_impressions_asks_for_csv():
    """TC-640: 노출수가 없으면(API 미제공) 데이터 부족이며 CSV 가져오기를 안내한다. [FR-007, FR-018]"""
    r = rep([snap(imp=None), after(imp=None)])
    assert r.status == "insufficient" and sum("노출수가 없습니다" in x and "CSV" in x for x in r.reasons) == 2


def test_reversed_or_garbled_periods_are_unusable():
    """TC-641: 거꾸로 된 기간·잘못된 날짜 문자열은 기간 정보 없음으로 처리하고 예외를 내지 않는다. [FR-018, SEC-016]"""
    r = rep([snap(start="2026-08-31", end="2026-08-04"), after(start="2026-09-02", end="not-a-date")])
    assert r.status == "insufficient"
    assert sum("기간 정보가 없어" in x for x in r.reasons) >= 1


def test_reversed_period_alone_is_reported_as_missing_period_info():
    """TC-686: 시작일이 종료일보다 늦은 기간만 있어도 '기간 정보 없음'으로 처리하고 음수·0일 같은 이상한 일수를 이유에 쓰지 않는다. [FR-018, SEC-016]"""
    r = rep([snap(start="2026-08-31", end="2026-08-04"), after()])
    assert r.status == "insufficient"
    assert any("변경 전 집계 기간 정보가 없어" in x for x in r.reasons)
    assert not any("일이 최소 기준" in x for x in r.reasons)


def test_multiple_valid_snapshots_use_latest_and_note_it():
    """TC-642: 같은 단계 자료가 여러 건이면 가장 최근(수집 시각, 번호) 것을 쓰고 알린다. [FR-018]"""
    old = snap(id=1, imp=2000, taken="2026-08-31T00:00:00Z", start="2026-08-04", end="2026-08-31")
    new = snap(id=3, imp=28000, taken="2026-09-01T00:00:00Z")
    tie = snap(id=4, imp=14000, start="2026-08-18", taken="2026-09-01T00:00:00Z")
    older_but_bigger_id = snap(id=9, imp=1500, start="2026-08-04", taken="2026-08-31T12:00:00Z")
    r = rep([old, new, tie, older_but_bigger_id, after()])
    assert r.before.id == 4 and any("4건" in n for n in r.notes)


def test_several_changes_use_latest_apply_and_rollback_invalidates():
    """TC-643: 변경이 여러 번이면 가장 최근 적용을 기준으로 하고, 그 뒤 롤백이 있으면 데이터 부족이다. 이전 롤백은 영향 없음. [FR-018, SEC-006]"""
    first = chg(1, at="2026-08-01T00:00:00Z")
    rb_old = chg(2, "rollback", at="2026-08-10T00:00:00Z")
    second = chg(3, at=APPLIED)
    r = rep([snap(), after()], [second, rb_old, first])  # 입력 순서가 뒤섞여도 시각순으로 정렬한다
    assert r.status == "ok" and r.target.id == 3 and any("2번 바꿨" in n for n in r.notes) and [c.id for c in r.changes] == [1, 2, 3]
    rb_new = chg(4, "rollback", at="2026-09-20T00:00:00Z")
    r2 = rep([snap(), after()], [first, second, rb_new])
    assert r2.status == "insufficient" and any("롤백" in x for x in r2.reasons) and r2.metrics == ()


def test_same_timestamp_rollback_orders_by_id():
    """TC-644: 시각이 같은 변경은 번호 순으로 앞뒤를 가린다(같은 시각이어도 번호가 큰 롤백은 뒤). [SEC-006]"""
    r = rep([snap(), after()], [chg(1), chg(2, "rollback", at=APPLIED)])
    assert r.status == "insufficient" and any("롤백" in x for x in r.reasons)
    r2 = rep([snap(), after()], [chg(2), chg(1, "rollback", at=APPLIED)])
    assert r2.status == "ok"


def test_no_successful_apply_means_no_comparison():
    """TC-645: 성공한 적용 기록이 없으면(실패·중단·계획·롤백만) 비교하지 않는다. [FR-018, FR-010]"""
    for changes in ([], [chg(1, result="failed")], [chg(1, result="aborted")], [chg(1, result="planned")], [chg(1, "rollback")]):
        r = rep([snap(), after()], changes)
        assert r.status == "no_change" and r.target is None and r.metrics == () and r.notes
    assert rep([snap(), after()], [chg(1, result="failed")]).changes == ()


def test_unparseable_change_time_is_insufficient():
    """TC-646: 변경 시각을 해석할 수 없으면 전후를 나눌 수 없어 데이터 부족이다(예외 없음). [FR-018]"""
    for bad in ("garbage", None):
        r = rep([snap(), after()], [chg(1, at=bad)])
        assert r.status == "insufficient" and any("변경 시각" in x for x in r.reasons) and r.baseline_missing is True


def test_percent_change_is_none_when_baseline_zero_or_missing():
    """TC-647: 변경 전 값이 0이거나 없으면 변화율은 계산하지 않는다(0으로 나누기 없음). [FR-018]"""
    r = rep([snap(views=0, wm=None), after()])
    m = {x.key: x for x in r.metrics}
    assert r.status == "ok"
    assert m["views"].before == 0.0 and m["views"].delta == 200.0 and m["views"].pct is None
    assert m["watch_minutes"].before is None and m["watch_minutes"].delta is None and m["watch_minutes"].pct is None


def test_build_report_does_not_mutate_inputs():
    """TC-648: 리포트 계산은 입력(변경·지표 목록)을 바꾸지 않는 순수 함수이며 결과가 항상 같다. [FR-018]"""
    changes = [chg(3), chg(1, at="2026-08-01T00:00:00Z"), chg(2, "rollback", at="2026-08-10T00:00:00Z")]
    snaps = [after(), snap()]
    c0, s0 = copy.deepcopy(changes), copy.deepcopy(snaps)
    r1 = build_report(VID, "t", changes, snaps, RULES)
    r2 = build_report(VID, "t", changes, snaps, RULES)
    assert changes == c0 and snaps == s0 and r1 == r2


def test_disclaimer_texts_forbid_causal_claims():
    """TC-649: 면책 문구는 원인 단정 금지와 다른 요인 가능성(시기·노출·A/B)을 담고, 결과 구조에는 '효과 있음' 같은 판정 필드가 없다. [POL-002, FR-018, SCR-008]"""
    assert "원인을 단정할 수 없습니다" in rp.LIMIT_NOTE and "시기·노출 차이" in rp.LIMIT_NOTE
    assert "원인이라고 말하지 않습니다" in rp.CAUSAL_NOTE and "공식 A/B" in rp.CAUSAL_NOTE and "다른 요인" in rp.CAUSAL_NOTE
    assert rp.INSUFFICIENT_LABEL == "데이터 부족"
    fields = set(rp.VideoReport.__dataclass_fields__)
    assert not {"verdict", "improved", "effective", "conclusion", "winner"} & fields


def test_rules_from_settings():
    """TC-650: 최소 노출 기준은 설정(cadence.min_impressions_before_rechange), 평가 기간은 sequential_mode.evaluation_window_days에서 가져온다. [FR-014, FR-019]"""
    s = SimpleNamespace(min_impressions_before_rechange=5000, evaluation_window_days=21)
    assert Rules.from_settings(s) == Rules(5000, rp.MIN_PERIOD_DAYS, 21)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.migrate(c)
    yield c
    c.close()


def _change(conn, vid, ctype, result, applied_at, created_at="2026-09-01T00:00:00Z", prev="이전", new="새"):
    conn.execute(
        "INSERT INTO title_changes (video_id, change_type, previous_title, new_title, result, applied_at, created_at, approver) VALUES (?,?,?,?,?,?,?,?)",
        (vid, ctype, prev, new, result, applied_at, created_at, "me"),
    )


def test_load_video_data_reads_only_success_and_is_read_only(conn):
    """TC-651: DB 조회는 성공한 변경과 해당 영상의 지표만 시각순으로 읽고, DB를 바꾸지 않으며, 영상 ID에 SQL 조각이 있어도 값으로만 쓴다. [SEC-018, T-12, FR-018]"""
    conn.execute("INSERT INTO videos (video_id,title,snippet_json,fetched_at) VALUES (?,?,?,?)", (VID, "현재 제목", "{}", "x"))
    _change(conn, VID, "apply", "success", "2026-09-01T03:00:00Z")
    _change(conn, VID, "apply", "failed", None)
    _change(conn, VID, "rollback", "success", None, created_at="2026-09-05T00:00:00Z")
    _change(conn, "otherother1", "apply", "success", "2026-09-01T03:00:00Z")
    conn.execute("INSERT INTO metrics_snapshots (video_id,taken_at,phase,source,impressions) VALUES (?,?,?,?,?)", (VID, "2026-09-02T00:00:00Z", "after", "csv", 5))
    conn.execute("INSERT INTO metrics_snapshots (video_id,taken_at,phase,source,impressions) VALUES (?,?,?,?,?)", (VID, "2026-08-02T00:00:00Z", "before", "api", 7))
    conn.execute("INSERT INTO metrics_snapshots (video_id,taken_at,phase,source,impressions) VALUES (?,?,?,?,?)", ("otherother1", "2026-08-02T00:00:00Z", "before", "api", 9))
    conn.commit()
    total = conn.total_changes
    d = rp.load_video_data(conn, VID)
    assert d.title == "현재 제목" and [(c.change_type, c.at) for c in d.changes] == [("apply", "2026-09-01T03:00:00Z"), ("rollback", "2026-09-05T00:00:00Z")]
    assert [(s.phase, s.impressions) for s in d.snapshots] == [("before", 7), ("after", 5)]
    evil = rp.load_video_data(conn, "x' OR '1'='1")
    assert evil == rp.VideoData("x' OR '1'='1", None, (), ())
    assert conn.total_changes == total
    assert conn.execute("SELECT COUNT(*) FROM title_changes").fetchone()[0] == 4


def test_list_changed_video_ids_orders_by_latest_success_apply(conn):
    """TC-652: 보고 대상 영상은 성공한 적용 기록이 있는 영상만, 최근 변경 순이다(실패·롤백만 있는 영상 제외). [FR-018]"""
    _change(conn, "aaaaaaaaaaa", "apply", "success", "2026-09-01T00:00:00Z")
    _change(conn, "bbbbbbbbbbb", "apply", "success", "2026-09-03T00:00:00Z")
    _change(conn, "bbbbbbbbbbb", "apply", "success", "2026-08-01T00:00:00Z")
    _change(conn, "ccccccccccc", "apply", "failed", None)
    _change(conn, "ddddddddddd", "rollback", "success", "2026-09-09T00:00:00Z")
    assert rp.list_changed_video_ids(conn) == ["bbbbbbbbbbb", "aaaaaaaaaaa"]


def test_module_has_no_write_sql_or_network():
    """TC-653: 리포트 모듈에는 쓰기 SQL(INSERT/UPDATE/DELETE/DROP)·네트워크 코드가 없다(읽기 전용). [FR-018, SEC-001, SEC-007]"""
    text = open(rp.__file__, encoding="utf-8").read().upper()
    for bad in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "GOOGLEAPICLIENT", "REQUESTS", "URLLIB", "SOCKET"):
        assert bad not in text, bad
