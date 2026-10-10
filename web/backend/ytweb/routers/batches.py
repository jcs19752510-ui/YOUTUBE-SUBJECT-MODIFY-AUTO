from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ytweb.core.deps import get_clock, get_idempotency_key, get_session, require_csrf, require_session
from ytweb.domain.batches import cancel_batch, create_draft, execute_batch, get_batch, list_batches
from ytweb.domain.common import Env
from ytweb.domain.deps import get_env, idempotent
from ytweb.domain.schemas import BatchCreatedOut, BatchCreateIn, BatchExecutedOut, BatchOut, ExecuteIn, Page
from ytweb.domain.serialize import batch_dict, job_dict

router = APIRouter(prefix="/api/v1/batches", tags=["batches"])


@router.post("", status_code=201, response_model=BatchCreatedOut)
def post_batch(
    body: BatchCreateIn, key: str | None = Depends(get_idempotency_key), session: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock), env: Env = Depends(get_env), _=Depends(require_csrf),
):
    now = clock()

    def handler():
        batch, precheck = create_draft(session, body.suggestion_ids, body.note, now=now, env=env)
        return 201, {"batch": batch_dict(session, batch), "precheck": precheck}

    status, payload = idempotent(session, key=key, route="POST /api/v1/batches", request=body.model_dump(), now=now, handler=handler)
    return JSONResponse(payload, status_code=status)


@router.get("", response_model=Page[BatchOut])
def get_batches(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), session: Session = Depends(get_session), _=Depends(require_session)):
    rows, total = list_batches(session, page=page, page_size=page_size)
    return {"items": [batch_dict(session, b, with_items=False) for b in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/{batch_id}", response_model=BatchOut)
def get_one(batch_id: int = Path(ge=1), session: Session = Depends(get_session), _=Depends(require_session)):
    return batch_dict(session, get_batch(session, batch_id))


@router.post("/{batch_id}/execute", status_code=202, response_model=BatchExecutedOut)
def post_execute(
    body: ExecuteIn, batch_id: int = Path(ge=1), key: str | None = Depends(get_idempotency_key), session: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock), env: Env = Depends(get_env), _=Depends(require_csrf),
):
    now = clock()

    def handler():
        batch, job = execute_batch(session, batch_id, body.confirm_text, now=now, env=env)
        return 202, {"batch": batch_dict(session, batch), "job": job_dict(job)}

    status, payload = idempotent(session, key=key, route=f"POST /api/v1/batches/{batch_id}/execute", request={"id": batch_id, **body.model_dump()}, now=now, handler=handler)
    return JSONResponse(payload, status_code=status)


@router.post("/{batch_id}/cancel", response_model=BatchOut)
def post_cancel(batch_id: int = Path(ge=1), session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), env: Env = Depends(get_env), _=Depends(require_csrf)):
    batch = cancel_batch(session, batch_id, now=clock(), env=env)
    return batch_dict(session, batch)
