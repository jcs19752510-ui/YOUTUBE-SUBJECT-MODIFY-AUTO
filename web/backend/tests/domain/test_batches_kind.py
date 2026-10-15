"""배치 목록의 영상 구분(롱폼/쇼츠) 조회·표시: 구분 조건 = 그 구분의 영상이 1개 이상 든 배치, kind_counts, 항목 video_kind, 기간과 AND."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from ytweb.db.models import Batch, BatchItem, Suggestion, Video
from ytweb.domain.batches import list_batches
from ytweb.domain.serialize import batch_dict, kind_counts_for

from tests.domain.conftest import hdr  # noqa: F401  (fixture 모듈 로드)

UTC = timezone.utc
D = date(2026, 10, 10)
NOW = datetime(2026, 10, 10, 3, 0, tzinfo=UTC)   # 한국 12시


def _video(db, vid, *, short, dur):
    db.add(Video(video_id=vid, title=f"제목 {vid}", duration_sec=dur, is_short=short, snippet={}, fetched_at=NOW))
    db.flush()


def _batch(db, at, vids):
    b = Batch(status="draft", created_at=at, updated_at=at)
    db.add(b)
    db.flush()
    for i, v in enumerate(vids, 1):
        s = Suggestion(video_id=v, title=f"새 {v} {b.id}", source="manual", created_at=at, updated_at=at)
        db.add(s)
        db.flush()
        db.add(BatchItem(batch_id=b.id, suggestion_id=s.id, video_id=v, seq=i, status="pending", updated_at=at))
    db.flush()
    return b.id


@pytest.fixture
def kb(seeded):
    db = seeded
    _video(db, "KLONG000001", short=False, dur=600)
    _video(db, "KLONG000002", short=False, dur=900)
    _video(db, "KSHORT00001", short=True, dur=30)
    _video(db, "KUNKN000001", short=False, dur=None)
    old = NOW - timedelta(days=5)
    ids = {
        "long": _batch(db, NOW, ["KLONG000001", "KLONG000002"]),                 # 롱폼 2
        "short": _batch(db, NOW, ["KSHORT00001"]),                               # 쇼츠 1
        "mixed": _batch(db, NOW, ["KLONG000001", "KSHORT00001", "KUNKN000001"]),  # 롱 1 쇼 1 불명 1
        "old_long": _batch(db, old, ["KLONG000002"]),                             # 기간 밖
        "unknown": _batch(db, NOW, ["KUNKN000001"]),                              # 불명만
    }
    db.commit()
    return ids


def _ids(rows):
    return {b.id for b in rows}


def test_filter_long_includes_mixed_and_counts_each_batch_once(seeded, kb):
    rows, total = list_batches(seeded, page=1, page_size=50, kind="long")
    assert _ids(rows) == {kb["long"], kb["mixed"], kb["old_long"]} and total == 3   # 롱폼 2개 든 배치도 1번만


def test_filter_short_includes_mixed(seeded, kb):
    rows, total = list_batches(seeded, page=1, page_size=50, kind="short")
    assert _ids(rows) == {kb["short"], kb["mixed"]} and total == 2


def test_no_kind_returns_all_and_unknown_only_batch_not_in_either(seeded, kb):
    rows, total = list_batches(seeded, page=1, page_size=50)
    assert _ids(rows) == set(kb.values()) and total == 5
    assert kb["unknown"] not in _ids(list_batches(seeded, page=1, page_size=50, kind="long")[0])
    assert kb["unknown"] not in _ids(list_batches(seeded, page=1, page_size=50, kind="short")[0])


def test_total_is_exact_with_paging(seeded, kb):
    rows, total = list_batches(seeded, page=1, page_size=1, kind="long")
    assert len(rows) == 1 and total == 3
    assert len(list_batches(seeded, page=3, page_size=1, kind="long")[0]) == 1
    assert list_batches(seeded, page=4, page_size=1, kind="long")[0] == []


def test_kind_and_date_range(seeded, kb):
    rows, total = list_batches(seeded, page=1, page_size=50, date_from=D, date_to=D, kind="long")
    assert _ids(rows) == {kb["long"], kb["mixed"]} and total == 2   # old_long 은 기간 밖


def test_kind_counts_and_item_video_kind(seeded, kb):
    rows, _ = list_batches(seeded, page=1, page_size=50)
    kc = kind_counts_for(seeded, rows)
    assert kc[kb["long"]] == {"long": 2, "short": 0, "unknown": 0}
    assert kc[kb["short"]] == {"long": 0, "short": 1, "unknown": 0}
    assert kc[kb["mixed"]] == {"long": 1, "short": 1, "unknown": 1}
    assert kc[kb["unknown"]] == {"long": 0, "short": 0, "unknown": 1}
    mixed = next(b for b in rows if b.id == kb["mixed"])
    d = batch_dict(seeded, mixed)
    assert d["kind_counts"] == {"long": 1, "short": 1, "unknown": 1}
    assert {i["video_id"]: i["video_kind"] for i in d["items"]} == {"KLONG000001": "long", "KSHORT00001": "short", "KUNKN000001": None}
    assert batch_dict(seeded, mixed, with_items=False)["kind_counts"]["short"] == 1


def test_kind_counts_for_uses_constant_queries(seeded, kb):
    from sqlalchemy import event
    rows, _ = list_batches(seeded, page=1, page_size=50)
    n = []
    eng = seeded.get_bind()
    f = lambda *a, **k: n.append(1)  # noqa: E731
    event.listen(eng, "before_cursor_execute", f)
    try:
        kind_counts_for(seeded, rows)
    finally:
        event.remove(eng, "before_cursor_execute", f)
    assert len(n) == 1


def test_api_kind_query(api, csrf, kb, factory):
    r = api.get("/api/v1/batches", params={"kind": "short"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert {b["id"] for b in j["items"]} == {kb["short"], kb["mixed"]} and j["total"] == 2
    assert {b["id"]: b["kind_counts"] for b in j["items"]}[kb["mixed"]] == {"long": 1, "short": 1, "unknown": 1}
    assert api.get("/api/v1/batches", params={"kind": "x"}).status_code == 422
    d = api.get(f"/api/v1/batches/{kb['mixed']}").json()
    assert sorted(str(i["video_kind"]) for i in d["items"]) == ["None", "long", "short"]
    assert api.get("/api/v1/batches", params={"kind": "long", "date_from": "2026-10-10", "date_to": "2026-10-10"}).json()["total"] == 2
