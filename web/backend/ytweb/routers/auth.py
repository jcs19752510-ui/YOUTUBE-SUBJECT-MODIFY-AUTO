"""세션 발급·확인·로그아웃. 토큰 원문은 Set-Cookie 로만 나가고 DB 에는 sha256 만 남는다."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ytweb.config import WebSettings
from ytweb.core import admin_account, audit
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
    delete_other_sessions,
    delete_session,
    lookup_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pin: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login_id: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


def _idle_seconds(settings: WebSettings) -> int | None:
    timeout = settings.session_idle_timeout
    return int(timeout.total_seconds()) if timeout is not None else None


def _set_cookie(response: Response, token: str, ttl_hours: int) -> None:
    # http://127.0.0.1 에서는 Secure 를 붙이지 않는다(설계 질문 Q-WA-1). __Host- 접두사도 쓰지 않는다(Path=/api 필요).
    response.set_cookie(COOKIE_NAME, token, max_age=ttl_hours * 3600, path=COOKIE_PATH, httponly=True, samesite="strict", secure=False)


@router.get("/me")
def me(
    request: Request,
    db: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock),
) -> dict:
    """상태 확인. 로그인 중이면 호출 자체가 마지막 사용 시각을 갱신한다(화면의 '계속 사용')."""
    settings: WebSettings = request.app.state.web_settings
    info = lookup_session(db, request.cookies.get(COOKIE_NAME), now=clock(), idle_timeout=settings.session_idle_timeout)
    login_mode = settings.admin_login
    return {
        "authenticated": info is not None,
        "pin_required": False if login_mode else pin_required(db),
        "csrf_token": info.csrf_token if info else None,
        "login_required": login_mode and info is None,
        "admin_login_id": admin_account.admin_login_id(db) if login_mode and info else None,
        "idle_timeout_seconds": _idle_seconds(settings),
    }


def _origin_first(request: Request, settings: WebSettings = Depends(get_web_settings)) -> None:
    """본문 검증(422)보다 먼저 출처를 검사한다(비허용 출처에는 어떤 형식 정보도 알리지 않음)."""
    verify_same_origin(request, settings)


@router.post("/login", dependencies=[Depends(_origin_first)])
def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock),
    settings: WebSettings = Depends(get_web_settings),
) -> dict:
    verify_same_origin(request, settings)
    if not settings.admin_login:
        raise ProblemError(409, "login_disabled", "이 서버는 로그인 기능이 꺼져 있습니다.",
                           hint="로그인 없이 바로 사용할 수 있습니다.")
    now = clock()
    try:
        account = admin_account.authenticate(db, body.login_id, body.password, now=now)
    except ProblemError as exc:
        audit.record(db, actor="owner", action="login.denied", target_type="session", detail={"code": exc.code}, now=now)
        db.commit()
        raise
    token, info = create_session(db, now=now, ttl_hours=settings.session_ttl_hours, idle_timeout=settings.session_idle_timeout)
    delete_other_sessions(db, info.session_id)  # 관리자 1명: 새 로그인이 이전 세션을 모두 끝낸다(세션 고정 방지)
    audit.record(db, actor="owner", action="login.success", target_type="session", target_id=info.session_id[:12], now=now)
    _set_cookie(response, token, settings.session_ttl_hours)
    return {"csrf_token": info.csrf_token, "admin_login_id": account.login_id, "idle_timeout_seconds": _idle_seconds(settings)}


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
    if settings.admin_login:
        raise ProblemError(403, "login_required", "아이디와 비밀번호로 로그인해야 합니다.", hint="로그인 화면에서 아이디와 비밀번호를 입력하세요.")
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
