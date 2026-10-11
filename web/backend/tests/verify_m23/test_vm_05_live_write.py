"""TC-VM-400~: youtube/live_write.py (M3 단위 1) 독립 검증 — 허용 목록 0호출, 본문 검사, 응답 제목 확인, 오류 definite 구분, 토큰 보호."""
from __future__ import annotations

import copy
import io
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from tests.verify_m23.fakegoogle import SCOPE_READ, SCOPE_WRITE, _Resp
from ytweb.youtube import google_oauth as oauth
from ytweb.youtube import live_write as lw
from ytweb.youtube.base import GatewayError
from ytweb.youtube.live_read import GoogleAccess

HANGUL = re.compile("[가-힣]")
VID, OTHER = "abcdefghijk", "zzzzzzzzzzz"
NOW = datetime.now(timezone.utc)


def access(tmp_path, token="AT-WRITE-X"):
    st = oauth.TokenStore(tmp_path / "w.json")
    st.save({"access_token": token, "refresh_token": "RT-WRITE-X", "expires_at": (NOW + timedelta(hours=1)).isoformat(), "scope": SCOPE_WRITE})
    (tmp_path / "c.json").write_text(json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    return GoogleAccess(tmp_path / "c.json", st)


def body(title="새 제목", vid=VID, **sn):
    return {"id": vid, "snippet": {"title": title, "categoryId": "22", "description": "설명", "tags": ["a"], **sn}}


class Spy:
    def __init__(self, resp=None, exc=None):
        self.calls, self.resp, self.exc = [], resp, exc

    def __call__(self, url, token, b):
        self.calls.append((url, token, copy.deepcopy(b)))
        if self.exc:
            raise self.exc
        return self.resp if self.resp is not None else {"snippet": b["snippet"]}


def gw(tmp_path, allowed, send, **kw):
    return lw.LiveYouTubeGateway(access(tmp_path), allowed, http_send=send, **kw)


# ---------- 허용 목록 ----------
@pytest.mark.parametrize("allowed", [set(), [], frozenset(), {OTHER}, {VID.upper()}, {VID + " "}, {" " + VID}, {VID[:-1]}, {""}])
def test_tc_vm_400_video_outside_allowed_list_makes_zero_network_calls_and_no_token_read(tmp_path, fg, allowed):
    spy = Spy()
    g = gw(tmp_path, allowed, spy, http_get=lambda *a: (_ for _ in ()).throw(AssertionError("읽기 호출도 안 됨")))
    with pytest.raises(GatewayError) as e:
        g.update_snippet(VID, body())
    assert e.value.code == "not_allowed" and e.value.definite is True and HANGUL.search(e.value.message)
    assert spy.calls == [] and fg.calls == []


def test_tc_vm_401_allowed_list_is_a_snapshot_later_mutation_does_not_widen_it(tmp_path):
    allowed = {OTHER}
    spy = Spy()
    g = gw(tmp_path, allowed, spy)
    allowed.add(VID)
    with pytest.raises(GatewayError):
        g.update_snippet(VID, body())
    assert spy.calls == []


def test_tc_vm_402_allowed_video_sends_exactly_one_put_with_write_token_and_full_body(tmp_path):
    spy = Spy()
    out = gw(tmp_path, {VID, OTHER}, spy).update_snippet(VID, body("한글 제목"))
    assert out["title"] == "한글 제목" and len(spy.calls) == 1
    url, token, b = spy.calls[0]
    assert url == "https://www.googleapis.com/youtube/v3/videos?part=snippet" and token == "AT-WRITE-X"
    assert b == body("한글 제목")                                       # 제목 외 항목(설명·태그·카테고리) 보존


def test_tc_vm_403_allowed_check_precedes_body_validation_and_token_access(tmp_path):
    g = lw.LiveYouTubeGateway(GoogleAccess(tmp_path / "nope.json", oauth.TokenStore(tmp_path / "none.json")), set(), http_send=Spy())
    with pytest.raises(GatewayError) as e:
        g.update_snippet(VID, {"garbage": 1})
    assert e.value.code == "not_allowed"


# ---------- 본문 검사 ----------
@pytest.mark.parametrize("b", [
    {"id": OTHER, "snippet": {"title": "t", "categoryId": "22"}},
    {"snippet": {"title": "t", "categoryId": "22"}},
    {"id": VID},
    {"id": VID, "snippet": None},
    {"id": VID, "snippet": "x"},
    {"id": VID, "snippet": {"title": "", "categoryId": "22"}},
    {"id": VID, "snippet": {"title": "   ", "categoryId": "22"}},
    {"id": VID, "snippet": {"title": 5, "categoryId": "22"}},
    {"id": VID, "snippet": {"title": "t"}},
    {"id": VID, "snippet": {"title": "t", "categoryId": ""}},
    {"id": VID, "snippet": {"title": "t", "categoryId": 22}},
])
def test_tc_vm_410_invalid_body_never_sends(tmp_path, b):
    spy = Spy()
    with pytest.raises(GatewayError) as e:
        gw(tmp_path, {VID}, spy).update_snippet(VID, b)
    assert e.value.code == "invalid_request" and e.value.definite and spy.calls == []


@pytest.mark.parametrize("b", [None, [], "str", 5])
def test_tc_vm_411_non_dict_body_must_be_gateway_error_not_attribute_error(tmp_path, b):
    spy = Spy()
    with pytest.raises(GatewayError):
        gw(tmp_path, {VID}, spy).update_snippet(VID, b)
    assert spy.calls == []


# ---------- 응답 확인 ----------
@pytest.mark.parametrize("resp", [
    {"snippet": {"title": "다른 제목"}}, {"snippet": {"title": "새 제목 "}}, {"snippet": {}}, {"snippet": None}, {"snippet": "x"}, {}, [], None, "ok",
])
def test_tc_vm_420_response_without_exact_new_title_is_indefinite_unconfirmed(tmp_path, resp):
    class S(Spy):
        def __call__(self, url, token, b):
            self.calls.append(1)
            return resp
    g = gw(tmp_path, {VID}, S())
    with pytest.raises(GatewayError) as e:
        g.update_snippet(VID, body())
    assert e.value.code == "unconfirmed" and e.value.definite is False and HANGUL.search(e.value.message)


def test_tc_vm_421_title_equality_is_exact_not_normalized(tmp_path):
    spy = Spy(resp={"snippet": {"title": "새  제목"}})
    with pytest.raises(GatewayError) as e:
        gw(tmp_path, {VID}, spy).update_snippet(VID, body("새 제목"))
    assert e.value.definite is False


def test_tc_vm_422_send_errors_propagate_with_definite_flag_intact(tmp_path):
    for d in (True, False):
        with pytest.raises(GatewayError) as e:
            gw(tmp_path, {VID}, Spy(exc=GatewayError("x", "m", definite=d))).update_snippet(VID, body())
        assert e.value.definite is d


# ---------- default_http_send: 상태코드별 definite ----------
def _urlopen_raising(code, reason=None, headers=None):
    def f(req, timeout=None):
        payload = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode() if reason else b"<html>"
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(payload))
    return f


@pytest.mark.parametrize("code,reason,exp_code,definite", [
    (401, None, "unauthorized", True),
    (403, "quotaExceeded", "quota_exceeded", True), (403, "dailyLimitExceeded", "quota_exceeded", True), (403, "rateLimitExceeded", "quota_exceeded", True),
    (403, "forbidden", "forbidden", True), (403, None, "forbidden", True),
    (404, None, "video_not_found", True),
    (400, "invalidTitle", "http_400", True), (409, None, "http_409", True), (429, None, "http_429", True),
    (500, None, "http_500", False), (502, None, "http_502", False), (503, "backendError", "http_503", False), (504, None, "http_504", False), (599, None, "http_599", False),
])
def test_tc_vm_430_status_code_to_definite_mapping(monkeypatch, code, reason, exp_code, definite):
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_raising(code, reason))
    with pytest.raises(GatewayError) as e:
        lw.default_http_send(lw.API + "/videos?part=snippet", "SECRET-WRITE-TOKEN", body())
    assert e.value.code == exp_code and e.value.definite is definite and HANGUL.search(e.value.message)
    assert "SECRET-WRITE-TOKEN" not in e.value.message and "SECRET-WRITE-TOKEN" not in str(e.value) and e.value.__cause__ is None


@pytest.mark.parametrize("exc", [TimeoutError("timed out"), ConnectionResetError("reset"), OSError("net down token=SECRET-WRITE-TOKEN"), urllib.error.URLError("dns")])
def test_tc_vm_431_timeout_and_connection_errors_are_indefinite_and_hide_details(monkeypatch, exc):
    def boom(req, timeout=None):
        raise exc
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(GatewayError) as e:
        lw.default_http_send(lw.API + "/videos?part=snippet", "SECRET-WRITE-TOKEN", body())
    assert e.value.code == "network" and e.value.definite is False and HANGUL.search(e.value.message)
    assert "SECRET-WRITE-TOKEN" not in e.value.message and e.value.__cause__ is None


def test_tc_vm_432_non_json_success_body_is_indefinite(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp(b"<html>proxy</html>"))
    with pytest.raises(GatewayError) as e:
        lw.default_http_send(lw.API + "/videos?part=snippet", "T", body())
    assert e.value.definite is False


def test_tc_vm_433_send_refuses_non_https_without_call(fg):
    with pytest.raises(GatewayError) as e:
        lw.default_http_send("http://www.googleapis.com/youtube/v3/videos?part=snippet", "T", body())
    assert e.value.code == "insecure_url" and fg.calls == []


def test_tc_vm_434_send_uses_put_json_utf8_bearer(fg, tmp_path):
    a = access(tmp_path)
    fg.access["AT-WRITE-X"] = SCOPE_WRITE
    fg.videos[VID] = {"title": "원래", "categoryId": "22"}
    g = lw.LiveYouTubeGateway(a, {VID})                       # 기본 전송 함수 사용
    out = g.update_snippet(VID, body("한글 새 제목"))
    c = fg.put_calls()[0]
    assert out["title"] == "한글 새 제목" and c.auth == "Bearer AT-WRITE-X" and c.body["snippet"]["title"] == "한글 새 제목"
    assert fg.videos[VID]["title"] == "한글 새 제목"


# ---------- 읽기/쓰기 토큰 분리 ----------
def test_tc_vm_440_read_scope_token_cannot_write_fake_google_403_forbidden(fg, tmp_path):
    a = access(tmp_path, token="AT-READ-ONLY-1")
    fg.access["AT-READ-ONLY-1"] = SCOPE_READ
    fg.videos[VID] = {"title": "원래", "categoryId": "22"}
    with pytest.raises(GatewayError) as e:
        lw.LiveYouTubeGateway(a, {VID}).update_snippet(VID, body())
    assert e.value.code == "forbidden" and e.value.definite and fg.videos[VID]["title"] == "원래"


def test_tc_vm_441_read_snippet_uses_its_access_token_and_handles_empty(tmp_path):
    seen = []
    def get(url, token):
        seen.append((url, token))
        return {"items": []}
    g = lw.LiveYouTubeGateway(access(tmp_path), {VID}, http_get=get)
    assert g.read_snippet(VID) is None and seen[0][1] == "AT-WRITE-X" and "id=abcdefghijk" in seen[0][0]
    g2 = lw.LiveYouTubeGateway(access(tmp_path), {VID}, http_get=lambda u, t: {"items": [{"snippet": "str"}]})
    assert g2.read_snippet(VID) is None


def test_tc_vm_442_read_snippet_of_non_allowed_video_does_network_read_OBSERVATION(tmp_path):
    """관찰(Low): read_snippet 은 허용 목록을 보지 않는다(읽기뿐이라 제목은 안 바뀜). 배치/롤백 경로는 앞단에서 막지만,
    게이트웨이 단독으로는 '허용 밖 영상 네트워크 0회'가 update 에만 해당한다는 사실을 기록한다."""
    seen = []
    g = lw.LiveYouTubeGateway(access(tmp_path), {VID}, http_get=lambda u, t: seen.append(u) or {"items": []})
    g.read_snippet(OTHER)
    assert len(seen) == 1
