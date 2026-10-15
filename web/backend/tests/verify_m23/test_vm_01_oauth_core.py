"""TC-VM-010~: google_oauth.py (M2 단위 1) 독립 검증 — PKCE·state·URL·클라이언트 파일·토큰 교환/갱신·토큰 저장소."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ytweb.youtube import google_oauth as oauth

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


class T:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


# ---------- PKCE / state ----------
def test_tc_vm_010_pkce_challenge_is_s256_of_verifier_and_verifier_long_enough():
    v, c = oauth.make_pkce()
    assert 43 <= len(v) <= 128                                   # RFC 7636 길이 규정
    assert c == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    assert "=" not in c and "+" not in c and "/" not in c
    assert oauth.make_pkce()[0] != v                               # 매번 다름


def test_tc_vm_011_state_is_256bit_unique_and_returns_matching_challenge():
    p = oauth.PendingAuth(T())
    states = {p.start()[0] for _ in range(15)}
    assert len(states) == 15 and all(len(s) >= 43 for s in states)  # token_urlsafe(32) = 43자 = 256비트
    st, ch = p.start()
    v = p.finish(st)
    assert base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode() == ch


def test_tc_vm_012_state_single_use():
    p = oauth.PendingAuth(T())
    st, _ = p.start()
    p.finish(st)
    with pytest.raises(oauth.OAuthError) as e:
        p.finish(st)
    assert e.value.code == "state_invalid"


@pytest.mark.parametrize("bad", [None, "", "x", "A" * 43, " ", "\x00", "a" * 5000])
def test_tc_vm_013_forged_or_empty_state_rejected(bad):
    p = oauth.PendingAuth(T())
    p.start()
    with pytest.raises(oauth.OAuthError) as e:
        p.finish(bad)
    assert e.value.code == "state_invalid" and any("가" <= ch <= "힣" for ch in e.value.message)


@pytest.mark.parametrize("age,ok", [(0, True), (599.999, True), (600, False), (601, False)])
def test_tc_vm_014_state_ttl_boundary_600s(age, ok):
    t = T()
    p = oauth.PendingAuth(t)
    st, _ = p.start()
    t.t += age
    if ok:
        assert p.finish(st)
    else:
        with pytest.raises(oauth.OAuthError):
            p.finish(st)


def test_tc_vm_015_pending_capped_at_20_oldest_evicted_not_newest():
    t = T()
    p = oauth.PendingAuth(t)
    sts = []
    for _ in range(21):
        sts.append(p.start()[0])
        t.t += 1
    assert len(p._items) == 20
    with pytest.raises(oauth.OAuthError):
        p.finish(sts[0])                  # 가장 오래된 것이 밀려남
    assert p.finish(sts[-1])              # 최신은 유효


def test_tc_vm_016_expired_entries_purged_on_next_start():
    t = T()
    p = oauth.PendingAuth(t)
    p.start()
    t.t += 601
    p.start()
    assert len(p._items) == 1


# ---------- auth URL ----------
def _q(url):
    return {k: v for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}


def test_tc_vm_020_auth_url_read_scope_only_and_no_secret():
    u = oauth.build_auth_url("cid", "http://127.0.0.1:8080/api/v1/google/callback", "ST", "CH")
    q = _q(u)
    assert u.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert q["scope"] == [oauth.SCOPE_READ] and "force-ssl" not in u
    assert q["code_challenge_method"] == ["S256"] and q["code_challenge"] == ["CH"] and q["state"] == ["ST"]
    assert q["response_type"] == ["code"] and q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert "client_secret" not in q and "code_verifier" not in q


def test_tc_vm_021_auth_url_write_scope_is_exactly_force_ssl_not_both():
    q = _q(oauth.build_auth_url("cid", "http://x/cb", "ST", "CH", scope=oauth.SCOPE_WRITE))
    assert q["scope"] == [oauth.SCOPE_WRITE] and oauth.SCOPE_READ not in q["scope"][0].split()


def test_tc_vm_022_auth_url_encodes_hostile_values():
    q = _q(oauth.build_auth_url("c&d=1", "http://x/cb?a=b&c", "s&t", "ch"))
    assert q["client_id"] == ["c&d=1"] and q["state"] == ["s&t"] and "d" not in q


# ---------- client file ----------
@pytest.mark.parametrize("payload,code", [
    (None, "client_missing"),
    ("{not json", "client_invalid"),
    ("[]", "client_invalid"),
    ('"str"', "client_invalid"),
    ('{"installed": {}}', "client_invalid"),
    ('{"installed": {"client_id": "a"}}', "client_invalid"),
    ('{"installed": {"client_id": "", "client_secret": "s"}}', "client_invalid"),
    ('{"installed": "x"}', "client_invalid"),
    ('{}', "client_invalid"),
])
def test_tc_vm_030_client_file_errors_have_korean_message(tmp_path, payload, code):
    f = tmp_path / "c.json"
    if payload is not None:
        f.write_text(payload, encoding="utf-8")
    with pytest.raises(oauth.OAuthError) as e:
        oauth.load_client(f)
    assert e.value.code == code and any("가" <= ch <= "힣" for ch in e.value.message)


def test_tc_vm_031_client_file_installed_and_web_accepted(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    assert oauth.load_client(f) == ("i", "s")
    f.write_text(json.dumps({"web": {"client_id": "w", "client_secret": "z"}}))
    assert oauth.load_client(f) == ("w", "z")


def test_tc_vm_032_client_error_never_contains_secret(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"installed": {"client_id": "", "client_secret": "TOP-SECRET-VALUE"}}))
    with pytest.raises(oauth.OAuthError) as e:
        oauth.load_client(f)
    assert "TOP-SECRET-VALUE" not in e.value.message and "TOP-SECRET-VALUE" not in str(e.value)


# ---------- 교환 / 갱신 ----------
def _http(resp, seen=None):
    def post(url, form):
        if seen is not None:
            seen.append((url, form))
        return resp
    return post


def test_tc_vm_040_exchange_sends_verifier_redirect_secret_and_returns_expiry():
    seen = []
    t = oauth.exchange_code(_http({"access_token": "A", "refresh_token": "R", "expires_in": 100, "scope": "S"}, seen), ("i", "s"), "CODE", "VER", "http://r", NOW)
    url, form = seen[0]
    assert url == oauth.TOKEN_URL and form["grant_type"] == "authorization_code" and form["code_verifier"] == "VER" and form["redirect_uri"] == "http://r"
    assert t["refresh_token"] == "R" and t["scope"] == "S"
    assert datetime.fromisoformat(t["expires_at"]) == NOW + timedelta(seconds=100)


@pytest.mark.parametrize("resp,code", [
    ({"error": "invalid_grant"}, "grant_invalid_grant"),
    ({"error": "access_denied"}, "grant_access_denied"),
    ({}, "grant_no_token"),
    ({"access_token": ""}, "grant_no_token"),
    ({"access_token": "A"}, "no_refresh"),
    ({"access_token": "A", "refresh_token": ""}, "no_refresh"),
])
def test_tc_vm_041_exchange_failure_modes(resp, code):
    with pytest.raises(oauth.OAuthError) as e:
        oauth.exchange_code(_http(resp), ("i", "s"), "C", "V", "http://r", NOW)
    assert e.value.code == code and any("가" <= ch <= "힣" for ch in e.value.message)
    assert "access_denied" not in e.value.message and "invalid_grant" not in e.value.message   # 영문 오류 코드를 사용자에게 노출하지 않는다


def test_tc_vm_042_refresh_keeps_old_refresh_token_when_google_omits_it():
    seen = []
    old = {"access_token": "old", "refresh_token": "RT-OLD", "expires_at": "x"}
    t = oauth.refresh_tokens(_http({"access_token": "NEW", "expires_in": 60}, seen), ("i", "s"), old, NOW)
    assert seen[0][1]["grant_type"] == "refresh_token" and seen[0][1]["refresh_token"] == "RT-OLD"
    assert t["access_token"] == "NEW" and t["refresh_token"] == "RT-OLD"


def test_tc_vm_043_refresh_rotated_refresh_token_is_adopted():
    t = oauth.refresh_tokens(_http({"access_token": "N", "refresh_token": "RT-NEW"}), ("i", "s"), {"refresh_token": "RT-OLD"}, NOW)
    assert t["refresh_token"] == "RT-NEW"


def test_tc_vm_044_default_expires_in_3600_when_missing():
    t = oauth.exchange_code(_http({"access_token": "A", "refresh_token": "R"}), ("i", "s"), "C", "V", "http://r", NOW)
    assert datetime.fromisoformat(t["expires_at"]) == NOW + timedelta(seconds=3600)


# ---------- 기본 HTTP ----------
def test_tc_vm_050_default_post_refuses_non_https_without_calling(fg):
    with pytest.raises(oauth.OAuthError) as e:
        oauth.default_http_post("http://oauth2.googleapis.com/token", {"a": "b"})
    assert e.value.code == "insecure_url" and fg.calls == []


def test_tc_vm_051_default_post_network_error_hides_details(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise OSError("connect to 10.0.0.5 failed; Authorization: Bearer SECRET-TOKEN-ABC")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(oauth.OAuthError) as e:
        oauth.default_http_post(oauth.TOKEN_URL, {"refresh_token": "SECRET-TOKEN-ABC"})
    assert e.value.code == "network" and "SECRET-TOKEN-ABC" not in e.value.message and "10.0.0.5" not in e.value.message
    assert "SECRET-TOKEN-ABC" not in repr(e.value) and e.value.__cause__ is None


def test_tc_vm_052_default_post_http_error_returns_error_code_from_body(fg):
    fg.token_error = "invalid_grant"
    out = oauth.default_http_post(oauth.TOKEN_URL, {"client_id": fg.client_id, "client_secret": fg.client_secret, "grant_type": "refresh_token", "refresh_token": "x"})
    assert out == {"error": "invalid_grant"}


# ---------- 토큰 저장소 ----------
def _tok(**kw):
    return {"access_token": "A", "refresh_token": "R", "expires_at": (NOW + timedelta(hours=1)).isoformat(), **kw}


def test_tc_vm_060_store_file_is_0600_dir_created_no_tmp_left(tmp_path):
    s = oauth.TokenStore(tmp_path / "deep" / "dir" / "google_token.json")
    s.save(_tok())
    assert stat.S_IMODE(os.stat(s.path).st_mode) == 0o600
    assert [p.name for p in s.path.parent.iterdir()] == ["google_token.json"]
    assert s.load()["refresh_token"] == "R"


def test_tc_vm_061_overwrite_keeps_0600_even_if_tmp_preexisted_with_loose_mode(tmp_path):
    s = oauth.TokenStore(tmp_path / "t.json")
    loose = tmp_path / "t.tmp"
    loose.write_text("old")
    os.chmod(loose, 0o666)
    s.save(_tok())
    assert stat.S_IMODE(os.stat(s.path).st_mode) == 0o600


def test_tc_vm_062_crash_during_write_keeps_previous_file(tmp_path, monkeypatch):
    s = oauth.TokenStore(tmp_path / "t.json")
    s.save(_tok(access_token="GOOD"))
    real_dump = json.dump
    monkeypatch.setattr(oauth.json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        s.save(_tok(access_token="BAD"))
    monkeypatch.setattr(oauth.json, "dump", real_dump)
    assert s.load()["access_token"] == "GOOD"


@pytest.mark.parametrize("content", ["", "{", "[]", "null", '{"access_token":"a"}', '{"refresh_token":""}', '"s"'])
def test_tc_vm_063_load_corrupt_or_without_refresh_returns_none(tmp_path, content):
    p = tmp_path / "t.json"
    p.write_text(content)
    assert oauth.TokenStore(p).load() is None


def test_tc_vm_064_load_missing_none_and_clear_idempotent(tmp_path):
    s = oauth.TokenStore(tmp_path / "x.json")
    assert s.load() is None
    s.clear()
    s.save(_tok())
    s.clear()
    s.clear()
    assert s.load() is None


@pytest.mark.parametrize("delta,fresh", [(61, True), (60, False), (59, False), (-5, False), (3600, True)])
def test_tc_vm_065_is_fresh_margin_60s_boundary(delta, fresh):
    tk = {"expires_at": (NOW + timedelta(seconds=delta)).isoformat()}
    assert oauth.TokenStore.is_fresh(tk, NOW) is fresh


@pytest.mark.parametrize("tk", [{}, {"expires_at": "garbage"}, {"expires_at": ""}])
def test_tc_vm_066_is_fresh_bad_values_are_not_fresh(tk):
    assert oauth.TokenStore.is_fresh(tk, NOW) is False


@pytest.mark.parametrize("tk", [{"expires_at": "2026-10-11T13:00:00"}, {"expires_at": 12345}, {"expires_at": None}])
def test_tc_vm_067_is_fresh_naive_or_nonstring_expiry_must_not_crash(tk):
    # 손상·수동 편집된 토큰 파일이 예외(TypeError)로 작업 전체를 죽이면 안 된다.
    assert oauth.TokenStore.is_fresh(tk, NOW) is False
