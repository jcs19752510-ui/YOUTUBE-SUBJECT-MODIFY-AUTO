"""검증 전용 프로브 라우터(소스 수정 없이 core 기능을 HTTP 로 두드리기 위한 테스트 전용 모듈)."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session
from ytweb.core.deps import (
    get_clock,
    get_idempotency_key,
    get_session,
    require_csrf,
    require_session,
)
from ytweb.core.errors import ProblemError
from ytweb.core.idempotency import run_idempotent

router = APIRouter(prefix="/api/v1/_t")
CALLS: dict[str, int] = {}
FAIL_NEXT = {"flag": False}
SECRET_IN_EXC = "SuperSecretValue-9f8e7d"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int


def _do(route: str, body: dict, key: str | None, db: Session, clock: Callable[[], datetime]):
    def handler():
        CALLS[route] = CALLS.get(route, 0) + 1
        if FAIL_NEXT["flag"]:
            FAIL_NEXT["flag"] = False
            raise ProblemError(409, "probe_conflict", "프로브 충돌")
        return 201, {"route": route, "count": CALLS[route], "at": clock(), "echo": body}

    status, payload = run_idempotent(db, key=key, route=route, request=body, now=clock(), handler=handler)
    return JSONResponse(payload, status_code=status)


@router.post("/charge")
def charge(body: dict[str, Any], _=Depends(require_csrf), key: str | None = Depends(get_idempotency_key),
           db: Session = Depends(get_session), clock=Depends(get_clock)):
    return _do("charge", body, key, db, clock)


@router.post("/charge2")
def charge2(body: dict[str, Any], _=Depends(require_csrf), key: str | None = Depends(get_idempotency_key),
            db: Session = Depends(get_session), clock=Depends(get_clock)):
    return _do("charge2", body, key, db, clock)


@router.get("/boom")
def boom():
    raise RuntimeError(f"/home/user/secret/path.py exploded token={SECRET_IN_EXC}")


@router.get("/dberr")
def dberr(db: Session = Depends(get_session)):
    db.execute(text("INSERT INTO settings_kv(key, value, updated_at) VALUES ('dup', '1', '2026-01-01')"))
    db.execute(text("INSERT INTO settings_kv(key, value, updated_at) VALUES ('dup', '1', '2026-01-01')"))


@router.get("/dberr-param")
def dberr_param(db: Session = Depends(get_session)):
    """파라미터 값이 예외 문자열에 실리는지 보기 위한 경로(고유 제약 위반)."""
    stmt = text("INSERT INTO settings_kv(key, value, updated_at) VALUES (:k, :v, :t)")
    row = {"k": "dup2", "v": '"PinHash-Looking-Value-ABC"', "t": "2026-01-01"}
    db.execute(stmt, row)
    db.execute(stmt, row)


@router.get("/http")
def http_exc():
    raise HTTPException(status_code=418, detail=f"/etc/shadow {SECRET_IN_EXC}")


@router.post("/validate")
def validate(body: Strict, _=Depends(require_csrf)):
    return {"ok": True}


@router.get("/needs-session")
def needs_session(_=Depends(require_session)):
    return {"ok": True}
