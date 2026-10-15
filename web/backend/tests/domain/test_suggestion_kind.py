"""제안 목록 응답의 video_kind(롱폼/쇼츠/불명). 영상 정보는 영상 테이블 한 번의 조회로 가져온다."""
from __future__ import annotations

from sqlalchemy import event

from ytweb.db.models import Video
from ytweb.domain.serialize import suggestion_kinds
from tests.domain.helpers import eligible_video_ids, suggest


def _setup(db, env, clock):
    a, b, c = eligible_video_ids(db, 3)
    for vid in (a, b, c):  # 제안은 제외 대상이 아닌 상태에서 만들고, 그 뒤 영상 길이·쇼츠 여부를 바꾼다
        suggest(db, env, clock(), vid, 1)
    for vid, short, dur in ((a, False, 600), (b, True, 30), (c, False, None)):
        v = db.get(Video, vid)
        v.is_short, v.duration_sec = short, dur
    db.commit()
    return a, b, c


def test_response_has_video_kind_long_short_unknown(seeded, db, env, clock, api, csrf):
    a, b, c = _setup(db, env, clock)
    r = api.get("/api/v1/suggestions?page_size=200")
    assert r.status_code == 200, r.text
    by = {i["video_id"]: i["video_kind"] for i in r.json()["items"]}
    assert by[a] == "long"
    assert by[b] == "short"
    assert by[c] is None


def test_kinds_use_one_video_query(seeded, db, env, clock):
    _setup(db, env, clock)
    from ytweb.db.models import Suggestion
    from sqlalchemy import select
    rows = list(db.execute(select(Suggestion)).scalars())
    assert len(rows) >= 3
    n = []
    eng = db.get_bind()
    def cnt(*a, **k): n.append(1)
    event.listen(eng, "before_cursor_execute", cnt)
    try:
        kinds = suggestion_kinds(db, rows)
    finally:
        event.remove(eng, "before_cursor_execute", cnt)
    assert len(n) == 1
    assert set(kinds.values()) == {"long", "short", None}


def test_empty_list_has_no_query(db):
    assert suggestion_kinds(db, []) == {}
