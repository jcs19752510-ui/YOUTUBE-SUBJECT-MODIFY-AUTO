"""Gemini 제안기: 요청 구성·응답 해석·오류 처리·키 비노출·제안기 선택(2026-10-12, 선생님 요청). 실제 네트워크는 쓰지 않는다."""
import io
import json
import urllib.error

import pytest

from ytweb.ai import gemini as G
from ytweb.ai.base import TitleSuggestionError, VideoBrief
from ytweb.ai.factory import get_live_suggester
from ytweb.ai.gemini import GeminiSuggester
from ytweb.ai.rule import RuleSuggester

KEY = "AIzaSy-FAKE-KEY-0123456789"
BRIEF = VideoBrief("vid12345678", "[시니어 필수] 해외여행 통역 앱", "01:10 통역 앱 설치 및 실행 방법 (공식 앱 사용)")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _reply(items, thought=True):
    parts = ([{"text": "생각 중...", "thought": True}] if thought else []) + [{"text": json.dumps({"candidates": items}, ensure_ascii=False)}]
    return _Resp(json.dumps({"candidates": [{"content": {"parts": parts}}]}).encode())


def _patch(monkeypatch, handler):
    seen = {}

    def fake(req, timeout=None):
        seen["req"], seen["timeout"] = req, timeout
        return handler()

    monkeypatch.setattr(G.urllib.request, "urlopen", fake)
    return seen


def test_request_has_key_in_header_only_and_sends_only_title_and_summary(monkeypatch):
    seen = _patch(monkeypatch, lambda: _reply([{"title": "새 제목", "evidence": "통역 앱 설치", "topic": "life"}]))
    out = GeminiSuggester(KEY).suggest(BRIEF, count=3, tone="x")
    req = seen["req"]
    assert req.get_header("X-goog-api-key") == KEY and KEY not in req.full_url
    assert req.full_url.startswith("https://generativelanguage.googleapis.com/") and seen["timeout"] == G.TIMEOUT_SEC
    sent = json.loads(req.data)
    user_text = sent["contents"][0]["parts"][0]["text"]
    assert KEY not in json.dumps(sent) and BRIEF.title in user_text and "통역 앱 설치 및 실행 방법" in user_text
    assert BRIEF.video_id not in user_text  # 영상 ID 는 보내지 않는다
    assert [(d.title, d.evidence, d.topic) for d in out] == [("새 제목", "통역 앱 설치", "life")]


def test_thought_parts_are_ignored_and_bad_items_dropped(monkeypatch):
    _patch(monkeypatch, lambda: _reply([{"title": "  ", "evidence": "x", "topic": "life"}, "문자열", {"title": "좋은 제목", "evidence": None, "topic": "weird"}]))
    out = GeminiSuggester(KEY).suggest(BRIEF, count=5, tone="x")
    assert [(d.title, d.evidence, d.topic) for d in out] == [("좋은 제목", "", None)]


def test_count_caps_the_result(monkeypatch):
    _patch(monkeypatch, lambda: _reply([{"title": f"제목{i}", "evidence": "e", "topic": "life"} for i in range(8)]))
    assert len(GeminiSuggester(KEY).suggest(BRIEF, count=3, tone="x")) == 3


@pytest.mark.parametrize("code,word", [(403, "API 키"), (404, "모델"), (429, "한도"), (500, "서버 오류")])
def test_http_errors_become_korean_messages_without_the_key(monkeypatch, code, word):
    def boom():
        raise urllib.error.HTTPError("https://x", code, "msg", {}, io.BytesIO(("키는 " + KEY).encode()))

    _patch(monkeypatch, boom)
    with pytest.raises(TitleSuggestionError) as e:
        GeminiSuggester(KEY).suggest(BRIEF, count=1, tone="x")
    assert word in str(e.value) and KEY not in str(e.value)


def test_network_and_format_errors(monkeypatch):
    def down():
        raise urllib.error.URLError("dns")

    _patch(monkeypatch, down)
    with pytest.raises(TitleSuggestionError, match="연결하지 못했습니다"):
        GeminiSuggester(KEY).suggest(BRIEF, count=1, tone="x")
    _patch(monkeypatch, lambda: _Resp(b"not json"))
    with pytest.raises(TitleSuggestionError, match="읽지 못했습니다"):
        GeminiSuggester(KEY).suggest(BRIEF, count=1, tone="x")
    _patch(monkeypatch, lambda: _Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}).encode()))
    with pytest.raises(TitleSuggestionError, match="형식"):
        GeminiSuggester(KEY).suggest(BRIEF, count=1, tone="x")


def test_already_made_titles_are_sent_to_the_model(monkeypatch):
    seen = _patch(monkeypatch, lambda: _reply([]))
    GeminiSuggester(KEY).with_avoid({"이미 만든 제목"}).suggest(BRIEF, count=1, tone="x")
    assert "이미 만든 제목" in json.loads(seen["req"].data)["contents"][0]["parts"][0]["text"]


def test_factory_uses_gemini_only_with_a_nonempty_key_file(monkeypatch, tmp_path):
    f = tmp_path / "gemini_api_key"
    monkeypatch.setenv("YTWEB_GEMINI_KEY_FILE", str(f))
    assert isinstance(get_live_suggester(), RuleSuggester)  # 파일 없음
    f.write_text("  \n", encoding="utf-8")
    assert isinstance(get_live_suggester(), RuleSuggester)  # 빈 파일
    f.write_text(KEY + "\n", encoding="utf-8")
    s = get_live_suggester()
    assert isinstance(s, GeminiSuggester) and s._key == KEY  # 줄바꿈 제거
    monkeypatch.delenv("YTWEB_GEMINI_KEY_FILE")
    assert isinstance(get_live_suggester(), RuleSuggester)


def test_default_model_is_an_alias_not_a_retired_version(monkeypatch):
    monkeypatch.delenv("YTWEB_GEMINI_MODEL", raising=False)
    assert GeminiSuggester(KEY).model == "gemini-flash-latest"
    monkeypatch.setenv("YTWEB_GEMINI_MODEL", "my-model")
    assert GeminiSuggester(KEY).model == "my-model"
