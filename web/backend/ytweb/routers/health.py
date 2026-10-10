"""생존/준비 점검. nginx 가 /api/healthz 로도 노출하므로 두 경로를 모두 둔다."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ytweb.config import WebSettings
from ytweb.core.deps import get_web_settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
@router.get("/api/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
@router.get("/api/readyz")
def readyz(request: Request, settings: WebSettings = Depends(get_web_settings)):
    try:
        with request.app.state.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "degraded", "db": "down", "mode": settings.mode}, status_code=503)
    return {"status": "ok", "db": "ok", "mode": settings.mode}
