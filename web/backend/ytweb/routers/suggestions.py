from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ytweb.core import audit, jobs
from ytweb.core.deps import get_clock, get_session, require_csrf, require_session
from ytweb.core.errors import ProblemError
from ytweb.db.models import Video
from ytweb.domain.common import VIDEO_ID_PATTERN, Env
from ytweb.domain.deps import get_env
from ytweb.domain.schemas import ApproveIn, GenerateIn, JobOut, Page, SuggestionOut, TitleEditIn
from ytweb.domain.serialize import job_dict, suggestion_dict
from ytweb.domain.suggestions import approve, edit_title, list_suggestions, reject

router = APIRouter(prefix="/api/v1/suggestions", tags=["suggestions"])


@router.post("/generate", status_code=202, response_model=JobOut)
def post_generate(body: GenerateIn, session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), _=Depends(require_csrf)):
    ids = list(dict.fromkeys(body.video_ids))
    found = set(session.execute(select(Video.video_id).where(Video.video_id.in_(ids))).scalars())
    missing = [v for v in ids if v not in found]
    if missing:
        raise ProblemError(404, "video_not_found", "목록에 없는 영상이 있습니다.", detail=", ".join(missing[:5]), hint="영상 목록을 새로고침한 뒤 다시 선택하세요.")
    now = clock()
    job = jobs.enqueue(session, type="suggestions.generate", payload={"video_ids": ids, "count": body.count}, total=len(ids), now=now)
    audit.record(session, actor="web", action="suggestion.generate_request", target_type="job", target_id=job.id, detail={"videos": len(ids)}, now=now)
    return job_dict(job)


@router.get("", response_model=Page[SuggestionOut])
def get_suggestions(
    video_id: str | None = Query(default=None, pattern=VIDEO_ID_PATTERN),
    status: Literal["candidate", "approved", "queued", "applied", "rolled_back", "rejected", "blocked", "expired"] | None = None,
    result: Literal["pass", "warn", "block"] | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), _=Depends(require_session),
):
    rows, total = list_suggestions(session, video_id=video_id, status=status, result=result, page=page, page_size=page_size, now=clock())
    return {"items": [suggestion_dict(s) for s in rows], "total": total, "page": page, "page_size": page_size}


@router.patch("/{suggestion_id}", response_model=SuggestionOut)
def patch_suggestion(body: TitleEditIn, suggestion_id: int = Path(ge=1), session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), env: Env = Depends(get_env), _=Depends(require_csrf)):
    return suggestion_dict(edit_title(session, suggestion_id, body.title, now=clock(), env=env))


@router.post("/{suggestion_id}/approve", response_model=SuggestionOut)
def post_approve(body: ApproveIn, suggestion_id: int = Path(ge=1), session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), env: Env = Depends(get_env), _=Depends(require_csrf)):
    return suggestion_dict(approve(session, suggestion_id, body.approver, now=clock(), env=env))


@router.post("/{suggestion_id}/reject", response_model=SuggestionOut)
def post_reject(suggestion_id: int = Path(ge=1), session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), _=Depends(require_csrf)):
    return suggestion_dict(reject(session, suggestion_id, now=clock()))
