"""이력(/changes)·성과 리포트(/reports)의 영상 구분(롱폼/쇼츠) 조회 조건과 응답 video_kind."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from ytweb.db.models import Change, Video
from ytweb.domain.reports import build_reports, export_csv

from tests.domain.helpers import eligible_video_ids

UTC = timezone.utc


def _add(db, vid, when, *, result="success"):
    db.add(Change(video_id=vid, change_type="apply", previous_title="이전", new_title="새 제목", result=result, mode="demo", applied_at=when, created_at=when))
    db.commit()


@pytest.fixture
def kv(seeded):
    """롱폼·쇼츠·길이불명 영상 각 1개(가짜 구분은 DB 값으로 지정)."""
    ids = eligible_video_ids(seeded, 3)
    for vid, short, dur in zip(ids, (False, True, False), (600, 30, None)):
        v = seeded.get(Video, vid)
        v.is_short, v.duration_sec = short, dur
    seeded.commit()
    when = datetime(2026, 3, 10, 3, tzinfo=UTC)
    for vid in ids:
        _add(seeded, vid, when)
    _add(seeded, ids[0], datetime(2026, 4, 20, 3, tzinfo=UTC), result="failed")
    return ids  # long, short, unknown


def _vids(r):
    return {i["video_id"] for i in r.json()["items"]}


def test_changes_filter_and_field(kv, api, csrf):
    lg, sh, un = kv
    r = api.get("/api/v1/changes?page_size=200")
    kinds = {i["video_id"]: i["video_kind"] for i in r.json()["items"]}
    assert kinds[lg] == "long" and kinds[sh] == "short" and kinds[un] is None
    r = api.get("/api/v1/changes?kind=short&page_size=200")
    assert _vids(r) == {sh} and r.json()["total"] == 1 and all(i["video_kind"] == "short" for i in r.json()["items"])
    r = api.get("/api/v1/changes?kind=long&page_size=200")
    assert _vids(r) == {lg} and r.json()["total"] == 2  # 성공 1 + 실패 1


def test_changes_total_with_paging_and_and_conditions(kv, api, csrf):
    lg, sh, un = kv
    r = api.get("/api/v1/changes?kind=long&page_size=1&page=2")
    assert r.json()["total"] == 2 and len(r.json()["items"]) == 1
    assert api.get("/api/v1/changes?kind=long&result=failed").json()["total"] == 1
    assert api.get("/api/v1/changes?kind=long&result=success").json()["total"] == 1
    assert api.get(f"/api/v1/changes?kind=long&video_id={sh}").json()["total"] == 0
    assert api.get("/api/v1/changes?kind=long&date_from=2026-03-10&date_to=2026-03-10").json()["total"] == 1
    assert api.get("/api/v1/changes?kind=short&date_from=2026-04-01").json()["total"] == 0


def test_changes_bad_kind_422(kv, api, csrf):
    assert api.get("/api/v1/changes?kind=etc").status_code == 422
    assert api.get("/api/v1/reports/changes?kind=etc").status_code == 422


def test_reports_filter_and_field(kv, seeded, env, api, csrf):
    lg, sh, un = kv
    allr = {i["video_id"]: i["video_kind"] for i in build_reports(seeded, env)["items"]}
    assert allr == {lg: "long", sh: "short", un: None}
    assert {i["video_id"] for i in build_reports(seeded, env, None, None, None, "short")["items"]} == {sh}
    assert {i["video_id"] for i in build_reports(seeded, env, None, None, None, "long")["items"]} == {lg}
    assert {i["video_id"] for i in build_reports(seeded, env, None, date(2026, 3, 10), date(2026, 3, 10), "short")["items"]} == {sh}
    assert build_reports(seeded, env, None, date(2026, 4, 1), None, "short")["items"] == []
    r = api.get("/api/v1/reports/changes?kind=short")
    assert r.status_code == 200 and _vids(r) == {sh} and r.json()["items"][0]["video_kind"] == "short"


def test_reports_video_id_ignores_kind(kv, seeded, env):
    lg, sh, un = kv
    items = build_reports(seeded, env, sh, None, None, "long")["items"]
    assert [i["video_id"] for i in items] == [sh] and items[0]["video_kind"] == "short"


def test_csv_filter_columns_unchanged(kv, seeded, env, api, csrf):
    lg, sh, un = kv
    base = export_csv(seeded, env).splitlines()[0]
    c = export_csv(seeded, env, None, None, None, "short")
    assert c.splitlines()[0] == base and "kind" not in base
    assert sh in c and lg not in c and un not in c
    h = api.get("/api/v1/reports/export.csv?kind=long")
    assert h.status_code == 200 and lg.encode() in h.content and sh.encode() not in h.content
