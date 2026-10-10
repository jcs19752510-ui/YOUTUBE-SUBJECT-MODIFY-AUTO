"""Idempotency-Key 처리(WEB_DESIGN §3, §10). 같은 키+같은 요청=저장된 응답 재생."""
from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ytweb.core.canonical import canonical_json, sha256_hex
from ytweb.core.errors import ProblemError
from ytweb.db.models import IdempotencyKey

KEY_TTL = timedelta(hours=24)
_KEY_RE = re.compile(r"^[A-Za-z0-9._:\-]{8,80}$")


def run_idempotent(
    session: Session,
    *,
    key: str | None,
    route: str,
    request: dict,
    now: datetime,
    handler: Callable[[], tuple[int, Any]],
    required: bool = True,
) -> tuple[int, Any]:
    if key is None or key == "":
        if required:
            raise ProblemError(400, "idempotency_key_required", "Idempotency-Key 헤더가 필요합니다.",
                               hint="요청마다 새로 만든 고유 값(UUID 권장)을 Idempotency-Key 헤더에 넣으세요.")
        return handler()
    if not _KEY_RE.match(key):
        raise ProblemError(400, "idempotency_key_invalid", "Idempotency-Key 형식이 올바르지 않습니다.",
                           hint="영문·숫자·._:- 만 사용해 8~80자로 만드세요.")

    request_hash = sha256_hex(canonical_json(jsonable_encoder(request)))
    row = session.get(IdempotencyKey, key)
    if row is not None and row.created_at < now - KEY_TTL:
        session.execute(delete(IdempotencyKey).where(IdempotencyKey.key == key))
        session.flush()
        row = None
    if row is not None:
        if row.route != route or row.request_hash != request_hash:
            raise ProblemError(422, "idempotency_key_reuse", "같은 Idempotency-Key 로 다른 요청을 보냈습니다.",
                               hint="새 요청에는 새 키를 사용하세요.")
        if row.response_status is None:
            raise ProblemError(409, "idempotency_in_progress", "같은 키의 요청이 아직 처리 중입니다.",
                               hint="잠시 후 같은 요청을 다시 보내세요.")
        return row.response_status, row.response_body

    row = IdempotencyKey(key=key, route=route, request_hash=request_hash, created_at=now)
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ProblemError(409, "idempotency_in_progress", "같은 키의 요청이 동시에 처리 중입니다.",
                           hint="잠시 후 같은 요청을 다시 보내세요.") from None

    status, body = handler()
    encoded = jsonable_encoder(body)
    row.response_status = status
    row.response_body = encoded
    session.flush()
    return status, encoded
