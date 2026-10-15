"""FastAPI 의존성(WEB_DESIGN §10). 앱 상태(app.state)는 app.py 의 create_app 이 채운다."""
from __future__ import annotations

import hmac
from collections.abc import Callable, Iterator
from datetime import datetime

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session
from youtube_title.config import Settings

from ytweb.config import WebSettings
from ytweb.core.errors import ProblemError
from ytweb.core.sessions import COOKIE_NAME, SessionInfo, lookup_session
from ytweb.db.session import session_scope

OPEN_SESSIONS_KEY = "ytweb_open_sessions"


def get_session(request: Request) -> Iterator[Session]:
    """요청 범위 DB 세션. FastAPI 는 yield 뒤의 종료 코드를 응답 전송 '뒤에' 실행하므로, 성공 응답이 나가기 전에
    GuardMiddleware 가 이 목록의 세션을 먼저 commit 한다(DEF-VA-010). 여기서의 종료 commit 은 오류 경로(rollback)와 이중 안전장치다."""
    for session in session_scope(request.app.state.session_factory):
        request.scope.setdefault(OPEN_SESSIONS_KEY, []).append(session)
        yield session


def get_web_settings(request: Request) -> WebSettings:
    return request.app.state.web_settings


def get_policy(request: Request) -> Settings:
    return request.app.state.policy


def get_clock(request: Request) -> Callable[[], datetime]:
    return request.app.state.clock


def allowed_origins(settings: WebSettings) -> set[str]:
    return {f"http://{h.lower()}" for h in settings.allowed_hosts}


def verify_same_origin(request: Request, settings: WebSettings) -> None:
    """상태 변경 요청 검증. Sec-Fetch-Site 가 있으면 same-origin 만 통과(같은 PC 다른 포트도 same-site 로 분류되므로 거부),
    Origin 은 항상 허용 출처와 일치해야 한다(헤더 없는 비브라우저 클라이언트 포함)."""
    sec = request.headers.get("sec-fetch-site")
    if sec is not None and sec.strip().lower() != "same-origin":
        raise ProblemError(403, "cross_site_request", "다른 사이트에서 온 요청은 허용되지 않습니다.",
                           hint="프로그램 화면(허용된 주소)에서 직접 실행하세요.")
    origin = request.headers.get("origin")
    if origin is None or origin.strip().lower() not in allowed_origins(settings):
        raise ProblemError(403, "origin_not_allowed", "허용되지 않은 출처의 요청입니다.",
                           hint="http://127.0.0.1:8080 주소로 접속해 사용하세요.")


def require_session(
    request: Request,
    db: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock),
) -> SessionInfo:
    info = lookup_session(db, request.cookies.get(COOKIE_NAME), now=clock(), idle_timeout=request.app.state.web_settings.session_idle_timeout)
    if info is None:
        raise ProblemError(401, "session_required", "세션이 없거나 만료되었습니다.", hint="화면을 새로고침해 다시 시작하세요.")
    return info


def require_csrf(
    request: Request,
    db: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock),
    settings: WebSettings = Depends(get_web_settings),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> SessionInfo:
    verify_same_origin(request, settings)  # 출처 검증을 세션 확인보다 먼저(비허용 출처에는 세션 존재 여부도 알리지 않음)
    info = require_session(request, db, clock)
    if not x_csrf_token or not hmac.compare_digest(x_csrf_token.encode(), info.csrf_token.encode()):
        raise ProblemError(403, "csrf_invalid", "요청 확인 토큰(CSRF)이 올바르지 않습니다.", hint="화면을 새로고침한 뒤 다시 시도하세요.")
    return info


def get_idempotency_key(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str | None:
    return idempotency_key
