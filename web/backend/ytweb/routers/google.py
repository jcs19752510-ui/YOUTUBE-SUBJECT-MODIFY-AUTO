"""구글(유튜브) 연결 API — M2 단위 2. 읽기 전용 로그인만 다룬다(쓰기 범위·제목 변경 없음).

보안 메모
- `/callback` 은 구글에서 되돌아오는 브라우저 이동이라 세션 쿠키(SameSite=Strict)가 실려 오지 않는다. 대신 1회용 state(256비트, 10분 만료)로
  요청을 묶는다. 이는 'GET 은 상태를 바꾸지 않는다'(S-W03)의 유일한 예외이며, 토큰은 응답·주소·로그에 싣지 않는다.
- 클라이언트 파일은 Docker secret(`/run/secrets/google_client`), 토큰은 명명 볼륨의 0600 파일에 둔다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ytweb.config import WebSettings
from ytweb.core import audit
from ytweb.core.deps import get_clock, get_session, get_web_settings, require_csrf, require_session
from ytweb.core.errors import ProblemError
from ytweb.domain.schemas import GoogleStatusOut
from ytweb.domain import live_gateway as lg
from ytweb.youtube import google_oauth as oauth

router = APIRouter(prefix="/api/v1/google", tags=["google"])

MSG_NO_CLIENT = "데모 모드입니다. 구글 연결 파일(google_client.json)이 없어 실제 유튜브에는 연결할 수 없습니다. 아래 영상은 시연용 가상 데이터입니다."
MSG_READY = "구글 연결 준비가 됐습니다. [구글 계정 연결]을 눌러 로그인하세요. 읽기 전용이라 영상 제목은 바뀌지 않습니다."
MSG_CONNECTED = "구글(유튜브)에 읽기 전용으로 연결돼 있습니다. 영상 제목은 바뀌지 않습니다."


@dataclass
class GoogleCtx:
    pending: oauth.PendingAuth
    store: oauth.TokenStore
    http: oauth.HttpPost
    client_file: Path
    redirect_uri: str
    last_error: str | None = None
    write_states: set = field(default_factory=set)  # 쓰기 권한 로그인으로 시작한 state
    write_store: oauth.TokenStore | None = None


def get_google_ctx(request: Request, settings: WebSettings = Depends(get_web_settings)) -> GoogleCtx:
    ctx = getattr(request.app.state, "google_ctx", None)
    if ctx is None:
        ctx = GoogleCtx(
            pending=oauth.PendingAuth(),
            store=oauth.TokenStore(settings.secrets_dir / "google_token.json"),
            write_store=oauth.TokenStore(settings.secrets_dir / lg.WRITE_TOKEN_FILE),
            http=oauth.default_http_post,
            client_file=Path(os.environ.get("YTWEB_GOOGLE_CLIENT_FILE", "/run/secrets/google_client")),
            redirect_uri=os.environ.get("YTWEB_GOOGLE_REDIRECT_URI", f"http://127.0.0.1:{settings.port}/api/v1/google/callback"),
        )
        request.app.state.google_ctx = ctx
    return ctx


def _status(ctx: GoogleCtx) -> dict:
    client_ready = ctx.client_file.is_file()
    connected = client_ready and ctx.store.load() is not None
    err, ctx.last_error = ctx.last_error, None  # 오류 안내는 한 번만 보여 준다
    msg = MSG_CONNECTED if connected else (MSG_READY if client_ready else MSG_NO_CLIENT)
    write_connected = client_ready and ctx.write_store is not None and ctx.write_store.load() is not None
    allowed = lg.allowed_videos()
    return {"mode": "read" if client_ready else "demo", "connected": connected, "client_ready": client_ready, "message": msg, "last_error": err,
            "write_connected": write_connected, "live_write_enabled": lg.live_write_enabled(), "live_allowed_count": len(allowed),
            "live_write_ready": lg.live_write_enabled() and bool(allowed) and write_connected}


@router.get("/status", response_model=GoogleStatusOut)
def google_status(_=Depends(require_session), ctx: GoogleCtx = Depends(get_google_ctx)):
    return _status(ctx)


@router.post("/connect")
def google_connect(info=Depends(require_csrf), ctx: GoogleCtx = Depends(get_google_ctx),
                   session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock)):
    try:
        client_id, _secret = oauth.load_client(ctx.client_file)
    except oauth.OAuthError as e:
        raise ProblemError(409, "google_client_" + e.code.removeprefix("client_"), "구글 연결 파일 문제", e.message,
                           "web\\secrets\\google_client.json 을 확인한 뒤 start.ps1 을 다시 실행하세요.") from None
    state, challenge = ctx.pending.start()
    audit.record(session, actor="owner", action="google.connect.start", detail={"scope": "readonly"}, now=clock())
    return {"auth_url": oauth.build_auth_url(client_id, ctx.redirect_uri, state, challenge)}


@router.post("/connect-write")
def google_connect_write(info=Depends(require_csrf), ctx: GoogleCtx = Depends(get_google_ctx),
                         session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock)):
    """제목 수정(쓰기) 권한 로그인. 읽기 로그인과 별도 토큰 파일에 저장하며, 이 권한만으로는 실제 수정이 되지 않는다
    (YTWEB_LIVE_WRITE=1 과 허용 영상 목록이 모두 있어야 한다)."""
    try:
        client_id, _secret = oauth.load_client(ctx.client_file)
    except oauth.OAuthError as e:
        raise ProblemError(409, "google_client_" + e.code.removeprefix("client_"), "구글 연결 파일 문제", e.message,
                           "web\\secrets\\google_client.json 을 확인한 뒤 start.ps1 을 다시 실행하세요.") from None
    state, challenge = ctx.pending.start()
    ctx.write_states.add(state)
    if len(ctx.write_states) > oauth.MAX_PENDING:
        ctx.write_states.pop()
    audit.record(session, actor="owner", action="google.connect_write.start", detail={"scope": "force-ssl"}, now=clock())
    return {"auth_url": oauth.build_auth_url(client_id, ctx.redirect_uri, state, challenge, scope=oauth.SCOPE_WRITE)}


def _back(ctx: GoogleCtx, error: str | None = None) -> RedirectResponse:
    if error:
        ctx.last_error = error
    resp = RedirectResponse("/#/", status_code=303)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/callback", include_in_schema=False)
def google_callback(code: str | None = Query(default=None, max_length=2048), state: str | None = Query(default=None, max_length=256),
                    error: str | None = Query(default=None, max_length=100), ctx: GoogleCtx = Depends(get_google_ctx),
                    session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock)):
    is_write = state in ctx.write_states
    ctx.write_states.discard(state)
    try:
        verifier = ctx.pending.finish(state)  # state 가 없거나 이미 썼거나 만료면 여기서 거부(토큰 교환 안 함)
        if error or not code:
            raise oauth.OAuthError("denied", "구글 로그인이 취소됐거나 거부됐습니다. 필요하면 다시 연결해 주세요.")
        client = oauth.load_client(ctx.client_file)
        tokens = oauth.exchange_code(ctx.http, client, code, verifier, ctx.redirect_uri, clock())
    except oauth.OAuthError as e:
        audit.record(session, actor="owner", action="google.connect.failed", detail={"code": e.code}, now=clock())
        return _back(ctx, e.message)
    if is_write and ctx.write_store is not None:
        ctx.write_store.save(tokens)
        audit.record(session, actor="owner", action="google.write_connected", detail={"scope": tokens.get("scope", "")}, now=clock())
        return _back(ctx)
    ctx.store.save(tokens)
    audit.record(session, actor="owner", action="google.connected", detail={"scope": tokens.get("scope", "")}, now=clock())
    return _back(ctx)


@router.post("/disconnect")
def google_disconnect(info=Depends(require_csrf), ctx: GoogleCtx = Depends(get_google_ctx),
                      session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock)):
    ctx.store.clear()
    if ctx.write_store is not None:
        ctx.write_store.clear()
    audit.record(session, actor="owner", action="google.disconnected", now=clock())
    return {"connected": False}
