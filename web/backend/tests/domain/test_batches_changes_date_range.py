"""배치 목록·이력의 조회 기간(한국 시간 날짜 from~to, 양 끝 포함). 기준: 배치=만든 시각, 이력=처리 시각 coalesce(applied_at, created_at)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from ytweb.core.errors import ProblemError
from ytweb.db.models import Batch, Change
from ytweb.domain.batches import list_batches
from ytweb.domain.changes import list_changes

from tests.domain.conftest import hdr  # noqa: F401  (fixture 모듈 로드)

UTC = timezone.utc
D = date(2026, 10, 10)


def _kst(day: date, h: int, m: int = 0, s: int = 0) -> datetime:
    """한국 시간 day h:m:s 를 UTC 로."""
    return (datetime(day.year, day.month, day.day, h, m, s) - timedelta(hours=9)).replace(tzinfo=UTC)


def _batch(db, at):
    b = Batch(status="draft", created_at=at, updated_at=at)
    db.add(b)
    db.flush()
    return b.id


def _change(db, vid, *, applied=None, created=None):
    c = Change(video_id=vid, change_type="apply", previous_title="a", new_title="b", result="success", mode="demo", applied_at=applied, created_at=created or applied)
    db.add(c)
    db.flush()
    return c.id


@pytest.fixture
def bids(seeded):
    ids = {
        "prev_last": _batch(seeded, _kst(D - timedelta(days=1), 23, 59, 59)),   # 전날 한국 23:59:59 -> 기간 밖
        "first": _batch(seeded, _kst(D, 0, 0, 0)),                              # 당일 한국 자정 -> 안(경계)
        "last": _batch(seeded, _kst(D, 23, 59, 59)),                            # 당일 한국 23:59:59 -> 안(경계)
        "next_first": _batch(seeded, _kst(D + timedelta(days=1), 0, 0, 0)),     # 다음날 자정 -> 밖
    }
    seeded.commit()
    return ids


def _ids(rows):
    return {b.id for b in rows}


def test_batches_single_day_kst_boundaries(seeded, bids):
    rows, total = list_batches(seeded, page=1, page_size=50, date_from=D, date_to=D)
    assert _ids(rows) == {bids["first"], bids["last"]} and total == 2


def test_batches_open_ended_and_multi_day(seeded, bids):
    assert _ids(list_batches(seeded, page=1, page_size=50, date_from=D)[0]) >= {bids["first"], bids["last"], bids["next_first"]}
    assert bids["prev_last"] not in _ids(list_batches(seeded, page=1, page_size=50, date_from=D)[0])
    rows, total = list_batches(seeded, page=1, page_size=50, date_to=D)
    assert bids["next_first"] not in _ids(rows) and bids["prev_last"] in _ids(rows) and total == len(rows)
    rows, total = list_batches(seeded, page=1, page_size=50, date_from=D - timedelta(days=1), date_to=D + timedelta(days=1))
    assert _ids(rows) == set(bids.values()) and total == 4


def test_batches_unspecified_keeps_old_behaviour_and_total_after_filter(seeded, bids):
    rows, total = list_batches(seeded, page=1, page_size=50)
    assert _ids(rows) == set(bids.values()) and total == 4
    rows, total = list_batches(seeded, page=1, page_size=1, date_from=D, date_to=D)   # total 은 쪽 크기와 무관하게 필터 후 전체
    assert len(rows) == 1 and total == 2
    assert len(list_batches(seeded, page=2, page_size=1, date_from=D, date_to=D)[0]) == 1
    assert list_batches(seeded, page=1, page_size=50, date_from=D + timedelta(days=30), date_to=D + timedelta(days=30)) == ([], 0)


def test_batches_from_after_to_is_422(seeded):
    with pytest.raises(ProblemError) as e:
        list_batches(seeded, page=1, page_size=50, date_from=D + timedelta(days=1), date_to=D)
    assert (e.value.status, e.value.code) == (422, "date_range_invalid")


@pytest.fixture
def cids(seeded):
    vid = seeded.execute(__import__("sqlalchemy").text("select video_id from videos limit 1")).scalar_one()
    ids = {
        "applied_in": _change(seeded, vid, applied=_kst(D, 0, 0, 0), created=_kst(D - timedelta(days=5), 12)),   # 처리 시각이 기준(created 는 밖)
        "applied_out": _change(seeded, vid, applied=_kst(D - timedelta(days=1), 23, 59, 59), created=_kst(D, 12)),  # created 는 안이지만 처리 시각이 밖
        "planned_in": _change(seeded, vid, applied=None, created=_kst(D, 23, 59, 59)),                           # applied 없으면 created 기준
        "planned_out": _change(seeded, vid, applied=None, created=_kst(D + timedelta(days=1), 0, 0, 0)),
    }
    seeded.commit()
    return ids


def _cids(res):
    return {c.id for c, _ in res[0]}


def test_changes_basis_is_applied_else_created(seeded, cids):
    res = list_changes(seeded, video_id=None, batch_id=None, result=None, page=1, page_size=50, date_from=D, date_to=D)
    assert _cids(res) == {cids["applied_in"], cids["planned_in"]} and res[2] == 2


def test_changes_unspecified_and_total_and_combined_filters(seeded, cids):
    res = list_changes(seeded, video_id=None, batch_id=None, result=None, page=1, page_size=50)
    assert _cids(res) >= set(cids.values()) and res[2] == len(res[0])
    res = list_changes(seeded, video_id=None, batch_id=None, result=None, page=1, page_size=1, date_from=D, date_to=D)
    assert len(res[0]) == 1 and res[2] == 2
    res = list_changes(seeded, video_id=None, batch_id=None, result="failed", page=1, page_size=50, date_from=D, date_to=D)   # 다른 조건과 함께 적용
    assert res[0] == [] and res[2] == 0


def test_changes_from_after_to_is_422(seeded):
    with pytest.raises(ProblemError) as e:
        list_changes(seeded, video_id=None, batch_id=None, result=None, page=1, page_size=50, date_from=D + timedelta(days=1), date_to=D)
    assert (e.value.status, e.value.code) == (422, "date_range_invalid")


def test_http_query_params(api, csrf, seeded, bids, cids, factory, env):
    # seeded 는 db 세션 fixture — HTTP 쪽은 같은 DB 를 본다
    r = api.get("/api/v1/batches?date_from=2026-10-10&date_to=2026-10-10")
    assert r.status_code == 200 and r.json()["total"] == 2
    assert api.get("/api/v1/batches").json()["total"] == 4
    assert api.get("/api/v1/changes?date_from=2026-10-10&date_to=2026-10-10").json()["total"] == 2
    for path in ("batches", "changes"):
        bad = api.get(f"/api/v1/{path}?date_from=2026-10-11&date_to=2026-10-10")
        assert bad.status_code == 422 and bad.json()["code"] == "date_range_invalid"
        assert api.get(f"/api/v1/{path}?date_from=not-a-date").status_code == 422
