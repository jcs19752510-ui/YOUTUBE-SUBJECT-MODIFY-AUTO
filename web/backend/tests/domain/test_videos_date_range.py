"""영상 목록 조회 기간(최근 변경 시각 기준, 한국시간 양 끝 포함) 시험."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from ytweb.core.errors import ProblemError
from ytweb.db.models import Change
from ytweb.domain.batches import apply_one, create_draft, execute_batch
from ytweb.domain.suggestions import approve
from ytweb.domain.videos import list_videos

from tests.domain.helpers import eligible_video_ids, suggest

UTC = timezone.utc
D = date(2026, 6, 10)
# 2026-06-10 00:00 KST = 2026-06-09 15:00 UTC
KST_START = datetime(2026, 6, 9, 15, 0, tzinfo=UTC)


def _list(db, clock, **kw):
    args = dict(q=None, status=None, excluded=None, sort="video_id", order="asc", page=1, page_size=50)
    args.update(kw)
    return list_videos(db, now=clock(), **args)


@pytest.fixture
def changed(seeded, env, clock, gw):
    """영상 4개를 실제로 한 번씩 변경하고 최근 변경 시각을 지정한 값으로 맞춘다. 나머지 영상은 변경 없음."""
    ids = eligible_video_ids(seeded, 4)
    sugs = []
    for vid in ids:
        s = suggest(seeded, env, clock(), vid)[0]
        approve(seeded, s.id, "홍길동", now=clock(), env=env)
        sugs.append(s)
    batch, _ = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=env)
    execute_batch(seeded, batch.id, f"실행 {len(sugs)}건", now=clock(), env=env)
    for it in batch.items:
        apply_one(seeded, it.id, now=clock(), env=env, gateway=gw)
    rows = {c.video_id: c.id for c in seeded.execute(select(Change)).scalars()}
    when = {
        ids[0]: KST_START,                              # 6/10 00:00:00 KST (경계 포함)
        ids[1]: KST_START + timedelta(hours=24) - timedelta(seconds=1),  # 6/10 23:59:59 KST (경계 포함)
        ids[2]: KST_START - timedelta(seconds=1),       # 6/9 23:59:59 KST (밖)
        ids[3]: KST_START + timedelta(hours=24),        # 6/11 00:00:00 KST (밖)
    }
    for vid, ts in when.items():
        seeded.execute(update(Change).where(Change.id == rows[vid]).values(applied_at=ts))
    seeded.flush()
    return ids


def test_no_range_keeps_existing_behaviour(seeded, clock, changed):
    items, total = _list(seeded, clock)
    assert total == 60 and len(items) == 50


def test_range_inside_and_boundaries_kst(seeded, clock, changed):
    items, total = _list(seeded, clock, date_from=D, date_to=D)
    assert total == 2 and {i["video_id"] for i in items} == {changed[0], changed[1]}


def test_outside_days_excluded_and_wider_range_includes(seeded, clock, changed):
    assert {i["video_id"] for i in _list(seeded, clock, date_from=D - timedelta(days=1), date_to=D)[0]} == {changed[0], changed[1], changed[2]}
    assert _list(seeded, clock, date_from=D + timedelta(days=1), date_to=D + timedelta(days=1))[1] == 1
    assert _list(seeded, clock, date_from=date(2026, 6, 12), date_to=date(2026, 6, 12))[1] == 0


def test_videos_without_change_excluded_when_range_given(seeded, clock, changed):
    items, total = _list(seeded, clock, date_from=date(2000, 1, 1), date_to=date(2100, 1, 1))
    assert total == 4 and all(i["last_change_at"] is not None for i in items)


def test_one_sided_range(seeded, clock, changed):
    assert _list(seeded, clock, date_from=D)[1] == 3
    assert _list(seeded, clock, date_to=D)[1] == 3


def test_total_and_page_are_after_filter(seeded, clock, changed):
    items, total = _list(seeded, clock, date_from=date(2000, 1, 1), date_to=date(2100, 1, 1), page_size=3, page=2)
    assert total == 4 and len(items) == 1


def test_from_after_to_is_422(seeded, clock, changed):
    with pytest.raises(ProblemError) as e:
        _list(seeded, clock, date_from=date(2026, 6, 11), date_to=date(2026, 6, 10))
    assert e.value.status == 422 and e.value.code == "date_range_invalid"


def test_api_query_params_and_422(api, csrf):
    r = api.get("/api/v1/videos", params={"date_from": "2026-06-10", "date_to": "2026-06-10"})
    assert r.status_code == 200 and r.json()["total"] == 0
    r = api.get("/api/v1/videos", params={"date_from": "2026-06-11", "date_to": "2026-06-10"})
    assert r.status_code == 422 and "date_range_invalid" in r.text
    assert api.get("/api/v1/videos", params={"date_from": "not-a-date"}).status_code == 422
