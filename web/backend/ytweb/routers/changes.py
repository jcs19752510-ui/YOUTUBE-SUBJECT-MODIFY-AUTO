from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ytweb.core.deps import get_clock, get_idempotency_key, get_session, require_csrf, require_session
from ytweb.db.models import Video
from ytweb.domain.changes import list_changes_with_kind, rollback_change
from ytweb.domain.common import VIDEO_ID_PATTERN, Env
from ytweb.domain.kinds import video_kind
from ytweb.domain.deps import get_env, get_gateway, idempotent
from ytweb.domain.schemas import MAX_ID, MAX_PAGE, ChangeOut, Page, RollbackIn
from ytweb.domain.serialize import change_dict
from ytweb.youtube.base import YouTubeGateway

router = APIRouter(prefix="/api/v1/changes", tags=["changes"])


@router.get("", response_model=Page[ChangeOut])
def get_changes(
    video_id: str | None = Query(default=None, pattern=VIDEO_ID_PATTERN), batch_id: int | None = Query(default=None, ge=1, le=MAX_ID),
    result: Literal["planned", "success", "failed", "aborted"] | None = None,
    page: int = Query(1, ge=1, le=MAX_PAGE), page_size: int = Query(50, ge=1, le=200),
    date_from: date | None = None, date_to: date | None = None, kind: Literal["long", "short"] | None = None,
    session: Session = Depends(get_session), _=Depends(require_session),
):
    pairs, rb, total, kinds = list_changes_with_kind(session, video_id=video_id, batch_id=batch_id, result=result, page=page, page_size=page_size, date_from=date_from, date_to=date_to, kind=kind)
    return {"items": [change_dict(c, t, rb[c.id], kinds[c.id]) for c, t in pairs], "total": total, "page": page, "page_size": page_size}


@router.post("/{change_id}/rollback", status_code=201, response_model=ChangeOut)
def post_rollback(
    body: RollbackIn, change_id: int = Path(ge=1, le=MAX_ID), key: str | None = Depends(get_idempotency_key),
    session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), env: Env = Depends(get_env),
    gateway: YouTubeGateway = Depends(get_gateway), _=Depends(require_csrf),
):
    now = clock()

    def handler():
        rb = rollback_change(session, change_id, body.typed_video_id, body.approver, now=now, env=env, gateway=gateway)
        video = session.get(Video, rb.video_id)
        return 201, change_dict(rb, video.title if video else None, False, video_kind(video.is_short, video.duration_sec) if video else None)

    status, payload = idempotent(session, key=key, route=f"POST /api/v1/changes/{change_id}/rollback", request={"id": change_id, **body.model_dump()}, now=now, handler=handler)
    return JSONResponse(payload, status_code=status)
