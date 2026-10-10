"""FastAPI 앱 팩토리. 라우터는 `ytweb.routers.*` 중 `router` 속성이 있는 모듈을 자동으로 포함한다."""
from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from ytitle.config import load_settings

from ytweb.config import WebSettings, load_web_settings
from ytweb.core.clock import utcnow
from ytweb.core.errors import PROBLEM_MEDIA_TYPE, ProblemError, problem_body
from ytweb.core.guard import GuardMiddleware
from ytweb.core.logsetup import setup_logging
from ytweb.core.ratelimit import RateLimiter, RateLimits
from ytweb.db.models import Base
from ytweb.db.session import make_engine, make_session_factory

log = logging.getLogger("ytweb.app")

_HTTP_TITLES = {404: "찾을 수 없습니다.", 405: "허용되지 않는 요청 방식입니다.", 415: "지원하지 않는 형식입니다."}


def problem_response(status: int, code: str, title: str, detail: str = "", hint: str = "", headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(problem_body(status, code, title, detail, hint), status_code=status,
                        media_type=PROBLEM_MEDIA_TYPE, headers=headers)


def discover_routers(package: str = "ytweb.routers") -> list[str]:
    pkg = importlib.import_module(package)
    names = []
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue
        full = f"{package}.{mod.name}"
        if hasattr(importlib.import_module(full), "router"):
            names.append(full)
    return sorted(names)


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(_: Request, exc: ProblemError):
        return problem_response(exc.status, exc.code, exc.title, exc.detail, exc.hint, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return problem_response(exc.status_code, code, _HTTP_TITLES.get(exc.status_code, "요청을 처리할 수 없습니다."),
                                headers=dict(exc.headers) if exc.headers else None)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        # 입력값을 되돌려 보내지 않는다(비밀 에코 방지): 위치와 사유만.
        parts = [f"{'.'.join(str(p) for p in e.get('loc', ()) if p != 'body')}: {e.get('msg', '')}" for e in exc.errors()[:10]]
        return problem_response(422, "validation_error", "요청 값이 올바르지 않습니다.", "; ".join(parts),
                                "필드 형식과 허용 범위를 확인하세요.")


def _mount_static(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()
    index = root / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str):
        if full_path.startswith("api/") or full_path in ("api", "healthz", "readyz"):
            raise StarletteHTTPException(404)
        target = (root / full_path).resolve()
        if full_path and target.is_file() and (root == target.parent or root in target.parents):
            return FileResponse(target)
        if index.is_file():
            return FileResponse(index)
        raise StarletteHTTPException(404)


def create_app(
    settings: WebSettings | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    router_modules: list[str] | None = None,
    rate_limits: RateLimits | None = None,
    time_fn: Callable[[], float] | None = None,
) -> FastAPI:
    settings = settings or load_web_settings()
    setup_logging(json_format=settings.log_json)

    engine = make_engine(settings.database_url)
    if settings.database_url.startswith("sqlite") and os.environ.get("YTWEB_AUTO_CREATE") == "1":
        Base.metadata.create_all(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title="ytitle web",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )
    app.state.web_settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.policy = load_settings(settings.base_dir, env={})
    app.state.clock = clock or utcnow

    _register_error_handlers(app)

    limiter_kwargs = {"time_fn": time_fn} if time_fn else {}
    app.add_middleware(
        GuardMiddleware,
        allowed_hosts=settings.allowed_hosts,
        limiter=RateLimiter(rate_limits or RateLimits(), **limiter_kwargs),
        docs_enabled=settings.enable_docs,
    )

    for name in router_modules if router_modules is not None else discover_routers():
        app.include_router(importlib.import_module(name).router)

    static = os.environ.get("YTWEB_STATIC_DIR")
    if static and Path(static).is_dir():
        _mount_static(app, Path(static))
    return app


def app_from_env() -> FastAPI:
    """uvicorn --factory ytweb.app:app_from_env"""
    return create_app()
