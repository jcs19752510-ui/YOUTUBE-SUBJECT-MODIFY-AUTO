"""M2 단위 2 시험(TC-M2-020~): 구글 연결 API. 실제 구글에는 접속하지 않고 가짜 응답을 쓴다."""
from __future__ import annotations

import json
import urllib.parse

import pytest

from tests.conftest import ORIGIN
from tests.domain.conftest import hdr
from ytweb.routers.google import GoogleCtx
from ytweb.youtube import google_oauth as oauth


@pytest.fixture
def gctx(api, tmp_path):
    calls = []

    def http(url, form):
        calls.append(form)
        return {"access_token": "AT-secret", "refresh_token": "RT-secret", "expires_in": 3600, "scope": oauth.SCOPE_READ}

    client = tmp_path / "google_client.json"
    ctx = GoogleCtx(pending=oauth.PendingAuth(), store=oauth.TokenStore(tmp_path / "tok" / "google_token.json"), http=http,
                    client_file=client, redirect_uri=ORIGIN + "/api/v1/google/callback")
    ctx.calls = calls  # type: ignore[attr-defined]
    api.app.state.google_ctx = ctx
    return ctx


def _with_client(ctx):
    ctx.client_file.write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "csec"}}), encoding="utf-8")


def _start(api, csrf, ctx):
    r = api.post("/api/v1/google/connect", headers=hdr(csrf))
    assert r.status_code == 200
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r.json()["auth_url"]).query)
    return q


def test_tc_m2_020_status_without_client_is_demo(api, csrf, gctx):
    s = api.get("/api/v1/google/status").json()
    assert s["mode"] == "demo" and s["connected"] is False and s["client_ready"] is False and "google_client.json" in s["message"]


def test_tc_m2_021_status_with_client_is_ready_not_connected(api, csrf, gctx):
    _with_client(gctx)
    s = api.get("/api/v1/google/status").json()
    assert (s["mode"], s["connected"], s["client_ready"]) == ("read", False, True)


def test_tc_m2_022_connect_requires_csrf_and_session(api, csrf, gctx):
    _with_client(gctx)
    assert api.post("/api/v1/google/connect", headers={"Origin": ORIGIN}).status_code in (401, 403)
    assert api.post("/api/v1/google/disconnect", headers={"Origin": ORIGIN}).status_code in (401, 403)


def test_tc_m2_023_connect_returns_read_only_auth_url_and_audits(api, csrf, gctx):
    _with_client(gctx)
    q = _start(api, csrf, gctx)
    assert q["scope"] == [oauth.SCOPE_READ] and q["client_id"] == ["cid"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == [ORIGIN + "/api/v1/google/callback"]
    audit_items = api.get("/api/v1/audit?page_size=200").json()["items"]
    assert any(a["action"] == "google.connect.start" for a in audit_items)


def test_tc_m2_024_connect_without_client_file_is_409_korean(api, csrf, gctx):
    r = api.post("/api/v1/google/connect", headers=hdr(csrf))
    assert r.status_code == 409 and "google_client.json" in json.dumps(r.json(), ensure_ascii=False)


def test_tc_m2_025_full_login_flow_saves_token_and_hides_it(api, csrf, gctx):
    _with_client(gctx)
    q = _start(api, csrf, gctx)
    api.cookies.clear()  # 구글에서 돌아올 때는 세션 쿠키가 없다
    r = api.get(f"/api/v1/google/callback?code=THECODE&state={q['state'][0]}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/#/"
    body = r.text + json.dumps(dict(r.headers))
    assert "RT-secret" not in body and "AT-secret" not in body and "THECODE" not in r.headers["location"]
    assert gctx.calls[0]["code"] == "THECODE" and gctx.calls[0]["code_verifier"] and gctx.calls[0]["client_secret"] == "csec"
    assert gctx.store.load()["refresh_token"] == "RT-secret"
    from tests.conftest import login
    login(api)
    s = api.get("/api/v1/google/status").json()
    assert s["connected"] is True and s["last_error"] is None
    audit_text = json.dumps(api.get("/api/v1/audit?page_size=200").json())
    assert "RT-secret" not in audit_text and "AT-secret" not in audit_text and "google.connected" in audit_text


def test_tc_m2_026_wrong_state_never_exchanges_code(api, csrf, gctx):
    _with_client(gctx)
    api.cookies.clear()
    r = api.get("/api/v1/google/callback?code=X&state=forged", follow_redirects=False)
    assert r.status_code == 303 and gctx.calls == [] and gctx.store.load() is None
    from tests.conftest import login
    login(api)
    s = api.get("/api/v1/google/status").json()
    assert s["last_error"] and "만료" in s["last_error"]
    assert api.get("/api/v1/google/status").json()["last_error"] is None  # 한 번만 보여 줌


def test_tc_m2_027_state_cannot_be_reused(api, csrf, gctx):
    _with_client(gctx)
    q = _start(api, csrf, gctx)
    api.cookies.clear()
    url = f"/api/v1/google/callback?code=C&state={q['state'][0]}"
    api.get(url, follow_redirects=False)
    api.get(url, follow_redirects=False)
    assert len(gctx.calls) == 1


def test_tc_m2_028_user_denied_login_saves_nothing(api, csrf, gctx):
    _with_client(gctx)
    q = _start(api, csrf, gctx)
    api.cookies.clear()
    r = api.get(f"/api/v1/google/callback?error=access_denied&state={q['state'][0]}", follow_redirects=False)
    assert r.status_code == 303 and gctx.calls == [] and gctx.store.load() is None


def test_tc_m2_029_google_token_error_saves_nothing(api, csrf, gctx):
    _with_client(gctx)
    gctx.http = lambda u, f: {"error": "invalid_grant"}
    q = _start(api, csrf, gctx)
    api.cookies.clear()
    api.get(f"/api/v1/google/callback?code=C&state={q['state'][0]}", follow_redirects=False)
    assert gctx.store.load() is None


def test_tc_m2_030_disconnect_clears_token(api, csrf, gctx):
    _with_client(gctx)
    gctx.store.save({"access_token": "a", "refresh_token": "r", "expires_at": "2026-01-01T00:00:00+00:00"})
    assert api.get("/api/v1/google/status").json()["connected"] is True
    assert api.post("/api/v1/google/disconnect", headers=hdr(csrf)).json() == {"connected": False}
    assert gctx.store.load() is None and api.get("/api/v1/google/status").json()["connected"] is False


def test_tc_m2_031_oversized_callback_params_rejected(api, csrf, gctx):
    api.cookies.clear()
    assert api.get("/api/v1/google/callback?code=" + "a" * 3000 + "&state=x", follow_redirects=False).status_code == 422
