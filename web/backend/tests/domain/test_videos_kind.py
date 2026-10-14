"""영상 목록 '영상 구분'(롱폼/쇼츠) 조회 시험(2026-10-14)."""
from __future__ import annotations

from ytweb.db.models import Video
from ytweb.domain.videos import list_videos


def _list(db, clock, **kw):
    args = dict(q=None, status=None, excluded=None, sort="video_id", order="asc", page=1, page_size=200)
    args.update(kw)
    return list_videos(db, now=clock(), **args)


def _set(db, kinds):
    """시드 영상 앞 3개를 (is_short, duration) 지정값으로 바꾼다."""
    vids = db.query(Video).order_by(Video.video_id).limit(len(kinds)).all()
    for v, (short, dur) in zip(vids, kinds):
        v.is_short, v.duration_sec = short, dur
    db.flush()
    return [v.video_id for v in vids]


def test_kind_short_only(seeded, clock):
    ids = _set(seeded, [(True, 60), (False, 600), (False, None)])
    rows, total = _list(seeded, clock, kind="short")
    got = {r["video_id"] for r in rows}
    assert ids[0] in got and ids[1] not in got and ids[2] not in got
    assert total == len(rows) and all(r["is_short"] for r in rows)


def test_kind_long_only_excludes_shorts_and_unknown_duration(seeded, clock):
    ids = _set(seeded, [(True, 60), (False, 600), (False, None)])
    rows, total = _list(seeded, clock, kind="long")
    got = {r["video_id"] for r in rows}
    assert ids[1] in got and ids[0] not in got and ids[2] not in got
    assert total == len(rows) and all((not r["is_short"]) and r["duration_sec"] is not None for r in rows)


def test_kind_none_keeps_all(seeded, clock):
    _set(seeded, [(True, 60), (False, 600), (False, None)])
    _, all_total = _list(seeded, clock)
    _, s = _list(seeded, clock, kind="short")
    _, l = _list(seeded, clock, kind="long")
    assert s + l <= all_total and s >= 1 and l >= 1


def test_kind_combines_with_search(seeded, clock):
    ids = _set(seeded, [(True, 60), (True, 90), (False, 600)])
    rows, _ = _list(seeded, clock, kind="short", q=ids[1])
    assert [r["video_id"] for r in rows] == [ids[1]]
