"""M3 단위 2 시험(TC-M3-010~): 쓰기 로그인 API와 게이트웨이 선택. 실제 구글에는 접속하지 않는다."""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import ORIGIN
from tests.domain.conftest import hdr
from ytweb.db.models import Video
from ytweb.domain import live_gateway as lg
from ytweb.routers.google import GoogleCtx
from ytweb.youtube import google_oauth as oauth
from ytweb.youtube.base import GatewayError
from ytweb.youtube.mock import MockYouTubeGateway

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def gctx(api, tmp_path):
    def http(url, form):
        return {"access_token": "AT-w", "refresh_token": "RT-w", "expires_in": 3600, "scope": oauth.SCOPE_WRITE}

    ctx = GoogleCtx(pending=oauth.PendingAuth(), store=oauth.TokenStore(tmp_path / "t" / "google_token.json"), http=http,
                    client_file=tmp_path / "google_client.json", redirect_uri=ORIGIN + "/api/v1/google/callback",
                    write_store=oauth.TokenStore(tmp_path / "t" / lg.WRITE_TOKEN_FILE))
    ctx.client_file.write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "csec"}}), encoding="utf-8")
    api.app.state.google_ctx = ctx
    return ctx


def _q(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def test_tc_m3_010_connect_write_uses_write_scope_and_saves_to_write_store(api, csrf, gctx):
    r = api.post("/api/v1/google/connect-write", headers=hdr(csrf))
    assert r.status_code == 200
    q = _q(r.json()["auth_url"])
    assert q["scope"] == [oauth.SCOPE_WRITE]
    api.get(f"/api/v1/google/callback?code=C&state={q['state'][0]}", follow_redirects=False)
    assert gctx.write_store.load() and gctx.store.load() is None  # 읽기 토큰 파일은 건드리지 않는다
    s = api.get("/api/v1/google/status").json()
    assert s["write_connected"] is True and s["live_write_ready"] is False and s["connected"] is False


def test_tc_m3_011_read_connect_still_saves_read_store(api, csrf, gctx):
    q = _q(api.post("/api/v1/google/connect", headers=hdr(csrf)).json()["auth_url"])
    assert q["scope"] == [oauth.SCOPE_READ]
    api.get(f"/api/v1/google/callback?code=C&state={q['state'][0]}", follow_redirects=False)
    assert gctx.store.load() and gctx.write_store.load() is None


def test_tc_m3_012_disconnect_clears_both_tokens(api, csrf, gctx):
    gctx.store.save({"access_token": "a", "refresh_token": "r", "expires_at": "x"})
    gctx.write_store.save({"access_token": "a", "refresh_token": "r", "expires_at": "x"})
    assert api.post("/api/v1/google/disconnect", headers=hdr(csrf)).status_code == 200
    assert gctx.store.load() is None and gctx.write_store.load() is None


def test_tc_m3_013_forged_state_for_write_does_nothing(api, csrf, gctx):
    api.get("/api/v1/google/callback?code=C&state=forged", follow_redirects=False)
    assert gctx.write_store.load() is None


def _write_token(sd):
    oauth.TokenStore(sd / lg.WRITE_TOKEN_FILE).save({"access_token": "AT", "refresh_token": "RT", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})


def _client(tmp_path):
    f = tmp_path / "client.json"
    f.write_text(json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    return str(f)


def test_tc_m3_020_select_gateway_requires_all_three(db, tmp_path):
    _write_token(tmp_path)
    base = {"YTWEB_GOOGLE_CLIENT_FILE": _client(tmp_path)}
    for env in ({**base}, {**base, "YTWEB_LIVE_WRITE": "1"}, {**base, "YTWEB_LIVE_ALLOWED_VIDEOS": "abcdefghijk"},
                {**base, "YTWEB_LIVE_WRITE": "0", "YTWEB_LIVE_ALLOWED_VIDEOS": "abcdefghijk"}):
        assert isinstance(lg.select_gateway(db, NOW, tmp_path, env), MockYouTubeGateway), env
    ok = {**base, "YTWEB_LIVE_WRITE": "1", "YTWEB_LIVE_ALLOWED_VIDEOS": "abcdefghijk, zzzzzzzzzzz"}
    assert isinstance(lg.select_gateway(db, NOW, tmp_path, ok), lg.SyncedLiveGateway)
    assert lg.allowed_videos(ok) == {"abcdefghijk", "zzzzzzzzzzz"}


def test_tc_m3_021_no_write_token_falls_back_to_mock(db, tmp_path):
    env = {"YTWEB_GOOGLE_CLIENT_FILE": _client(tmp_path), "YTWEB_LIVE_WRITE": "1", "YTWEB_LIVE_ALLOWED_VIDEOS": "abcdefghijk"}
    assert isinstance(lg.select_gateway(db, NOW, tmp_path, env), MockYouTubeGateway)


class _FakeLive:
    def __init__(self, out=None, err=None):
        self.out, self.err = out, err

    def read_snippet(self, vid):
        return {"title": "x"}

    def update_snippet(self, vid, body):
        if self.err:
            raise self.err
        return self.out


def test_tc_m3_030_synced_gateway_mirrors_confirmed_title_to_db(db, seeded):
    v = db.query(Video).first()
    out = {"title": "새 제목입니다", "categoryId": "22", "description": "설명"}
    g = lg.SyncedLiveGateway(db, _FakeLive(out=out), NOW)
    g.update_snippet(v.video_id, {"id": v.video_id, "snippet": out})
    db.refresh(v)
    assert v.title == "새 제목입니다" and v.snippet == out and v.category_id == "22"


def test_tc_m3_031_synced_gateway_does_not_touch_db_on_error(db, seeded):
    v = db.query(Video).first()
    before = v.title
    g = lg.SyncedLiveGateway(db, _FakeLive(err=GatewayError("forbidden", "거부")), NOW)
    with pytest.raises(GatewayError):
        g.update_snippet(v.video_id, {})
    db.refresh(v)
    assert v.title == before
