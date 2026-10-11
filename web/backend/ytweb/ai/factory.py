"""모드별 제안기 선택. M1 은 데모 모드뿐이라 항상 모의 제안기다(실서비스 어댑터는 M3, 사용자 승인 후)."""
from __future__ import annotations

from ytweb.ai.base import TitleSuggester
from ytweb.ai.mock import MockSuggester


def get_suggester(mode: str = "demo") -> TitleSuggester:
    if mode != "demo":
        raise ValueError(f"지원하지 않는 모드입니다: {mode!r}")
    return MockSuggester()
