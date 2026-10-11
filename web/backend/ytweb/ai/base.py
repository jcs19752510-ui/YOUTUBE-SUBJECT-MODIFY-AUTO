"""제목 제안기 어댑터 규약. 실서비스로 바꿀 때 이 프로토콜만 구현하면 된다(S-W06, S-W07).

보안 원칙(규칙 J): 어댑터는 텍스트만 만들어 돌려주며 도구·DB·네트워크 권한이 없다. 입력은 제목+설명 요약뿐이고
(자막·성과·토큰 제외), 응답은 항상 `ai.guard.sanitize_drafts` 를 거친 뒤 기존 검증기를 통과해야 후보가 된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VideoBrief:
    """AI 로 보내는 전송 최소 입력."""

    video_id: str
    title: str
    summary: str


@dataclass(frozen=True)
class SuggestionDraft:
    title: str
    evidence: str
    topic: str | None  # life | health | finance | None(모름 → 엄격 모드)


class TitleSuggestionError(Exception):
    """제안기 장애(타임아웃·형식 오류·한도 초과 등). 메시지에는 비밀·원문을 넣지 않는다."""


class TitleSuggester(Protocol):
    name: str          # ai_runs.provider 및 suggestions.source('ai:<name>')
    model: str | None

    def suggest(self, brief: VideoBrief, *, count: int, tone: str) -> list[SuggestionDraft]: ...
