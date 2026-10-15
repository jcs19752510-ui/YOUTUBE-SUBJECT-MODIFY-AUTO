"""유튜브 게이트웨이 규약. 쓰기 호출은 도메인에서 이 규약을 통해서만 일어난다(M3 라이브 게이트웨이도 같은 규약)."""
from __future__ import annotations

from typing import Protocol

EXCERPT_CHARS = 280


def make_excerpt(description: str | None) -> str | None:
    text = " ".join((description or "").split())
    return text[:EXCERPT_CHARS] or None


class GatewayError(Exception):
    """게이트웨이 호출 실패. definite=True 면 요청이 처리되지 않았음이 분명하고, False 면 반영됐는지 알 수 없다."""

    def __init__(self, code: str, message: str, *, definite: bool = True) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.definite = definite


class YouTubeGateway(Protocol):
    def read_snippet(self, video_id: str) -> dict | None:
        """영상의 현재 snippet 전체. 없으면 None."""

    def update_snippet(self, video_id: str, body: dict) -> dict:
        """videos.update(part=snippet) 흉내. body = {"id": video_id, "snippet": {...}}. 갱신 후 snippet 을 돌려준다.

        유튜브는 snippet 을 통째로 교체하므로 body 에 빠진 항목(description·tags 등)은 사라진다 — 구현은 이 동작을 그대로 따라야 한다."""
