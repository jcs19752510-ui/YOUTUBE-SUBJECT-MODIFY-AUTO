"""TC-VM-300~: domain/live_sync.py + videos.sync 핸들러(M2 단위 3) 독립 검증."""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from tests.verify_m23.conftest import connect_both, finish_flow, start_flow, hdr
from ytweb.core import jobs
from ytweb.core.errors import ProblemError
from ytweb.db.models import AuditLog, BatchItem, Change, MetricsSnapshot, Suggestion, Video
from ytweb.domain import handlers
from ytweb.domain.common import set_default_env
from ytweb.domain.live_sync import purge_pristine_demo, sync_live
from ytweb.domain.seed import seed_demo
from ytweb.domain.exclusions import exclusion_reasons
from ytweb.youtube.live_read import YouTubeReader

HANGUL = re.compile("[가-힣]")
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def vid(n):
    return f"ytvid{n:06d}"


def raw(n, *, dur="PT10M", privacy="public", kids=False, title=None, live="none", views="100"):
    return {"id": vid(n), "snippet": {"title": title or f"영상 제목 {n}", "categoryId": "26", "description": "설명", "liveBroadcastContent": live},
            "contentDetails": {"duration": dur}, "status": {"privacyStatus": privacy, "madeForKids": kids}, "statistics": {"viewCount": views}}


class Src:
    def __init__(self, items):
        self.items = {i["id"]: i for i in items}

    def __call__(self, url, token):
        if "/channels" in url:
            return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU"}}}]}
        if "/playlistItems" in url:
            return {"items": [{"contentDetails": {"videoId": k}} for k in self.items]}
        import urllib.parse
        ids = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["id"][0].split(",")
        return {"items": [self.items[i] for i in ids if i in self.items]}


def reader(*items):
    return YouTubeReader(lambda: "T", Src(items))


def test_tc_vm_300_new_videos_inserted_as_youtube_source_with_exclusions(db, env):
    r = sync_live(db, reader(raw(1), raw(2, privacy="private"), raw(3, kids=True)), NOW, env.policy)
    db.commit()
    assert (r.created, r.updated, r.total, r.demo_removed) == (3, 0, 3, 0)
    rows = {v.video_id: v for v in db.execute(select(Video)).scalars()}
    assert all(v.source == "youtube" for v in rows.values())
    assert rows[vid(1)].exclusion_reasons == [] and rows[vid(2)].exclusion_reasons and rows[vid(3)].exclusion_reasons
    assert rows[vid(1)].title == "영상 제목 1" and rows[vid(1)].views == 100


def test_tc_vm_301_shorts_boundary_uses_policy_seconds_inclusive(db, env):
    m = env.policy.shorts_max_seconds
    def d(sec):
        return f"PT{sec // 60}M{sec % 60}S"
    sync_live(db, reader(raw(1, dur=d(m)), raw(2, dur=d(m + 1)), raw(3, dur=d(m - 1))), NOW, env.policy)
    rows = {v.video_id: v for v in db.execute(select(Video)).scalars()}
    assert rows[vid(1)].is_short is True and rows[vid(2)].is_short is False and rows[vid(3)].is_short is True
    assert rows[vid(1)].exclusion_reasons and not rows[vid(2)].exclusion_reasons


def test_tc_vm_302_unknown_duration_is_not_short_but_excluded_by_policy_if_policy_says(db, env):
    sync_live(db, reader(raw(1, dur="garbage")), NOW, env.policy)
    v = db.get(Video, vid(1))
    assert v.duration_sec is None and v.is_short is False
    assert v.exclusion_reasons == exclusion_reasons(v, env.policy)        # 정책 함수와 항상 일치


def test_tc_vm_303_second_sync_is_idempotent_and_updates_views_only_counts(db, env):
    sync_live(db, reader(raw(1, views="100")), NOW, env.policy)
    r = sync_live(db, reader(raw(1, views="250")), NOW, env.policy)
    assert (r.created, r.updated) == (0, 1) and db.get(Video, vid(1)).views == 250
    assert db.execute(select(Video)).scalars().all().__len__() == 1


def test_tc_vm_304_remote_title_change_is_pulled_when_app_never_changed_it(db, env):
    sync_live(db, reader(raw(1, title="옛 제목")), NOW, env.policy)
    sync_live(db, reader(raw(1, title="유튜브에서 바뀐 제목")), NOW, env.policy)
    assert db.get(Video, vid(1)).title == "유튜브에서 바뀐 제목"


def test_tc_vm_305_video_with_change_history_keeps_stored_title_and_snippet_but_views_refresh(db, env):
    sync_live(db, reader(raw(1, title="앱이 바꾼 후 제목", views="1")), NOW, env.policy)
    v = db.get(Video, vid(1))
    snap = copy.deepcopy(v.snippet)
    db.add(Change(video_id=vid(1), change_type="apply", previous_title="x", new_title="앱이 바꾼 후 제목", result="success", mode="live", created_at=NOW))
    db.flush()
    sync_live(db, reader(raw(1, title="다른 제목", views="999")), NOW, env.policy)
    v = db.get(Video, vid(1))
    assert v.title == "앱이 바꾼 후 제목" and v.snippet == snap and v.views == 999


def test_tc_vm_306_empty_channel_syncs_zero_and_is_not_an_error(db, env):
    r = sync_live(db, reader(), NOW, env.policy)
    assert (r.created, r.updated, r.total) == (0, 0, 0)


def test_tc_vm_310_pristine_demo_removed_before_import_with_metrics(seeded, env):
    n = len(seeded.execute(select(Video)).scalars().all())
    assert n > 0 and seeded.execute(select(MetricsSnapshot)).scalars().first() is not None
    r = sync_live(seeded, reader(raw(1)), NOW, env.policy)
    seeded.commit()
    assert r.demo_removed == n and [v.video_id for v in seeded.execute(select(Video)).scalars()] == [vid(1)]
    assert seeded.execute(select(MetricsSnapshot)).scalars().first() is None


@pytest.mark.parametrize("kind", ["suggestion", "batch_item", "change"])
def test_tc_vm_311_demo_with_any_history_blocks_import_keeps_everything_with_korean_hint(seeded, env, kind):
    from ytweb.db.models import Batch
    v = seeded.execute(select(Video).order_by(Video.video_id)).scalars().first()
    s = Suggestion(video_id=v.video_id, title="새 제목 후보입니다", source="demo", created_at=NOW, updated_at=NOW)
    seeded.add(s)
    seeded.flush()
    if kind == "batch_item":
        b = Batch(status="draft", created_at=NOW, updated_at=NOW)
        seeded.add(b)
        seeded.flush()
        seeded.add(BatchItem(batch_id=b.id, suggestion_id=s.id, video_id=v.video_id, seq=1, status="pending", updated_at=NOW))
    elif kind == "change":
        seeded.add(Change(video_id=v.video_id, change_type="apply", previous_title="a", new_title="b", result="success", mode="demo", created_at=NOW))
    if kind != "suggestion":
        pass
    seeded.commit()
    before = seeded.execute(select(Video)).scalars().all().__len__()
    mets = seeded.execute(select(MetricsSnapshot)).scalars().all().__len__()
    with pytest.raises(ProblemError) as e:
        sync_live(seeded, reader(raw(1)), NOW, env.policy)
    assert e.value.status == 409 and e.value.code == "demo_data_in_use" and "reset-demo" in (e.value.hint or "") and HANGUL.search(e.value.hint)
    seeded.rollback()
    assert seeded.execute(select(Video)).scalars().all().__len__() == before
    assert seeded.execute(select(MetricsSnapshot)).scalars().all().__len__() == mets
    assert seeded.get(Video, vid(1)) is None                          # 부분 반영도 없음


def test_tc_vm_312_purge_without_demo_is_zero_and_never_touches_youtube_rows(db, env):
    sync_live(db, reader(raw(1)), NOW, env.policy)
    assert purge_pristine_demo(db) == 0 and db.get(Video, vid(1)) is not None


# ---------- 작업 핸들러 + 실제 배선(가짜 구글) ----------
def _job(factory, now):
    with factory() as s:
        j = jobs.enqueue(s, type="videos.sync", payload={}, now=now)
        s.commit()
        return s.get(type(j), j.id) if False else j.id


class JobStub:
    def __init__(self, i):
        self.id = i
        self.payload = {}


def test_tc_vm_320_handler_without_connection_stays_demo_and_makes_no_google_call(gapp, fg, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    out = handlers.handle_videos_sync(factory, JobStub(_job(factory, clock())))
    assert out["total"] > 0 and "source" not in out and fg.calls == []
    with factory() as s:
        assert {v.source for v in s.execute(select(Video)).scalars()} == {"demo"}


def test_tc_vm_321_handler_with_read_connection_imports_real_via_fake_google_only_get(gapp, csrf, fg, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    fg.videos = {vid(1): {"title": "구글 영상 1", "categoryId": "26", "description": "d"}, vid(2): {"title": "구글 영상 2", "categoryId": "22"}}
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect"))
    fg.calls.clear()
    out = handlers.handle_videos_sync(factory, JobStub(_job(factory, clock())))
    assert out["source"] == "youtube" and out["created"] == 2 and out["total"] == 2
    assert {c.method for c in fg.calls} == {"GET"} and all(c.auth.startswith("Bearer AT-READ") for c in fg.calls)
    with factory() as s:
        assert {v.video_id for v in s.execute(select(Video)).scalars()} == {vid(1), vid(2)}
        a = [r for r in s.execute(select(AuditLog)).scalars() if r.action == "videos.sync.live"]
        assert a and "AT-" not in json.dumps(a[0].detail)


def test_tc_vm_322_write_only_connection_does_not_count_as_read_connected(gapp, csrf, fg, factory, env, clock, monkeypatch):
    """쓰기 토큰만 있고 읽기 토큰이 없으면 영상 불러오기는 읽기 토큰 파일 기준이므로 데모 경로(구글 호출 0)여야 한다."""
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect-write"))
    fg.calls.clear()
    out = handlers.handle_videos_sync(factory, JobStub(_job(factory, clock())))
    assert "source" not in out and [c for c in fg.calls if "googleapis.com" in c.url and c.path != "/token"] == []


def test_tc_vm_323_google_failure_becomes_problem_with_korean_hint_and_no_partial_rows(gapp, csrf, fg, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect"))
    fg.quota_on_read = True
    with pytest.raises(ProblemError) as e:
        handlers.handle_videos_sync(factory, JobStub(_job(factory, clock())))
    assert e.value.status == 502 and HANGUL.search(e.value.hint or "") and HANGUL.search(e.value.detail or "")
    with factory() as s:
        assert s.execute(select(Video)).scalars().first() is None


def test_tc_vm_324_revoked_refresh_token_gives_korean_reconnect_guidance(gapp, csrf, fg, factory, env, clock, monkeypatch, web_settings):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect"))
    p = web_settings.secrets_dir / "google_token.json"
    t = json.loads(p.read_text())
    t["expires_at"] = "2020-01-01T00:00:00+00:00"
    p.write_text(json.dumps(t))
    fg.refresh.clear()                         # 구글 쪽에서 권한 철회
    with pytest.raises(ProblemError) as e:
        handlers.handle_videos_sync(factory, JobStub(_job(factory, clock())))
    assert HANGUL.search(e.value.detail or "") and "RT-" not in (e.value.detail or "") + (e.value.hint or "")
