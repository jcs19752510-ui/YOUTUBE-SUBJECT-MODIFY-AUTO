"""M2 단위 3 시험(TC-M2-040~): 내 채널 영상 읽기와 가져오기. 실제 구글에는 접속하지 않고 가짜 응답을 쓴다."""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from ytweb.core.errors import ProblemError
from ytweb.db.models import MetricsSnapshot, Suggestion, Video
from ytweb.domain import handlers
from ytweb.domain.live_sync import purge_pristine_demo, sync_live
from ytweb.youtube import google_oauth as oauth
from ytweb.youtube import live_read as lr
from ytweb.youtube.base import GatewayError

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def vid(n: int) -> str:
    return f"vid{n:08d}"[:11]


def item(n: int, *, title=None, dur="PT10M5S", privacy="public", views="1234", desc="설명 내용"):
    return {"id": vid(n), "snippet": {"title": title or f"내 영상 {n}", "description": desc, "categoryId": "26", "liveBroadcastContent": "none", "tags": ["a"]},
            "contentDetails": {"duration": dur}, "status": {"privacyStatus": privacy, "madeForKids": False}, "statistics": {"viewCount": views}}


class FakeYT:
    """채널 1개, 업로드 재생목록 2쪽(3개+3개, 1개 중복), videos.list 응답."""

    def __init__(self, items=None, pages=None, uploads="UUx"):
        self.items = {it["id"]: it for it in (items or [item(i) for i in range(1, 6)])}
        self.pages = pages or [[vid(1), vid(2), vid(3)], [vid(3), vid(4), vid(5)]]
        self.uploads, self.calls, self.tokens = uploads, [], []

    def __call__(self, url, token):
        self.tokens.append(token)
        u = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        name = u.path.rsplit("/", 1)[-1]
        self.calls.append(name)
        if name == "channels":
            return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": self.uploads}}}] if self.uploads else []}
        if name == "playlistItems":
            idx = int(q.get("pageToken", "0") or 0)
            body = {"items": [{"contentDetails": {"videoId": v}} for v in self.pages[idx]]}
            if idx + 1 < len(self.pages):
                body["nextPageToken"] = str(idx + 1)
            return body
        if name == "videos":
            return {"items": [self.items[i] for i in q["id"].split(",") if i in self.items]}
        raise AssertionError(name)


def reader(fake):
    return lr.YouTubeReader(lambda: "TOKEN", fake)


def test_tc_m2_040_parse_duration():
    assert lr.parse_duration("PT4M13S") == 253 and lr.parse_duration("PT1H2M3S") == 3723
    assert lr.parse_duration("P1DT1H") == 90000 and lr.parse_duration("PT0S") == 0
    for bad in ("PT", "P", "abc", None, 5, ""):
        assert lr.parse_duration(bad) is None


def test_tc_m2_041_to_video_fields_maps_and_rejects_malformed():
    f = lr.to_video_fields(item(1, views="99"))
    assert f["video_id"] == vid(1) and f["source"] == "youtube" and f["views"] == 99 and f["duration_sec"] == 605
    assert f["privacy_status"] == "public" and f["snippet"]["tags"] == ["a"] and f["description_excerpt"] == "설명 내용"
    assert lr.to_video_fields({"id": "short", "snippet": {"title": "x"}}) is None
    assert lr.to_video_fields({"id": vid(1), "snippet": {}}) is None
    assert lr.to_video_fields({"id": vid(1)}) is None
    assert lr.to_video_fields(item(1, views="not-a-number"))["views"] is None


def test_tc_m2_042_fetch_all_follows_pages_dedupes_and_sends_token():
    fake = FakeYT()
    rows = reader(fake).fetch_all()
    assert [r["video_id"] for r in rows] == [vid(i) for i in range(1, 6)]
    assert fake.calls == ["channels", "playlistItems", "playlistItems", "videos"] and set(fake.tokens) == {"TOKEN"}


def test_tc_m2_043_videos_are_requested_in_batches_of_50():
    n = 120
    fake = FakeYT(items=[item(i) for i in range(1, n + 1)], pages=[[vid(i) for i in range(1, n + 1)]])
    rows = reader(fake).fetch_all()
    assert len(rows) == n and fake.calls.count("videos") == 3


def test_tc_m2_044_no_channel_is_a_korean_error():
    with pytest.raises(GatewayError) as e:
        reader(FakeYT(uploads="")).fetch_all()
    assert e.value.code == "no_channel" and "채널" in e.value.message


def test_tc_m2_045_playlist_pages_are_capped():
    class Loop(FakeYT):
        def __call__(self, url, token):
            if "playlistItems" in url:
                self.calls.append("playlistItems")
                return {"items": [{"contentDetails": {"videoId": vid(1)}}], "nextPageToken": "again"}
            return super().__call__(url, token)

    fake = Loop()
    list(reader(fake).video_ids("UU"))
    assert fake.calls.count("playlistItems") == lr.MAX_PAGES


def test_tc_m2_046_access_token_fresh_stale_and_missing(tmp_path):
    client = tmp_path / "c.json"
    client.write_text(json.dumps({"installed": {"client_id": "A", "client_secret": "B"}}), encoding="utf-8")
    store = oauth.TokenStore(tmp_path / "t.json")
    posts = []

    def post(url, form):
        posts.append(form)
        return {"access_token": "NEW", "expires_in": 3600}

    acc = lr.GoogleAccess(client, store, post)
    assert acc.connected() is False
    with pytest.raises(GatewayError) as e:
        acc.access_token(NOW)
    assert e.value.code == "not_connected"
    store.save({"access_token": "OLD", "refresh_token": "RT", "expires_at": (NOW + timedelta(hours=1)).isoformat()})
    assert acc.connected() is True and acc.access_token(NOW) == "OLD" and posts == []
    assert acc.access_token(NOW + timedelta(hours=2)) == "NEW" and posts[0]["refresh_token"] == "RT"
    assert store.load()["access_token"] == "NEW" and store.load()["refresh_token"] == "RT"


def test_tc_m2_047_refresh_failure_becomes_unauthorized(tmp_path):
    client = tmp_path / "c.json"
    client.write_text(json.dumps({"installed": {"client_id": "A", "client_secret": "B"}}), encoding="utf-8")
    store = oauth.TokenStore(tmp_path / "t.json")
    store.save({"access_token": "OLD", "refresh_token": "RT", "expires_at": NOW.isoformat()})
    acc = lr.GoogleAccess(client, store, lambda u, f: {"error": "invalid_grant"})
    with pytest.raises(GatewayError) as e:
        acc.access_token(NOW + timedelta(hours=1))
    assert e.value.code == "unauthorized" and "다시 로그인" in e.value.message


def test_tc_m2_048_default_http_get_refuses_non_https():
    with pytest.raises(GatewayError) as e:
        lr.default_http_get("http://www.googleapis.com/youtube/v3/channels", "T")
    assert e.value.code == "insecure_url"


def test_tc_m2_049_sync_inserts_youtube_rows_with_exclusions_and_is_idempotent(db, env):
    items = [item(1), item(2, dur="PT45S"), item(3, privacy="private"), item(4)]
    fake = FakeYT(items=items, pages=[[vid(1), vid(2), vid(3), vid(4)]])
    r = sync_live(db, reader(fake), NOW, env.policy)
    db.commit()
    assert (r.created, r.updated, r.total, r.demo_removed) == (4, 0, 4, 0)
    rows = {v.video_id: v for v in db.execute(select(Video)).scalars()}
    assert all(v.source == "youtube" for v in rows.values())
    assert rows[vid(2)].is_short is True and rows[vid(2)].exclusion_reasons
    assert rows[vid(3)].exclusion_reasons and not rows[vid(1)].exclusion_reasons
    r2 = sync_live(db, reader(FakeYT(items=[item(1, title="바뀐 제목")], pages=[[vid(1)]])), NOW, env.policy)
    db.commit()
    assert (r2.created, r2.updated) == (0, 1) and db.get(Video, vid(1)).title == "바뀐 제목"


def test_tc_m2_050_pristine_demo_is_removed_before_live_sync(seeded, env):
    demo = seeded.execute(select(Video.video_id).where(Video.source == "demo")).scalars().all()
    assert demo and seeded.execute(select(MetricsSnapshot)).scalars().first() is not None
    r = sync_live(seeded, reader(FakeYT()), NOW, env.policy)
    seeded.commit()
    assert r.demo_removed == len(demo)
    assert not seeded.execute(select(Video).where(Video.source == "demo")).scalars().all()
    assert not seeded.execute(select(MetricsSnapshot).where(MetricsSnapshot.source == "demo")).scalars().all()
    assert seeded.execute(select(Video).where(Video.source == "youtube")).scalars().all()


def test_tc_m2_051_demo_with_history_blocks_live_sync_and_keeps_data(seeded, env, gw):
    first = seeded.execute(select(Video).where(Video.source == "demo")).scalars().first()
    seeded.add(Suggestion(video_id=first.video_id, title="기록 있는 제안", evidence="e", source="manual", topic="life", status="candidate", created_at=NOW, updated_at=NOW))
    seeded.commit()
    before = seeded.execute(select(Video)).scalars().all()
    with pytest.raises(ProblemError) as e:
        sync_live(seeded, reader(FakeYT()), NOW, env.policy)
    assert e.value.code == "demo_data_in_use" and "reset-demo.ps1" in e.value.hint
    assert len(seeded.execute(select(Video)).scalars().all()) == len(before)


def test_tc_m2_052_purge_without_demo_is_noop(db):
    assert purge_pristine_demo(db) == 0


def test_tc_m2_053_job_handler_uses_live_when_connected_and_demo_otherwise(factory, monkeypatch, env):
    from ytweb.domain.common import set_default_env
    set_default_env(env)

    class Acc:
        def __init__(self, ok): self.ok = ok
        def connected(self): return self.ok
        def access_token(self, now=None): return "T"

    fake = FakeYT()
    monkeypatch.setattr(handlers, "YouTubeReader", lambda token: lr.YouTubeReader(token, fake))
    monkeypatch.setattr(handlers, "google_access_from_env", lambda d: Acc(True))
    monkeypatch.setattr(handlers, "_progress", lambda *a, **k: None)
    class J:  # 핸들러는 job.id 만 쓴다
        id = "j1"; payload = {}
    out = handlers.handle_videos_sync(factory, J())
    assert out["source"] == "youtube" and out["total"] == 5 and fake.tokens and set(fake.tokens) == {"T"}
    monkeypatch.setattr(handlers, "google_access_from_env", lambda d: Acc(False))
    out2 = handlers.handle_videos_sync(factory, J())
    assert out2.get("source") != "youtube"  # 데모 시드 경로


def test_tc_live_sync_refreshes_a_video_changed_by_the_program_and_by_hand_but_not_one_in_flight(db, env):
    """선생님이 Studio 에서 직접 바꾼 제목이 [내 영상 불러오기]로 들어와야 한다(2026-10-12 PC 실측). 반영 진행 중(planned)인 영상만 예외."""
    from ytweb.db.models import Change

    sync_live(db, reader(FakeYT(items=[item(1), item(2)], pages=[[vid(1), vid(2)]])), NOW, env.policy)
    for n, result in ((1, "success"), (2, "planned")):
        db.add(Change(video_id=vid(n), change_type="apply", previous_title="옛", new_title="새", result=result, mode="demo", created_at=NOW))
    db.commit()
    sync_live(db, reader(FakeYT(items=[item(1, title="손으로 바꾼 제목 1"), item(2, title="손으로 바꾼 제목 2")], pages=[[vid(1), vid(2)]])), NOW, env.policy)
    db.commit()
    v1, v2 = db.get(Video, vid(1)), db.get(Video, vid(2))
    assert v1.title == "손으로 바꾼 제목 1" and v1.snippet["title"] == "손으로 바꾼 제목 1"  # 제목과 snippet 이 함께 갱신(승인 때 일관성 검사 통과)
    assert v2.title == "내 영상 2"  # 진행 중인 영상은 그대로
