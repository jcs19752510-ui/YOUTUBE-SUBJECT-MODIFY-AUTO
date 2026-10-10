"""변경 이력·롤백(093-103), 리포트·CSV(104-112)."""
from __future__ import annotations

import csv
import dataclasses
import io
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from ytweb.core.errors import ProblemError
from ytweb.db.models import AuditLog, Change, MetricsSnapshot, QuotaUsage, Suggestion, Video
from ytweb.domain.batches import apply_one
from ytweb.domain.changes import list_changes, rollback_change, rollbackable_map
from ytweb.domain.reports import CSV_COLUMNS, build_reports, csv_safe, export_csv
from ytweb.youtube.base import GatewayError

from tests.domain.helpers import FaultyGateway, queued_batch


def _problem(fn, *a, **kw) -> ProblemError:
    with pytest.raises(ProblemError) as e:
        fn(*a, **kw)
    return e.value


def _applied(db, env, clock, gw, n=1, skip=0):
    batch, sugs, _ = queued_batch(db, env, clock(), n, skip)
    return [(apply_one(db, i.id, now=clock(), env=env, gateway=gw), s) for i, s in zip(batch.items, sugs)]


def _one(db, env, clock, gw):
    (out, sug), = _applied(db, env, clock, gw)
    return db.get(Change, out.change_id), sug


def _rb(db, env, clock, gw, change, typed=None, approver="홍길동"):
    return rollback_change(db, change.id, typed or change.video_id, approver, now=clock(), env=env, gateway=gw)


def test_tc_wb_093_list_changes_with_titles_filters_and_rollbackable(seeded, env, clock, gw):
    results = _applied(seeded, env, clock, gw, 3)
    first = seeded.get(Change, results[0][0].change_id)
    seeded.add(Change(video_id=first.video_id, change_type="apply", previous_title="a", new_title="b", result="failed", mode="demo", error_code="x", created_at=clock()))
    seeded.commit()
    rows, rb, total = list_changes(seeded, video_id=None, batch_id=None, result=None, page=1, page_size=50)
    assert total == 4 and rows[0][0].id > rows[-1][0].id
    assert {c.video_id: t for c, t in rows}[first.video_id] == first.new_title
    assert rb[first.id] is True                                   # failed 행은 이후 변경으로 세지 않는다
    assert [c.id for c, _ in list_changes(seeded, video_id=first.video_id, batch_id=None, result="success", page=1, page_size=50)[0]] == [first.id]
    assert list_changes(seeded, video_id=None, batch_id=first.batch_id, result=None, page=1, page_size=2)[2] == 3
    assert len(list_changes(seeded, video_id=None, batch_id=first.batch_id, result=None, page=2, page_size=2)[0]) == 1


def test_tc_wb_094_rollback_restores_backup_and_verifies(seeded, env, clock, gw):
    change, sug = _one(seeded, env, clock, gw)
    original = dict(change.backup_snippet)
    clock.advance(hours=1)
    rb = _rb(seeded, env, clock, gw, change, approver=" 김철수 ")
    seeded.commit()
    video = seeded.get(Video, change.video_id)
    assert video.title == change.previous_title and video.snippet["description"] == original["description"]
    assert (rb.change_type, rb.result, rb.approver, rb.previous_title, rb.new_title, rb.mode) == ("rollback", "success", "김철수", change.new_title, change.previous_title, "demo")
    assert rb.verify_result["ok"] and rb.backup_snippet["title"] == change.new_title and rb.applied_at == clock()
    assert seeded.get(Suggestion, sug.id).status == "rolled_back"
    assert rollbackable_map(seeded, [change, rb]) == {change.id: False, rb.id: False}
    assert seeded.execute(select(AuditLog).where(AuditLog.action == "change.rollback")).scalar_one().detail["target_change"] == change.id
    assert len(seeded.execute(select(QuotaUsage).where(QuotaUsage.method == "videos.update")).scalars().all()) == 2


def test_tc_wb_095_typed_video_id_must_match(seeded, env, clock, gw):
    change, _ = _one(seeded, env, clock, gw)
    for wrong in ("", "demoVid9999", change.video_id.lower(), change.video_id + " "):
        e = _problem(_rb, seeded, env, clock, gw, change, typed=wrong) if wrong else _problem(rollback_change, seeded, change.id, wrong, "홍", now=clock(), env=env, gateway=gw)
        assert (e.status, e.code) == (422, "typed_video_id_mismatch")
    assert seeded.get(Video, change.video_id).title == change.new_title and len(seeded.execute(select(Change)).scalars().all()) == 1


def test_tc_wb_096_later_change_blocks_rollback(seeded, env, clock, gw):
    change, _ = _one(seeded, env, clock, gw)
    later = Change(video_id=change.video_id, change_type="apply", previous_title="x", new_title="y", result="success", mode="demo", applied_at=clock(), created_at=clock())
    seeded.add(later)
    seeded.commit()
    e = _problem(_rb, seeded, env, clock, gw, change)
    assert (e.status, e.code) == (409, "later_change_exists") and f"#{later.id}" in e.title
    assert rollbackable_map(seeded, [change, later]) == {change.id: False, later.id: False}  # later 는 백업이 없어 롤백 불가
    later.result = "planned"                                     # 진행 중 변경도 막는다
    seeded.commit()
    assert _problem(_rb, seeded, env, clock, gw, change).code == "later_change_exists"
    later.result = "failed"                                      # 실패한 시도는 막지 않는다
    seeded.commit()
    assert _rb(seeded, env, clock, gw, change).result == "success"


def test_tc_wb_097_only_successful_applies_are_rollbackable(seeded, env, clock, gw):
    change, _ = _one(seeded, env, clock, gw)
    rb = _rb(seeded, env, clock, gw, change)
    failed = Change(video_id=change.video_id, change_type="apply", previous_title="a", new_title="b", result="failed", mode="demo", created_at=clock())
    seeded.add(failed)
    seeded.commit()
    for c in (rb, failed):
        assert _problem(_rb, seeded, env, clock, gw, c).code == "not_rollbackable"
    assert _problem(rollback_change, seeded, 99999, "demoVid0001", "홍", now=clock(), env=env, gateway=gw).status == 404


def test_tc_wb_098_double_rollback_is_refused(seeded, env, clock, gw):
    change, _ = _one(seeded, env, clock, gw)
    _rb(seeded, env, clock, gw, change)
    seeded.commit()
    assert _problem(_rb, seeded, env, clock, gw, change).code == "later_change_exists"
    assert len(seeded.execute(select(Change).where(Change.change_type == "rollback")).scalars().all()) == 1


def test_tc_wb_099_gateway_failure_records_failed_rollback(seeded, env, clock, gw):
    change, _ = _one(seeded, env, clock, gw)
    faulty = FaultyGateway(seeded, clock)
    faulty.update_exc = GatewayError("backendError", "서버 오류")
    e = _problem(_rb, seeded, env, clock, faulty, change)
    assert (e.status, e.code) == (502, "gateway_error")
    seeded.rollback()
    row = seeded.execute(select(Change).where(Change.change_type == "rollback")).scalar_one()
    assert (row.result, row.error_code) == ("failed", "backendError") and seeded.get(Video, change.video_id).title == change.new_title
    assert _rb(seeded, env, clock, gw, change).result == "success"   # 실패 뒤 다시 시도할 수 있다(planned 가 남지 않음)
    other, _ = _one_second(seeded, env, clock, gw)
    faulty2 = FaultyGateway(seeded, clock)
    faulty2.update_exc = GatewayError("timeout", "끊김", definite=False)
    assert _problem(_rb, seeded, env, clock, faulty2, other).status == 502
    seeded.rollback()
    assert seeded.execute(select(Change).where(Change.change_type == "rollback", Change.video_id == other.video_id)).scalar_one().result == "planned"


def _one_second(db, env, clock, gw):
    (out, sug), = _applied(db, env, clock, gw, 1, skip=1)
    return db.get(Change, out.change_id), sug


def test_tc_wb_100_rollback_recovers_description_lost_by_apply(seeded, env, clock):
    lossy = FaultyGateway(seeded, clock)
    lossy.drop_on_update = ("description", "tags")
    change, _ = _one(seeded, env, clock, lossy)
    assert change.error_code == "verify_failed" and "description" not in seeded.get(Video, change.video_id).snippet
    good = FaultyGateway(seeded, clock)
    rb = _rb(seeded, env, clock, good, change)
    video = seeded.get(Video, change.video_id)
    assert rb.verify_result["ok"] and rb.error_code is None and video.snippet["description"] == change.backup_snippet["description"] and video.snippet["tags"] == change.backup_snippet["tags"]
    assert set(rb.verify_result["changed_since_backup"]) >= {"description", "tags"}
    lossy2 = FaultyGateway(seeded, clock)                       # 롤백 자체가 필드를 잃으면 검증 실패로 표시
    change2, _ = _one_second(seeded, env, clock, FaultyGateway(seeded, clock))
    lossy2.drop_on_update = ("description",)
    rb2 = _rb(seeded, env, clock, lossy2, change2)
    assert rb2.result == "success" and rb2.error_code == "verify_failed" and rb2.verify_result["preserved"]["description"] is False


def test_tc_wb_101_quota_exhausted_and_already_restored(seeded, env, clock, gw):
    change, _ = _one(seeded, env, clock, gw)
    tight = dataclasses.replace(env, policy=dataclasses.replace(env.policy, daily_limit_units=60))
    e = _problem(rollback_change, seeded, change.id, change.video_id, "홍길동", now=clock(), env=tight, gateway=gw)
    assert (e.status, e.code) == (429, "quota_exhausted")
    video = seeded.get(Video, change.video_id)
    video.title = change.previous_title                            # 누군가 이미 직접 되돌림
    video.snippet = {**video.snippet, "title": change.previous_title}
    seeded.commit()
    e2 = _problem(_rb, seeded, env, clock, gw, change)
    assert e2.code == "already_restored"
    used = seeded.execute(select(QuotaUsage.units)).scalars().all()
    assert sum(used) == 52 + 1                                      # 반영 52 + 이번 시도의 재조회 1(안 쓴 예약은 환원)


def test_tc_wb_102_invalid_backup_is_refused(seeded, env, clock, gw):
    change, _ = _one(seeded, env, clock, gw)
    change.backup_snippet = {"title": "다른 제목", "categoryId": "26"}
    seeded.commit()
    assert _problem(_rb, seeded, env, clock, gw, change).code == "backup_invalid"
    assert rollbackable_map(seeded, [change])[change.id] is True    # 목록에서는 가능으로 보이되 실행 때 한 번 더 막는다
    change.backup_snippet = None
    seeded.commit()
    assert rollbackable_map(seeded, [change])[change.id] is False


def test_tc_wb_103_approver_is_validated(seeded, env, clock, gw):
    change, _ = _one(seeded, env, clock, gw)
    assert _problem(_rb, seeded, env, clock, gw, change, approver="  ").code == "approver_required"
    assert _problem(_rb, seeded, env, clock, gw, change, approver="a\nb").code == "approver_invalid"


# ───────────── 리포트 ─────────────

def _success(db, vid, at, title="새 제목", ctype="apply"):
    c = Change(video_id=vid, change_type=ctype, previous_title="이전", new_title=title, result="success", mode="demo", applied_at=at, created_at=at, approver="홍길동")
    db.add(c)
    db.flush()
    return c


def _snap(db, vid, phase, start: date, end: date, impressions=3000, ctr=4.0, views=100, watch=300.0):
    db.add(MetricsSnapshot(video_id=vid, taken_at=__import__("datetime").datetime(end.year, end.month, end.day, 12, tzinfo=__import__("datetime").timezone.utc) + timedelta(days=1), phase=phase, source="demo",
                           period_start=start, period_end=end, impressions=impressions, ctr=ctr, views=views, watch_minutes=watch))
    db.flush()


def _vid(db, n=0):
    return [v.video_id for v in db.execute(select(Video).order_by(Video.video_id)).scalars() if not v.exclusion_reasons][n]


def test_tc_wb_104_report_without_changes_has_notes_only(seeded, env):
    data = build_reports(seeded, env)
    assert data["items"] == [] and any("원인이라고 말하지 않습니다" in n for n in data["notes"]) and any("순차 비교" in n for n in data["notes"])
    assert any("가상" in n for n in data["notes"])


def test_tc_wb_105_missing_after_metrics_is_insufficient_not_a_verdict(seeded, env, clock):
    vid = _vid(seeded)
    seeded.query(MetricsSnapshot).delete()
    t = clock() - timedelta(days=3)
    _success(seeded, vid, t)
    _snap(seeded, vid, "before", (t - timedelta(days=40)).date(), (t - timedelta(days=10)).date())
    (item,) = build_reports(seeded, env)["items"]
    assert (item["status"], item["label"], item["metrics"], item["after"]) == ("insufficient", "데이터 부족", [], None)
    assert "변경 후 지표가 아직 없습니다." in item["reasons"] and item["expected_after_date"] == (t.date() + timedelta(days=14)).isoformat() and not item["baseline_missing"]
    assert "ok" not in str(item["status"]) and "효과" not in str(item)


def test_tc_wb_106_missing_baseline_is_stated(seeded, env, clock):
    vid = _vid(seeded, 1)
    seeded.query(MetricsSnapshot).filter_by(video_id=vid).delete()
    t = clock() - timedelta(days=20)
    _success(seeded, vid, t)
    _snap(seeded, vid, "after", (t + timedelta(days=1)).date(), (t + timedelta(days=14)).date())
    (item,) = build_reports(seeded, env, vid)["items"]
    assert item["baseline_missing"] is True and "변경 전 지표(기준선)가 없습니다." in item["reasons"] and item["status"] == "insufficient"


def test_tc_wb_107_enough_data_gives_side_by_side_numbers(seeded, env, clock):
    vid = _vid(seeded, 2)
    seeded.query(MetricsSnapshot).filter_by(video_id=vid).delete()
    t = clock() - timedelta(days=20)
    _success(seeded, vid, t)
    _snap(seeded, vid, "before", (t - timedelta(days=30)).date(), (t - timedelta(days=1)).date(), impressions=3000, ctr=4.0, views=300, watch=900.0)
    _snap(seeded, vid, "after", (t + timedelta(days=1)).date(), (t + timedelta(days=14)).date(), impressions=2800, ctr=5.0, views=210, watch=700.0)
    (item,) = build_reports(seeded, env)["items"]
    assert item["status"] == "ok" and item["reasons"] == [] and item["label"] is None
    m = {x["key"]: x for x in item["metrics"]}
    assert set(m) == {"impressions", "ctr", "views", "watch_minutes"}
    assert m["impressions"]["before"] == pytest.approx(100.0) and m["impressions"]["after"] == pytest.approx(200.0) and m["ctr"]["delta"] == pytest.approx(1.0)


def test_tc_wb_108_low_impressions_and_short_period_are_insufficient(seeded, env, clock):
    vid = _vid(seeded, 3)
    seeded.query(MetricsSnapshot).filter_by(video_id=vid).delete()
    t = clock() - timedelta(days=20)
    _success(seeded, vid, t)
    _snap(seeded, vid, "before", (t - timedelta(days=30)).date(), (t - timedelta(days=1)).date(), impressions=500)
    _snap(seeded, vid, "after", (t + timedelta(days=1)).date(), (t + timedelta(days=3)).date())
    (item,) = build_reports(seeded, env)["items"]
    text = " ".join(item["reasons"])
    assert item["status"] == "insufficient" and "최소 기준" in text and "짧습니다" in text and item["metrics"] == []


def test_tc_wb_109_rollback_after_change_blocks_comparison(seeded, env, clock):
    vid = _vid(seeded, 4)
    t = clock() - timedelta(days=20)
    _success(seeded, vid, t)
    _success(seeded, vid, t + timedelta(days=2), ctype="rollback")
    (item,) = build_reports(seeded, env)["items"]
    assert item["status"] == "insufficient" and any("롤백" in r for r in item["reasons"])
    only_rb = build_reports(seeded, env, _vid(seeded, 5))
    assert only_rb["items"][0]["status"] == "no_change"
    assert _problem(build_reports, seeded, env, "zzzzzzzzzzz").status == 404


def test_tc_wb_110_csv_export_neutralizes_formulas(seeded, env, clock):
    vid = _vid(seeded, 6)
    video = seeded.get(Video, vid)
    video.title = "=HYPERLINK(\"http://evil\",\"x\")"
    _success(seeded, vid, clock() - timedelta(days=2), title="@SUM(A1)")
    text = export_csv(seeded, env)
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert tuple(rows[0]) == CSV_COLUMNS
    data = dict(zip(rows[0], rows[1]))
    assert data["title"] == "'=HYPERLINK(\"http://evil\",\"x\")" and data["new_title"] == "'@SUM(A1)" and data["status"] == "insufficient"
    assert all(not c.startswith(("=", "+", "@")) for r in rows for c in r if c)       # 어떤 칸도 수식으로 시작하지 않는다
    assert any("원인이라고 말하지 않습니다" in r[0] for r in rows[3:] if r)


@pytest.mark.parametrize("raw,expected", [("=1+1", "'=1+1"), ("+1", "'+1"), ("-1", "'-1"), ("@a", "'@a"), ("\tx", "'\tx"), ("\rx", "'\rx"), ("정상", "정상"), ("", ""), (-5.5, -5.5), (3, 3), (None, None)])
def test_tc_wb_111_csv_safe(raw, expected):
    assert csv_safe(raw) == expected


def test_tc_wb_112_csv_numbers_stay_numeric(seeded, env, clock):
    vid = _vid(seeded, 2)
    seeded.query(MetricsSnapshot).filter_by(video_id=vid).delete()
    t = clock() - timedelta(days=20)
    _success(seeded, vid, t)
    _snap(seeded, vid, "before", (t - timedelta(days=30)).date(), (t - timedelta(days=1)).date(), ctr=-1.5)
    _snap(seeded, vid, "after", (t + timedelta(days=1)).date(), (t + timedelta(days=14)).date())
    row = dict(zip(CSV_COLUMNS, list(csv.reader(io.StringIO(export_csv(seeded, env, vid).lstrip("﻿"))))[1]))
    assert row["before_ctr"] == "-1.5" and row["status"] == "ok"
