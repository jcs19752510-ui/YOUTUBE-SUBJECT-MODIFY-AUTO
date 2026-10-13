"""D 보안 점검: 3조건 우회·키 노출·호스트 고정·리다이렉트·쓰기 토큰 범위 검증 재현 시험. 실제 외부 호출 없음(urlopen 가짜)."""
import io
import json
import logging
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ytweb.ai import gemini
from ytweb.ai.base import TitleSuggestionError, VideoBrief
from ytweb.domain import live_gateway as lg
from ytweb.youtube import google_oauth as oauth
from ytweb.youtube.base import GatewayError
from ytweb.youtube.live_read import GoogleAccess
from ytweb.youtube.live_write import LiveYouTubeGateway

VID, OTHER = "abcdefghijk", "zzzzzzzzzzz"
KEY = "AIzaSyFAKEKEYFORTESTING000000000000000"


def _write_ready_dir(tmp_path, scope="https://www.googleapis.com/auth/youtube.readonly"):
    (tmp_path / "c.json").write_text(json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    oauth.TokenStore(tmp_path / lg.WRITE_TOKEN_FILE).save(
        {"access_token": "AT", "refresh_token": "RT", "scope": scope,
         "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    return tmp_path


def _env(tmp_path, **kw):
    e = {"YTWEB_GOOGLE_CLIENT_FILE": str(tmp_path / "c.json")}
    e.update(kw)
    return e


# 1) 3조건: 하나라도 빠지면 모의 게이트웨이
@pytest.mark.parametrize("drop", ["switch", "allowed", "token"])
def test_three_conditions_each_required(tmp_path, drop):
    sd = _write_ready_dir(tmp_path)
    env = _env(tmp_path, YTWEB_LIVE_WRITE="1", YTWEB_LIVE_ALLOWED_VIDEOS=VID)
    if drop == "switch":
        env["YTWEB_LIVE_WRITE"] = "0"
    if drop == "allowed":
        env["YTWEB_LIVE_ALLOWED_VIDEOS"] = " , "
    if drop == "token":
        (sd / lg.WRITE_TOKEN_FILE).unlink()
    assert lg.live_write_ready(sd, env) is False


@pytest.mark.parametrize("val", ["true", "True", "yes", "on", " 1", "1 ", "01"])
def test_switch_only_exact_1(tmp_path, val):
    sd = _write_ready_dir(tmp_path)
    env = _env(tmp_path, YTWEB_LIVE_WRITE=val, YTWEB_LIVE_ALLOWED_VIDEOS=VID)
    assert lg.live_write_ready(sd, env) is False


def test_live_gateway_blocks_unlisted_before_network(tmp_path):
    sd = _write_ready_dir(tmp_path)
    sent = []
    g = LiveYouTubeGateway(GoogleAccess(tmp_path / "c.json", oauth.TokenStore(sd / lg.WRITE_TOKEN_FILE)), {VID},
                           http_send=lambda *a: sent.append(a) or {})
    for vid, body in [(OTHER, {"id": OTHER, "snippet": {"title": "t", "categoryId": "22"}}),
                      (VID, {"id": OTHER, "snippet": {"title": "t", "categoryId": "22"}}),   # id 불일치(허용 영상 id 로 다른 영상 수정 시도)
                      (VID, {"id": VID, "snippet": {"title": " ", "categoryId": "22"}})]:
        with pytest.raises(GatewayError):
            g.update_snippet(vid, body)
    assert sent == []


def test_url_not_user_controllable_video_id_in_read_query(tmp_path):
    """read_snippet 의 id 는 urlencode 되어 쿼리 주입(& 추가) 불가."""
    sd = _write_ready_dir(tmp_path)
    urls = []
    g = LiveYouTubeGateway(GoogleAccess(tmp_path / "c.json", oauth.TokenStore(sd / lg.WRITE_TOKEN_FILE)), {VID},
                           http_get=lambda u, t: urls.append(u) or {"items": []})
    g.read_snippet("x&part=contentDetails#y")
    assert "&part=contentDetails" not in urls[0] and urls[0].startswith("https://www.googleapis.com/")


# 2) 쓰기 토큰 범위 미검증(결함 후보): 읽기 범위 토큰이 쓰기 토큰 파일에 저장돼도 live_write_ready 가 True
@pytest.mark.xfail(strict=True, reason="DEF-D-002(Low): 쓰기 토큰 scope 미검사 — 구글 403 으로 실제 변경은 막히고 표시만 틀림. 실제 쓰기 로그인 확인과 함께 고칠 것(고치면 이 xfail 이 XPASS 로 실패해 알려 줌)")
def test_write_token_scope_not_verified_REPRO(tmp_path):
    sd = _write_ready_dir(tmp_path, scope=oauth.SCOPE_READ)  # 쓰기 슬롯에 readonly 범위
    env = _env(tmp_path, YTWEB_LIVE_WRITE="1", YTWEB_LIVE_ALLOWED_VIDEOS=VID)
    # True 이면 '쓰기 권한 연결됨' 판정이 실제 범위를 보지 않는다는 뜻(구글이 403 으로 막으므로 안전하나 화면은 '준비됨'으로 표시)
    assert lg.live_write_ready(sd, env) is False, "쓰기 토큰의 scope 를 검사하지 않음"


# 3) Gemini: 키 노출 경로
class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_gemini_key_only_in_header_and_fixed_host(monkeypatch):
    seen = {}

    def fake(req, timeout=None):
        seen["url"], seen["headers"] = req.full_url, dict(req.header_items())
        return _Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps({"candidates": []})}]}}]}).encode())
    monkeypatch.setattr(gemini.urllib.request, "urlopen", fake)
    try:
        gemini.GeminiSuggester(KEY).suggest(VideoBrief("v", "t", "s"), count=1, tone="x")
    except TypeError:
        pytest.skip("VideoBrief 시그니처 다름")
    assert KEY not in seen["url"] and seen["url"].startswith("https://generativelanguage.googleapis.com/")
    assert seen["headers"].get("X-goog-api-key") == KEY


@pytest.mark.parametrize("exc", [
    urllib.error.HTTPError("https://x?key=" + KEY, 403, "bad " + KEY, {}, io.BytesIO(KEY.encode())),
    urllib.error.URLError("fail " + KEY), TimeoutError(KEY), ValueError(KEY)])
def test_gemini_errors_do_not_leak_key(monkeypatch, caplog, exc):
    def fake(req, timeout=None):
        raise exc
    monkeypatch.setattr(gemini.urllib.request, "urlopen", fake)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(TitleSuggestionError) as ei:
            gemini.GeminiSuggester(KEY).suggest(VideoBrief("v", "t", "s"), count=1, tone="x")
    assert KEY not in str(ei.value) and KEY not in repr(ei.value) and KEY not in caplog.text
    assert ei.value.__cause__ is None and ei.value.__suppress_context__


def test_gemini_model_env_with_url_characters_is_refused_before_request(monkeypatch):
    """YTWEB_GEMINI_MODEL 은 검증 없이 URL 경로에 들어간다(호스트는 고정이라 SSRF 는 아니나 경로·쿼리 주입 가능). 환경변수는 소유자만 설정."""
    urls = []

    def fake(req, timeout=None):
        urls.append(req.full_url)
        raise urllib.error.URLError("x")
    monkeypatch.setattr(gemini.urllib.request, "urlopen", fake)
    monkeypatch.setenv("YTWEB_GEMINI_MODEL", "x:generateContent?alt=sse&foo=")
    with pytest.raises(TitleSuggestionError):
        gemini.GeminiSuggester(KEY).suggest(VideoBrief("v", "t", "s"), count=1, tone="x")
    # DEF-D-001 조치(2026-10-13): 형식이 틀린 모델 이름은 요청을 보내기 전에 거부한다. (조치 전에는 URL 에 그대로 들어갔다 — 첫 실행 실패는 d-security.md 에 보존)
    assert urls == [], "형식이 틀린 모델 이름으로 요청이 나갔음"


def test_gemini_malformed_responses_fail_closed():
    for data in [{}, {"candidates": []}, {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]},
                 {"candidates": [{"content": {"parts": [{"text": "{\"candidates\": 5}"}]}}]}]:
        try:
            out = gemini._parse(data, 3)
        except TitleSuggestionError:
            continue
        assert out == []


# 4) 리다이렉트 비추종(Authorization 유출 방지)
def test_no_redirect_handler_installed():
    import urllib.request
    h = urllib.request._opener.handlers if urllib.request._opener else []
    assert any(isinstance(x, oauth._NoRedirect) for x in h)
    assert oauth._NoRedirect().redirect_request(None, None, 302, "", {}, "http://evil/") is None


# 5) OAuth state 1회성·종류
def test_state_single_use_and_unknown_rejected():
    p = oauth.PendingAuth()
    s, _ = p.start("write")
    assert p.peek_kind(s) == "write"
    p.finish(s)
    with pytest.raises(oauth.OAuthError):
        p.finish(s)
    with pytest.raises(oauth.OAuthError):
        p.finish(None)
    assert p.peek_kind("unknown") == "read"


def test_token_file_mode_0600(tmp_path):
    st = oauth.TokenStore(tmp_path / "t.json")
    st.save({"access_token": "a", "refresh_token": "r"})
    assert (st.path.stat().st_mode & 0o777) == 0o600
    assert not st.path.with_suffix(".tmp").exists()
