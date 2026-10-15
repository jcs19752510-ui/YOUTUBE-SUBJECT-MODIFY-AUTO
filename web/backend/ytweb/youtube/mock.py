"""DB 의 `videos` 행을 유튜브처럼 쓰는 모의 게이트웨이(데모 모드 전용)."""
from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from ytweb.core.clock import utcnow
from ytweb.db.models import Video
from ytweb.youtube.base import GatewayError, make_excerpt


class MockYouTubeGateway:
    def __init__(self, session: Session, clock: Callable[[], datetime] = utcnow) -> None:
        self._session = session
        self._clock = clock

    def read_snippet(self, video_id: str) -> dict | None:
        video = self._session.get(Video, video_id)
        return None if video is None else copy.deepcopy(video.snippet)

    def update_snippet(self, video_id: str, body: dict) -> dict:
        video = self._session.get(Video, video_id)
        if video is None:
            raise GatewayError("video_not_found", "영상을 찾을 수 없습니다.")
        snippet = body.get("snippet") if isinstance(body, dict) else None
        if body.get("id") != video_id or not isinstance(snippet, dict):
            raise GatewayError("invalid_request", "요청 본문의 영상 ID 또는 snippet 이 올바르지 않습니다.")
        if not isinstance(snippet.get("title"), str) or not snippet["title"].strip():
            raise GatewayError("invalid_request", "snippet.title 이 비어 있습니다.")
        if not isinstance(snippet.get("categoryId"), str) or not snippet["categoryId"]:
            raise GatewayError("invalid_request", "snippet.categoryId 가 없습니다(유튜브는 제목 변경에도 categoryId 를 요구합니다).")
        new = copy.deepcopy(snippet)  # 통째 교체: body 에 없는 항목은 사라진다
        if isinstance(new.get("localized"), dict):
            new["localized"] = {**new["localized"], "title": new["title"]}
        video.snippet = new
        video.title = new["title"]
        video.category_id = new["categoryId"]
        video.description_excerpt = make_excerpt(new.get("description"))
        video.fetched_at = self._clock()
        self._session.flush()
        return copy.deepcopy(new)
