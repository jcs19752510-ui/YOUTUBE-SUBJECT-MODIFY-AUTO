"""모드별 제안기 선택. 데모 모드는 모의 제안기, 실제 영상은 Gemini 키가 있으면 Gemini, 없으면 규칙 기반 제안기."""
from __future__ import annotations

import os

from ytweb.ai.base import TitleSuggester
from ytweb.ai.gemini import GeminiSuggester, read_key
from ytweb.ai.mock import MockSuggester
from ytweb.ai.rule import RuleSuggester

GEMINI_KEY_FILE_ENV = "YTWEB_GEMINI_KEY_FILE"


def get_suggester(mode: str = "demo") -> TitleSuggester:
    if mode != "demo":
        raise ValueError(f"지원하지 않는 모드입니다: {mode!r}")
    return MockSuggester()


def get_live_suggester() -> TitleSuggester:
    """실제(youtube) 영상용. 키 파일이 있고 비어 있지 않으면 Gemini, 아니면 외부 통신 없는 규칙 기반."""
    key = read_key(os.environ.get(GEMINI_KEY_FILE_ENV))
    return GeminiSuggester(key) if key else RuleSuggester()
