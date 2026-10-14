"""성과 리포트 조회 기간(한국시간 날짜, 양 끝 포함) - 2026-10-14. 변경 시각 기준 = coalesce(applied_at, created_at)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from ytweb.db.models import Change
from ytweb.domain.reports import build_reports, export_csv

from tests.domain.helpers import eligible_video_ids

UTC = timezone.utc


def _add(db, vid, applied_at, *, result="success", ctype="apply", created=None):
    db.add(Change(video_id=vid, change_type=ctype, previous_title="이전", new_title="새 제목", result=result, mode="demo",
                  applied_at=applied_at, created_at=created or applied_at or datetime(2026, 1, 1, tzinfo=UTC)))
    db.commit()


@pytest.fixture
def vids(seeded):
    return eligible_video_ids(seeded, 6)


def _ids(data):
    return {i["video_id"] for i in data["items"]}


def test_unset_range_keeps_existing_behavior(seeded, env, vids):
    _add(seeded, vids[0], datetime(2026, 3, 1, 3, tzinfo=UTC))
    _add(seeded, vids[1], datetime(2026, 9, 1, 3, tzinfo=UTC))
    assert _ids(build_reports(seeded, env)) == {vids[0], vids[1]}
    assert _ids(build_reports(seeded, env, None, None, None)) == {vids[0], vids[1]}


def test_inside_and_outside_range(seeded, env, vids):
    _add(seeded, vids[0], datetime(2026, 3, 10, 3, tzinfo=UTC))
    _add(seeded, vids[1], datetime(2026, 4, 20, 3, tzinfo=UTC))
    assert _ids(build_reports(seeded, env, None, date(2026, 3, 1), date(2026, 3, 31))) == {vids[0]}
    assert _ids(build_reports(seeded, env, None, date(2026, 5, 1), date(2026, 5, 31))) == set()
    assert _ids(build_reports(seeded, env, None, date(2026, 4, 1), None)) == {vids[1]}
    assert _ids(build_reports(seeded, env, None, None, date(2026, 3, 31))) == {vids[0]}


def test_kst_boundaries_both_ends_inclusive(seeded, env, vids):
    # 2026-03-09 14:59:59 UTC = 03-09 23:59:59 KST (3/9 안), 15:00:00 UTC = 3/10 00:00 KST
    _add(seeded, vids[0], datetime(2026, 3, 9, 14, 59, 59, tzinfo=UTC))
    _add(seeded, vids[1], datetime(2026, 3, 9, 15, 0, 0, tzinfo=UTC))
    _add(seeded, vids[2], datetime(2026, 3, 10, 14, 59, 59, tzinfo=UTC))
    _add(seeded, vids[3], datetime(2026, 3, 10, 15, 0, 0, tzinfo=UTC))
    got = _ids(build_reports(seeded, env, None, date(2026, 3, 10), date(2026, 3, 10)))
    assert got == {vids[1], vids[2]}


def test_applied_at_missing_falls_back_to_created_at(seeded, env, vids):
    _add(seeded, vids[0], None, created=datetime(2026, 3, 10, 3, tzinfo=UTC))
    assert _ids(build_reports(seeded, env, None, date(2026, 3, 10), date(2026, 3, 10))) == {vids[0]}


def test_only_successful_apply_counts(seeded, env, vids):
    t = datetime(2026, 3, 10, 3, tzinfo=UTC)
    _add(seeded, vids[0], t, result="failed")
    _add(seeded, vids[1], t, ctype="rollback")
    _add(seeded, vids[2], t)
    assert _ids(build_reports(seeded, env, None, date(2026, 3, 10), date(2026, 3, 10))) == {vids[2]}


def test_report_still_uses_all_changes_of_the_video(seeded, env, vids):
    _add(seeded, vids[0], datetime(2026, 2, 1, 3, tzinfo=UTC))
    _add(seeded, vids[0], datetime(2026, 3, 10, 3, tzinfo=UTC))
    item, = build_reports(seeded, env, None, date(2026, 3, 10), date(2026, 3, 10))["items"]
    assert len(item["changes"]) == 2


def test_video_id_given_ignores_range(seeded, env, vids):
    """특정 영상 조회는 사용자가 영상을 직접 지정한 것이므로 기간으로 숨기지 않는다(기존 동작 유지)."""
    _add(seeded, vids[0], datetime(2026, 3, 10, 3, tzinfo=UTC))
    got = build_reports(seeded, env, vids[0], date(2026, 6, 1), date(2026, 6, 1))
    assert _ids(got) == {vids[0]} and got["items"][0]["changes"]


def test_from_after_to_is_422(seeded, env, vids, api, csrf):
    from ytweb.core.errors import ProblemError
    with pytest.raises(ProblemError) as e:
        build_reports(seeded, env, None, date(2026, 3, 11), date(2026, 3, 10))
    assert e.value.status == 422 and e.value.code == "date_range_invalid"
    r = api.get("/api/v1/reports/changes?date_from=2026-03-11&date_to=2026-03-10")
    assert r.status_code == 422 and r.json()["code"] == "date_range_invalid"
    r = api.get("/api/v1/reports/export.csv?date_from=2026-03-11&date_to=2026-03-10")
    assert r.status_code == 422 and r.json()["code"] == "date_range_invalid"


def test_csv_follows_same_range(seeded, env, vids):
    _add(seeded, vids[0], datetime(2026, 3, 10, 3, tzinfo=UTC))
    _add(seeded, vids[1], datetime(2026, 4, 20, 3, tzinfo=UTC))
    csv_in = export_csv(seeded, env, None, date(2026, 3, 10), date(2026, 3, 10))
    assert vids[0] in csv_in and vids[1] not in csv_in
    csv_all = export_csv(seeded, env)
    assert vids[0] in csv_all and vids[1] in csv_all


def test_http_query_params(seeded, env, vids, api, csrf):
    _add(seeded, vids[0], datetime(2026, 3, 10, 3, tzinfo=UTC))
    _add(seeded, vids[1], datetime(2026, 4, 20, 3, tzinfo=UTC))
    r = api.get("/api/v1/reports/changes?date_from=2026-03-10&date_to=2026-03-10")
    assert r.status_code == 200 and {i["video_id"] for i in r.json()["items"]} == {vids[0]}
    c = api.get("/api/v1/reports/export.csv?date_from=2026-04-20&date_to=2026-04-20")
    assert c.status_code == 200 and vids[1].encode() in c.content and vids[0].encode() not in c.content
