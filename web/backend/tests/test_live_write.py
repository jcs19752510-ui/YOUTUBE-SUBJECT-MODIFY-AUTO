"""M3 단위 1: 실제 제목 수정 게이트웨이 (가짜 구글 사용 — 실제 호출 없음)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from ytweb.youtube import google_oauth as oauth
from ytweb.youtube.base import GatewayError
from ytweb.youtube.live_read import GoogleAccess
from ytweb.youtube.live_write import LiveYouTubeGateway

VID, OTHER = "abcdefghijk", "zzzzzzzzzzz"


def access(tmp_path):
    store = oauth.TokenStore(tmp_path / "w.json")
    store.save({"access_token": "AT", "refresh_token": "RT", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    (tmp_path / "c.json").write_text(json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    return GoogleAccess(tmp_path / "c.json", store)


def body(title="새 제목"):
    return {"id": VID, "snippet": {"title": title, "categoryId": "22", "description": "설명", "tags": ["a"]}}


def test_scope_and_auth_url_write():
    url = oauth.build_auth_url("cid", "http://127.0.0.1/cb", "st", "ch", scope=oauth.SCOPE_WRITE)
    assert "force-ssl" in url and "readonly" not in url
    assert "readonly" in oauth.build_auth_url("cid", "http://127.0.0.1/cb", "st", "ch")


def test_update_sends_once_and_confirms(tmp_path):
    calls = []
    def send(url, token, b):
        calls.append((url, token, b)); return {"snippet": b["snippet"]}
    g = LiveYouTubeGateway(access(tmp_path), {VID}, http_send=send)
    out = g.update_snippet(VID, body())
    assert out["title"] == "새 제목" and len(calls) == 1
    assert calls[0][0].endswith("/videos?part=snippet") and calls[0][1] == "AT" and calls[0][2]["snippet"]["tags"] == ["a"]


def test_not_allowed_makes_no_call(tmp_path):
    def send(*a): raise AssertionError("호출되면 안 됨")
    for allowed in (set(), {OTHER}):
        g = LiveYouTubeGateway(access(tmp_path), allowed, http_send=send)
        with pytest.raises(GatewayError) as e:
            g.update_snippet(VID, body())
        assert e.value.code == "not_allowed" and e.value.definite


@pytest.mark.parametrize("b", [
    {"id": OTHER, "snippet": {"title": "t", "categoryId": "22"}},
    {"id": VID, "snippet": {"title": " ", "categoryId": "22"}},
    {"id": VID, "snippet": {"title": "t"}},
    {"id": VID},
])
def test_invalid_body_makes_no_call(tmp_path, b):
    def send(*a): raise AssertionError("호출되면 안 됨")
    with pytest.raises(GatewayError) as e:
        LiveYouTubeGateway(access(tmp_path), {VID}, http_send=send).update_snippet(VID, b)
    assert e.value.code == "invalid_request"


def test_unconfirmed_response_is_indefinite(tmp_path):
    g = LiveYouTubeGateway(access(tmp_path), {VID}, http_send=lambda u, t, b: {"snippet": {"title": "다른 제목"}})
    with pytest.raises(GatewayError) as e:
        g.update_snippet(VID, body())
    assert e.value.code == "unconfirmed" and e.value.definite is False


def test_send_error_propagates(tmp_path):
    def send(*a): raise GatewayError("network", "끊김", definite=False)
    with pytest.raises(GatewayError) as e:
        LiveYouTubeGateway(access(tmp_path), {VID}, http_send=send).update_snippet(VID, body())
    assert e.value.definite is False


def test_read_snippet(tmp_path):
    g = LiveYouTubeGateway(access(tmp_path), {VID}, http_get=lambda url, t: {"items": [{"snippet": {"title": "원래"}}]})
    assert g.read_snippet(VID) == {"title": "원래"}
    g2 = LiveYouTubeGateway(access(tmp_path), {VID}, http_get=lambda url, t: {"items": []})
    assert g2.read_snippet(VID) is None
