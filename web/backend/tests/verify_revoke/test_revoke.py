"""연결 해제 시 구글에 토큰 폐기(revoke) 요청. 가짜 urlopen 만 쓰며 실제 구글에는 접속하지 않는다."""
from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request

import pytest

from tests.conftest import ORIGIN
from tests.domain.conftest import hdr
from ytweb.routers.google import GoogleCtx
from ytweb.youtube import google_oauth as oauth

TOK = {"access_token": "AT-FAKE-1", "refresh_token": "RT-FAKE-1", "expires_at": "2026-01-01T00:00:00+00:00"}
WTOK = {"access_token": "AT-FAKE-W", "refresh_token": "RT-FAKE-W", "expires_at": "2026-01-01T00:00:00+00:00"}


class _Resp:
    def __init__(self, status): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return b"{}"


@pytest.fixture
def rec(monkeypatch):
    """behavior: 'ok' | 400 | 500 | 'timeout' | 'conn'. rec.calls = [(Request, timeout)]"""
    class R:
        calls: list = []
        behavior: object = "ok"
    r = R(); r.calls = []

    def fake(req, *a, timeout=None, **k):
        r.calls.append((req, timeout))
        b = r.behavior
        if b == "ok": return _Resp(200)
        if b == "timeout": raise socket.timeout("timed out RT-FAKE-1")
        if b == "conn": raise urllib.error.URLError("refused RT-FAKE-1")
        raise urllib.error.HTTPError(req.full_url, b, "err RT-FAKE-1", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return r


@pytest.fixture
def gctx(api, tmp_path):
    client = tmp_path / "google_client.json"
    ctx = GoogleCtx(pending=oauth.PendingAuth(), store=oauth.TokenStore(tmp_path / "t" / "google_token.json"),
                    http=lambda u, f: {}, client_file=client, redirect_uri=ORIGIN + "/api/v1/google/callback",
                    write_store=oauth.TokenStore(tmp_path / "t" / "google_write_token.json"))
    api.app.state.google_ctx = ctx
    return ctx


def _client(ctx):
    ctx.client_file.write_text(json.dumps({"installed": {"client_id": "c", "client_secret": "s"}}), encoding="utf-8")


def _disc(api, csrf):
    return api.post("/api/v1/google/disconnect", headers=hdr(csrf))


def _body(req): return urllib.parse.parse_qs(req.data.decode())


@pytest.mark.parametrize("beh,expect", [("ok", True), (400, False), (500, False), ("timeout", False), ("conn", False)])
def test_read_token_revoke_outcomes(api, csrf, gctx, rec, beh, expect):
    _client(gctx); gctx.store.save(TOK); rec.behavior = beh
    r = _disc(api, csrf)
    assert r.status_code == 200
    assert r.json() == {"connected": False, "revoked": expect}
    assert gctx.store.load() is None and not gctx.store.path.exists()
    assert len(rec.calls) == 1


def test_request_shape(api, csrf, gctx, rec):
    _client(gctx); gctx.store.save(TOK)
    _disc(api, csrf)
    req, timeout = rec.calls[0]
    assert req.full_url == "https://oauth2.googleapis.com/revoke" and req.get_method() == "POST"
    assert req.get_header("Content-type") == "application/x-www-form-urlencoded"
    assert _body(req) == {"token": ["RT-FAKE-1"]}  # refresh_token 우선
    assert timeout == 5


def test_no_redirect_following(api, csrf, gctx, rec):
    h = [x for x in urllib.request._opener.handlers if isinstance(x, oauth._NoRedirect)]
    assert h and h[0].redirect_request(None) is None


def test_access_token_used_when_no_refresh(rec):
    assert oauth.revoke_token({"access_token": "AT-ONLY"}) is True
    assert _body(rec.calls[0][0]) == {"token": ["AT-ONLY"]}
    assert oauth.revoke_token({}) is False and oauth.revoke_token(None) is False and len(rec.calls) == 1


def test_write_token_only_and_both(api, csrf, gctx, rec):
    _client(gctx); gctx.write_store.save(WTOK)
    r = _disc(api, csrf).json()
    assert r["revoked"] is True and len(rec.calls) == 1 and _body(rec.calls[0][0]) == {"token": ["RT-FAKE-W"]}
    assert gctx.write_store.load() is None
    gctx.store.save(TOK); gctx.write_store.save(WTOK); rec.calls.clear()
    r = _disc(api, csrf).json()
    assert r["revoked"] is True and [_body(c[0])["token"][0] for c in rec.calls] == ["RT-FAKE-1", "RT-FAKE-W"]
    assert gctx.store.load() is None and gctx.write_store.load() is None


def test_one_of_two_fails_is_false_but_both_deleted(api, csrf, gctx, monkeypatch, rec):
    _client(gctx); gctx.store.save(TOK); gctx.write_store.save(WTOK)
    n = {"i": 0}
    def fake(req, *a, timeout=None, **k):
        n["i"] += 1
        if n["i"] == 2: raise urllib.error.URLError("x")
        return _Resp(200)
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    r = _disc(api, csrf).json()
    assert r == {"connected": False, "revoked": False}
    assert gctx.store.load() is None and gctx.write_store.load() is None


def test_local_deleted_before_network_call(api, csrf, gctx, monkeypatch):
    _client(gctx); gctx.store.save(TOK)
    seen = {}
    def fake(req, *a, **k):
        seen["exists"] = gctx.store.path.exists()
        return _Resp(200)
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    _disc(api, csrf)
    assert seen == {"exists": False}


def test_no_token_no_call(api, csrf, gctx, rec):
    _client(gctx)
    r = _disc(api, csrf)
    assert r.status_code == 200 and r.json() == {"connected": False, "revoked": None} and rec.calls == []


def test_demo_no_client_file_no_call(api, csrf, gctx, rec):
    gctx.store.save(TOK)  # 클라이언트 파일 없음(데모)
    r = _disc(api, csrf)
    assert r.json() == {"connected": False, "revoked": None} and rec.calls == []
    assert gctx.store.load() is None


def test_tokens_not_leaked(api, csrf, gctx, rec, caplog):
    _client(gctx); gctx.store.save(TOK); gctx.write_store.save(WTOK); rec.behavior = 500
    with caplog.at_level(logging.DEBUG):
        r = _disc(api, csrf)
    blob = r.text + caplog.text
    audit_text = json.dumps(api.get("/api/v1/audit?page_size=200").json())
    for s in ("RT-FAKE", "AT-FAKE"):
        assert s not in blob and s not in audit_text
    items = api.get("/api/v1/audit?page_size=200").json()["items"]
    disc = [a for a in items if a["action"] == "google.disconnected"]
    assert disc and "false" in json.dumps(disc[0]).lower()


def test_revoke_token_never_raises_or_leaks(monkeypatch):
    def boom(*a, **k): raise RuntimeError("RT-FAKE-1")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert oauth.revoke_token(TOK) is False
