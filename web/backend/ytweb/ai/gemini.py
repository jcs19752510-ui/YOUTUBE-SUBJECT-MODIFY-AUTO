"""Gemini 제안기(실제 영상용). 선생님 본인의 API 키(web/secrets/gemini_api_key)로 구글 생성 AI 를 호출한다.

보안(규칙 J): 이 어댑터는 텍스트만 만들고 도구·DB 권한이 없다. 보내는 것은 현재 제목과 영상 설명 요약뿐이며(`VideoBrief`),
키는 헤더로만 보내고 로그·오류 메시지·응답에 넣지 않는다. 응답은 `ai.guard.sanitize_drafts` 와 기존 검증기를 거친 뒤에만 후보가 된다.
표준 라이브러리만 쓴다(새 의존성 없음).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from ytweb.ai.base import SuggestionDraft, TitleSuggestionError, VideoBrief

DEFAULT_MODEL = "gemini-flash-latest"  # 특정 버전(예: 2.5)은 신규 사용자에게 막히므로 별칭을 쓴다. YTWEB_GEMINI_MODEL 로 바꿀 수 있다.
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_SEC = 60
MAX_OUTPUT_TOKENS = 16384  # 이 모델은 생각 토큰(실측 약 3,800개)도 출력 한도에서 쓴다. 4000 이면 JSON 이 잘려 실패했다(2026-10-13 실측)
ATTEMPTS = 3  # 구글 서버의 일시 오류(5xx)와 응답 잘림은 잠시 뒤 다시 시도한다. 429(사용량 한도)는 수 초 뒤에도 풀리지 않아 재시도하지 않고 바로 안내한다(2026-10-13 실측)
RETRY_WAIT_SEC = (1.5, 3.0)
RETRYABLE_HTTP = (500, 502, 503, 504)
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")  # 요청 주소에 들어가므로 / ? # : 등을 막는다(DEF-D-001)

SYSTEM_PROMPT = (
    "당신은 50~70대 시니어 시청자를 위한 유튜브 채널 '시니어 생활팁'의 제목 편집자입니다. "
    "주어진 영상 제목과 설명만 근거로 새 제목 후보를 만듭니다.\n"
    "규칙:\n"
    "1. 각 제목은 공백 포함 45~60자의 자연스러운 한국어 한 문장입니다. 설명의 챕터 문구를 그대로 나열하지 않고 읽기 좋게 다듬습니다.\n"
    "2. 영상 설명에 없는 내용은 쓰지 않습니다. 과장·단정(무조건, 100%, 최고, 완치, 기적, 확정, 보장)과 공포 조장은 금지입니다.\n"
    "3. 제목의 핵심 낱말 절반 이상은 영상 설명에 나온 글자 그대로 씁니다(활용형으로 바꾸지 않습니다).\n"
    "4. 영상의 핵심 주제어(예: 통역, 번역)를 제목 앞쪽 20자 안에 넣습니다. 현재 제목 맨 앞의 말머리(예: [시니어 필수])가 있으면 그대로 유지합니다.\n"
    "5. 후보마다 방향을 다르게 합니다(걱정 해소, 쉬움 강조, 구체적 기능 등). 느낌표는 최대 1개이고 이모지·링크·연락처는 쓰지 않습니다.\n"
    "6. evidence 에는 제목의 근거가 되는 문구를 영상 설명에서 한 글자도 바꾸지 말고 그대로 복사합니다.\n"
    "7. topic 은 life, health, finance 중 하나입니다.\n"
    "8. 이미 만든 제목(이미_만든_제목)과 같거나 거의 같은 제목은 다시 만들지 않습니다."
)
_SCHEMA = {
    "type": "OBJECT",
    "properties": {"candidates": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "title": {"type": "STRING"}, "evidence": {"type": "STRING"}, "topic": {"type": "STRING", "enum": ["life", "health", "finance"]},
    }, "required": ["title", "evidence", "topic"]}}},
    "required": ["candidates"],
}


def read_key(path: str | os.PathLike[str] | None) -> str | None:
    """키 파일을 읽는다(없거나 비어 있으면 None). 키 값은 어디에도 기록하지 않는다."""
    if not path:
        return None
    try:
        key = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return key or None


class GeminiSuggester:
    name = "gemini"

    def __init__(self, api_key: str | None, model: str | None = None, *, avoid_titles: tuple[str, ...] = ()) -> None:
        self._key = api_key
        self.model: str | None = model or os.environ.get("YTWEB_GEMINI_MODEL") or DEFAULT_MODEL
        self._avoid = avoid_titles

    def with_avoid(self, titles: set[str] | tuple[str, ...]) -> "GeminiSuggester":
        return GeminiSuggester(self._key, self.model, avoid_titles=tuple(sorted(titles))[:20])

    def suggest(self, brief: VideoBrief, *, count: int, tone: str) -> list[SuggestionDraft]:
        payload = {"현재_제목": brief.title, "영상_설명": brief.summary, "후보_수": count, "이미_만든_제목": list(self._avoid)}
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": MAX_OUTPUT_TOKENS, "responseMimeType": "application/json", "responseSchema": _SCHEMA},
        }
        if not _MODEL_NAME.fullmatch(self.model or ""):
            raise TitleSuggestionError("Gemini 모델 이름(YTWEB_GEMINI_MODEL) 형식이 올바르지 않습니다. 영문·숫자·.·_·- 만 쓸 수 있습니다.")
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["x-goog-api-key"] = self._key
        req = urllib.request.Request(ENDPOINT.format(model=self.model), data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        for attempt in range(ATTEMPTS):
            last = attempt == ATTEMPTS - 1
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:  # noqa: S310 - 고정된 https 주소
                    data = json.load(resp)
            except urllib.error.HTTPError as exc:
                if exc.code in RETRYABLE_HTTP and not last:
                    _sleep(RETRY_WAIT_SEC[min(attempt, len(RETRY_WAIT_SEC) - 1)])
                    continue
                raise TitleSuggestionError(_http_message(exc.code)) from None
            except (urllib.error.URLError, TimeoutError, OSError):
                raise TitleSuggestionError("Gemini 에 연결하지 못했습니다(인터넷 연결 또는 시간 초과).") from None
            except ValueError:
                raise TitleSuggestionError("Gemini 응답을 읽지 못했습니다.") from None
            if _truncated(data) and not last:
                _sleep(RETRY_WAIT_SEC[min(attempt, len(RETRY_WAIT_SEC) - 1)])
                continue
            return _parse(data, count)
        raise TitleSuggestionError("Gemini 응답을 읽지 못했습니다.")  # 도달하지 않는다(마지막 시도는 위에서 반환·예외)


def _sleep(sec: float) -> None:
    time.sleep(sec)


def _truncated(data: dict) -> bool:
    """출력 한도에 닿아 응답이 중간에 잘렸는지(finishReason=MAX_TOKENS)."""
    try:
        return data["candidates"][0].get("finishReason") == "MAX_TOKENS"
    except (KeyError, IndexError, TypeError, AttributeError):
        return False


def _http_message(code: int) -> str:
    if code in (400, 401, 403):
        return "Gemini 가 요청을 거부했습니다. API 키가 맞는지, 키에 사용 권한이 있는지 확인하세요."
    if code == 404:
        return "Gemini 모델을 찾을 수 없습니다. 모델 이름(YTWEB_GEMINI_MODEL)을 확인하세요."
    if code == 429:
        return "Gemini 사용량 한도에 걸렸습니다. 잠시 후 다시 시도하세요."
    return f"Gemini 서버 오류({code})입니다. 잠시 후 다시 시도하세요."


def _parse(data: dict, count: int) -> list[SuggestionDraft]:
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        items = json.loads(text)["candidates"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise TitleSuggestionError("Gemini 응답 형식이 올바르지 않습니다.") from None
    out: list[SuggestionDraft] = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not isinstance(it.get("title"), str) or not it["title"].strip():
            continue
        topic = it.get("topic") if it.get("topic") in ("life", "health", "finance") else None
        out.append(SuggestionDraft(it["title"].strip(), str(it.get("evidence") or "").strip(), topic))
    return out[: max(1, count)]
