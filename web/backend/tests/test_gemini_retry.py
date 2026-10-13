"""Gemini 제안기: 일시 오류(429·5xx)·응답 잘림 재시도와 출력 한도(2026-10-13 실서버 확인에서 호출 16회 중 5회만 성공 — 결함 GEM-1·GEM-2).
실제 네트워크·실제 대기는 쓰지 않는다."""
import io
import json
import urllib.error

import pytest

from ytweb.ai import gemini as G
from ytweb.ai.base import TitleSuggestionError, VideoBrief
from ytweb.ai.gemini import GeminiSuggester

KEY = "AIzaSy-FAKE-KEY-0123456789"
BRIEF = VideoBrief("vid12345678", "[시니어 필수] 해외여행 통역 앱", "01:10 통역 앱 설치 및 실행 방법 (공식 앱 사용)")
GOOD = [{"title": "[시니어 필수] 해외여행 통역 앱 설치부터 실행까지 쉽게", "evidence": "통역 앱 설치 및 실행 방법", "topic": "life"}]


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(items=GOOD):
    text = json.dumps({"candidates": items}, ensure_ascii=False)
    return _Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}).encode())


def _cut():  # 출력 한도에 닿아 JSON 이 중간에 잘린 응답(실측 형태)
    return _Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": '{"candidates": [{"title": "[시니어 필수] 해외'}]}, "finishReason": "MAX_TOKENS"}]}).encode())


def _http(code):
    return urllib.error.HTTPError("https://example.invalid", code, "x", {}, io.BytesIO(b"{}"))


def _script(monkeypatch, steps):
    """steps: 호출 순서대로 응답을 만드는 함수 또는 예외. 호출 횟수와 대기 기록을 돌려준다."""
    log = {"calls": 0, "sleeps": [], "bodies": []}

    def fake(req, timeout=None):
        log["bodies"].append(json.loads(req.data))
        step = steps[min(log["calls"], len(steps) - 1)]
        log["calls"] += 1
        if isinstance(step, Exception):
            raise step
        return step() if callable(step) else step  # 응답 본문은 한 번 읽으면 비므로 호출마다 새로 만든다

    monkeypatch.setattr(G.urllib.request, "urlopen", fake)
    monkeypatch.setattr(G, "_sleep", lambda sec: log["sleeps"].append(sec))
    return log


def _run():
    return GeminiSuggester(KEY).suggest(BRIEF, count=3, tone="plain")


def test_output_budget_is_large_enough_for_thinking_tokens(monkeypatch):
    log = _script(monkeypatch, [_ok])
    _run()
    assert log["bodies"][0]["generationConfig"]["maxOutputTokens"] >= 16000  # 생각 토큰 약 3,800개 + 후보


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_transient_http_errors_are_retried_then_succeed(monkeypatch, code):
    log = _script(monkeypatch, [_http(code), _http(code), _ok])
    assert [d.title for d in _run()] == [GOOD[0]["title"]]
    assert log["calls"] == 3 and len(log["sleeps"]) == 2 and all(s > 0 for s in log["sleeps"])


def test_gives_up_after_three_attempts_with_the_server_error_message(monkeypatch):
    log = _script(monkeypatch, [_http(503)])
    with pytest.raises(TitleSuggestionError) as e:
        _run()
    assert "503" in str(e.value) and KEY not in str(e.value)
    assert log["calls"] == G.ATTEMPTS == 3 and len(log["sleeps"]) == 2


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_client_errors_are_not_retried(monkeypatch, code):
    log = _script(monkeypatch, [_http(code), _ok])
    with pytest.raises(TitleSuggestionError):
        _run()
    assert log["calls"] == 1 and log["sleeps"] == []


def test_truncated_response_is_retried_once_it_succeeds(monkeypatch):
    log = _script(monkeypatch, [_cut, _ok])
    assert len(_run()) == 1
    assert log["calls"] == 2 and len(log["sleeps"]) == 1


def test_truncated_every_time_ends_with_a_korean_error(monkeypatch):
    log = _script(monkeypatch, [_cut])
    with pytest.raises(TitleSuggestionError) as e:
        _run()
    assert "형식" in str(e.value) and log["calls"] == 3


def test_network_errors_are_not_retried_to_keep_the_wait_short(monkeypatch):
    log = _script(monkeypatch, [urllib.error.URLError("down"), _ok])
    with pytest.raises(TitleSuggestionError):
        _run()
    assert log["calls"] == 1


def test_truncation_detector_handles_odd_shapes():
    assert G._truncated({"candidates": [{"finishReason": "MAX_TOKENS"}]}) is True
    assert G._truncated({"candidates": [{"finishReason": "STOP"}]}) is False
    for odd in ({}, {"candidates": []}, {"candidates": [None]}, {"candidates": "x"}):
        assert G._truncated(odd) is False


@pytest.mark.parametrize("bad", ["a/b", "x?y=1", "m#frag", "gemini:evil", "a b", "../x", "m" * 65])
def test_model_name_with_url_characters_is_refused_before_any_request(monkeypatch, bad):
    log = _script(monkeypatch, [_ok])
    with pytest.raises(TitleSuggestionError) as e:
        GeminiSuggester(KEY, model=bad).suggest(BRIEF, count=3, tone="plain")
    assert "모델 이름" in str(e.value)
    assert log["calls"] == 0


def test_default_and_normal_model_names_are_accepted(monkeypatch):
    log = _script(monkeypatch, [_ok, _ok])
    GeminiSuggester(KEY).suggest(BRIEF, count=3, tone="plain")
    GeminiSuggester(KEY, model="gemini-2.5-flash-lite").suggest(BRIEF, count=3, tone="plain")
    assert log["calls"] == 2
