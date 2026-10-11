"""세션 발급·확인·로그아웃. 토큰 원문은 Set-Cookie 로만 나가고 DB 에는 sha256 만 남는다."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ytweb.config import WebSettings
from ytweb.core import audit
from ytweb.core.deps import (
    get_clock,
    get_session,
    get_web_settings,
    require_csrf,
    verify_same_origin,
)
from ytweb.core.errors import ProblemError
from ytweb.core.pin import check_pin, pin_required
from ytweb.core.sessions import (
    COOKIE_NAME,
    COOKIE_PATH,
    SessionInfo,
    create_session,
    delete_session,
    lookup_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pin: str | None = Field(default=None, max_length=64)


def _set_cookie(response: Response, token: str, ttl_hours: int) -> None:
    # http://127.0.0.1 에서는 Secure 를 붙이지 않는다(설계 질문 Q-WA-1). __Host- 접두사도 쓰지 않는다(Path=/api 필요).
    response.set_cookie(COOKIE_NAME, token, max_age=ttl_hours * 3600, path=COOKIE_PATH, httponly=True, samesite="strict", secure=False)


@router.get("/me")
def me(
    request: Request,
    db: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock),
) -> dict:
    info = lookup_session(db, request.cookies.get(COOKIE_NAME), now=clock(), idle_timeout=request.app.state.web_settings.session_idle_timeout)
    return {"authenticated": info is not None, "pin_required": pin_required(db), "csrf_token": info.csrf_token if info else None}


@router.post("/session")
def create(
    request: Request,
    response: Response,
    body: SessionRequest | None = None,
    db: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock),
    settings: WebSettings = Depends(get_web_settings),
) -> dict:
    verify_same_origin(request, settings)
    now = clock()
    try:
        check_pin(db, body.pin if body else None, now=now)
    except ProblemError as exc:
        audit.record(db, actor="owner", action="session.denied", target_type="session", detail={"code": exc.code}, now=now)
        db.commit()
        raise
    token, info = create_session(db, now=now, ttl_hours=settings.session_ttl_hours, idle_timeout=settings.session_idle_timeout)
    audit.record(db, actor="owner", action="session.create", target_type="session", target_id=info.session_id[:12],
                 detail={"pin_used": pin_required(db)}, now=now)
    _set_cookie(response, token, settings.session_ttl_hours)
    return {"csrf_token": info.csrf_token}


@router.delete("/session", status_code=204)
def logout(
    info: SessionInfo = Depends(require_csrf),
    db: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock),
) -> Response:
    delete_session(db, info.session_id)
    audit.record(db, actor="owner", action="session.delete", target_type="session", target_id=info.session_id[:12], now=clock())
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, httponly=True, samesite="strict")
    return response
