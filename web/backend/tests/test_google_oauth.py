"""M2 단위 1 시험(TC-M2-001~): 구글 로그인 처리. 실제 구글에는 접속하지 않고 가짜 응답을 쓴다."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from ytweb.youtube import google_oauth as g

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
CLIENT = ("cid.apps.googleusercontent.com", "csecret")


def test_tc_m2_001_pkce_challenge_is_s256_of_verifier():
    v, c = g.make_pkce()
    assert c == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    assert 43 <= len(v) <= 128 and "=" not in c


def test_tc_m2_002_auth_url_has_required_security_params_and_read_scope_only():
    url = g.build_auth_url("cid", "http://127.0.0.1:8080/api/v1/google/callback", "ST", "CH")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["scope"] == ["https://www.googleapis.com/auth/youtube.readonly"]
    assert q["state"] == ["ST"] and q["code_challenge"] == ["CH"] and q["code_challenge_method"] == ["S256"]
    assert q["response_type"] == ["code"] and q["access_type"] == ["offline"]
    assert "youtube.force-ssl" not in url and "auth/youtube\"" not in url  # 쓰기 범위 없음


def test_tc_m2_003_state_is_single_use():
    p = g.PendingAuth()
    s, _ = p.start()
    assert p.finish(s)
    with pytest.raises(g.OAuthError) as e:
        p.finish(s)
    assert e.value.code == "state_invalid"


def test_tc_m2_004_unknown_or_empty_state_rejected():
    p = g.PendingAuth()
    for bad in ("nope", "", None):
        with pytest.raises(g.OAuthError):
            p.finish(bad)


def test_tc_m2_005_state_expires_after_ten_minutes():
    t = [1000.0]
    p = g.PendingAuth(clock=lambda: t[0])
    s, _ = p.start()
    t[0] += g.STATE_TTL_SECONDS - 1
    s2, _ = p.start()
    assert p.finish(s)  # 599초: 유효
    t[0] += g.STATE_TTL_SECONDS
    with pytest.raises(g.OAuthError):
        p.finish(s2)  # 600초 이상: 만료


def test_tc_m2_006_pending_is_bounded():
    p = g.PendingAuth()
    first, _ = p.start()
    for _ in range(g.MAX_PENDING + 5):
        p.start()
    with pytest.raises(g.OAuthError):
        p.finish(first)  # 가장 오래된 요청은 밀려남


def test_tc_m2_007_load_client_accepts_installed_and_web(tmp_path):
    for key in ("installed", "web"):
        f = tmp_path / f"{key}.json"
        f.write_text(json.dumps({key: {"client_id": "A", "client_secret": "B"}}), encoding="utf-8")
        assert g.load_client(f) == ("A", "B")


def test_tc_m2_008_load_client_errors_are_korean_and_leak_nothing(tmp_path):
    with pytest.raises(g.OAuthError) as e:
        g.load_client(tmp_path / "none.json")
    assert e.value.code == "client_missing" and "google_client.json" in e.value.message
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(g.OAuthError) as e:
        g.load_client(bad)
    assert e.value.code == "client_invalid"
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"installed": {"client_id": "A"}}), encoding="utf-8")
    with pytest.raises(g.OAuthError) as e:
        g.load_client(empty)
    assert "csecret" not in e.value.message


def test_tc_m2_009_exchange_code_sends_pkce_and_returns_tokens():
    seen = {}

    def http(url, form):
        seen.update(url=url, form=form)
        return {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600, "scope": g.SCOPE_READ}

    t = g.exchange_code(http, CLIENT, "CODE", "VER", "http://127.0.0.1:8080/cb", NOW)
    assert seen["url"] == g.TOKEN_URL and seen["form"]["code_verifier"] == "VER" and seen["form"]["grant_type"] == "authorization_code"
    assert t["refresh_token"] == "RT" and datetime.fromisoformat(t["expires_at"]) == NOW + timedelta(hours=1)


def test_tc_m2_010_exchange_without_refresh_token_is_rejected():
    with pytest.raises(g.OAuthError) as e:
        g.exchange_code(lambda u, f: {"access_token": "AT", "expires_in": 10}, CLIENT, "C", "V", "R", NOW)
    assert e.value.code == "no_refresh"


def test_tc_m2_011_google_error_becomes_korean_message_without_secrets():
    with pytest.raises(g.OAuthError) as e:
        g.exchange_code(lambda u, f: {"error": "invalid_grant"}, CLIENT, "C", "V", "R", NOW)
    assert "다시 로그인" in e.value.message and "csecret" not in e.value.message and "C" != e.value.message


def test_tc_m2_012_refresh_keeps_refresh_token_when_google_omits_it():
    old = {"refresh_token": "RT", "access_token": "old", "expires_at": NOW.isoformat()}
    new = g.refresh_tokens(lambda u, f: {"access_token": "AT2", "expires_in": 100}, CLIENT, old, NOW)
    assert new["refresh_token"] == "RT" and new["access_token"] == "AT2"


def test_tc_m2_013_default_http_refuses_non_https():
    with pytest.raises(g.OAuthError) as e:
        g.default_http_post("http://accounts.google.com/token", {})
    assert e.value.code == "insecure_url"


def test_tc_m2_014_token_store_roundtrip_atomic_and_private(tmp_path):
    s = g.TokenStore(tmp_path / "sub" / "google_token.json")
    assert s.load() is None
    s.save({"access_token": "AT", "refresh_token": "RT", "expires_at": NOW.isoformat()})
    assert s.load()["refresh_token"] == "RT"
    if os.name == "posix":
        assert stat.S_IMODE(s.path.stat().st_mode) == 0o600
    assert not list((tmp_path / "sub").glob("*.tmp"))
    s.clear(); s.clear()  # 두 번 지워도 오류 없음
    assert s.load() is None


def test_tc_m2_015_token_store_ignores_corrupt_or_incomplete_file(tmp_path):
    p = tmp_path / "t.json"
    s = g.TokenStore(p)
    p.write_text("{broken", encoding="utf-8"); assert s.load() is None
    p.write_text(json.dumps({"access_token": "only"}), encoding="utf-8"); assert s.load() is None


def test_tc_m2_016_is_fresh_boundary():
    exp = NOW + timedelta(seconds=61)
    assert g.TokenStore.is_fresh({"expires_at": exp.isoformat()}, NOW) is True
    assert g.TokenStore.is_fresh({"expires_at": (NOW + timedelta(seconds=60)).isoformat()}, NOW) is False
    assert g.TokenStore.is_fresh({}, NOW) is False


def test_tc_m2_017_scope_is_read_only_constant():
    assert g.SCOPE_READ.endswith("youtube.readonly")
