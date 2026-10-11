"""라우터 공용 의존성. 테스트에서 dependency_overrides 로 게이트웨이·제안기를 바꿔 끼울 수 있다."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import Depends
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ytweb.ai.base import TitleSuggester
from ytweb.ai.factory import get_suggester
from ytweb.config import WebSettings
from ytweb.core.deps import get_clock, get_policy, get_session, get_web_settings
from ytweb.core.errors import ProblemError
from ytweb.core.idempotency import run_idempotent
from ytweb.db.models import IdempotencyKey
from ytweb.domain.common import Env
from ytweb.youtube.base import YouTubeGateway
from ytweb.youtube.mock import MockYouTubeGateway


def get_env(policy=Depends(get_policy), web: WebSettings = Depends(get_web_settings)) -> Env:
    return Env.build(policy, web)


def get_gateway(session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock)) -> YouTubeGateway:
    from ytweb.domain.live_gateway import select_gateway
    return select_gateway(session, clock())


def get_title_suggester(web: WebSettings = Depends(get_web_settings)) -> TitleSuggester:
    return get_suggester(web.mode)


def idempotent(session: Session, *, key: str | None, route: str, request: dict, now: datetime, handler: Callable[[], tuple[int, Any]]) -> tuple[int, Any]:
    """run_idempotent 래퍼. 처리 중 오류로 끝나면 키 자리(응답 없음)를 지워, 같은 키로 다시 시도할 수 있게 한다."""
    failed: list[bool] = []

    def wrapped() -> tuple[int, Any]:
        try:
            return handler()
        except ProblemError:
            failed.append(True)
            raise

    try:
        return run_idempotent(session, key=key, route=route, request=request, now=now, handler=wrapped)
    except ProblemError:
        if failed and key:
            session.rollback()  # 확정되지 않은 변경은 버리고(서비스가 먼저 확정한 기록은 남는다) 키 자리만 정리한다
            session.execute(delete(IdempotencyKey).where(IdempotencyKey.key == key, IdempotencyKey.response_status.is_(None)))
            session.commit()
        raise
