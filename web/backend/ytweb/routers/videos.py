from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ytweb.ai.base import TitleSuggester
from ytweb.core import audit, jobs
from ytweb.core.deps import get_clock, get_session, require_csrf, require_session
from ytweb.core.settings_store import DEFAULT_SUGGESTIONS_PER_VIDEO, get_web_setting
from ytweb.db.models import Job
from ytweb.domain.common import VIDEO_ID_PATTERN, Env
from ytweb.domain.deps import get_env, get_title_suggester
from ytweb.domain.handlers import DEFAULT_TONE
from ytweb.domain.schemas import MAX_PAGE, JobOut, Page, SuggestionCreateIn, SuggestionOut, VideoDetailOut, VideoSummaryOut
from ytweb.domain.serialize import job_dict, suggestion_dict
from ytweb.domain.suggestions import generate_for_video
from ytweb.domain.videos import list_videos, video_detail

router = APIRouter(prefix="/api/v1/videos", tags=["videos"])

SortField = Literal["title", "views", "duration_sec", "last_change_at", "video_id", "suggestion_count", "workflow_status"]


@router.get("", response_model=Page[VideoSummaryOut])
def get_videos(
    q: str | None = Query(default=None, max_length=100),
    status: Literal["none", "suggested", "approved", "queued", "applied", "rolled_back"] | None = None,
    excluded: bool | None = None, sort: SortField = "video_id", order: Literal["asc", "desc"] = "asc",
    page: int = Query(1, ge=1, le=MAX_PAGE), page_size: int = Query(50, ge=1, le=200),
    date_from: date | None = None, date_to: date | None = None, kind: Literal["long", "short"] | None = None,
    session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), _=Depends(require_session),
):
    items, total = list_videos(session, now=clock(), q=q, status=status, excluded=excluded, sort=sort, order=order, page=page, page_size=page_size, date_from=date_from, date_to=date_to, kind=kind)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/sync", status_code=202, response_model=JobOut)
def post_sync(session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), _=Depends(require_csrf)):
    active = session.execute(select(Job).where(Job.type == "videos.sync", Job.status.in_(("queued", "running"))).order_by(Job.created_at.desc()).limit(1)).scalar_one_or_none()
    if active is not None:  # 이미 진행 중이면 같은 작업을 돌려준다(연타 방지)
        return job_dict(active)
    now = clock()
    job = jobs.enqueue(session, type="videos.sync", payload={}, total=200, now=now)
    audit.record(session, actor="web", action="videos.sync_request", target_type="job", target_id=job.id, now=now)
    return job_dict(job)


@router.get("/{video_id}", response_model=VideoDetailOut)
def get_video(video_id: str = Path(pattern=VIDEO_ID_PATTERN), session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), env: Env = Depends(get_env), _=Depends(require_session)):
    return video_detail(session, video_id, now=clock(), env=env)


@router.post("/{video_id}/suggestions", status_code=201, response_model=list[SuggestionOut])
def post_suggestions(
    body: SuggestionCreateIn | None = None, video_id: str = Path(pattern=VIDEO_ID_PATTERN),
    session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), env: Env = Depends(get_env),
    suggester: TitleSuggester = Depends(get_title_suggester), _=Depends(require_csrf),
):
    count = (body.count if body else None) or get_web_setting(session, "suggestions_per_video", DEFAULT_SUGGESTIONS_PER_VIDEO)
    tone_setting = get_web_setting(session, "tone", [])
    tone = ", ".join(tone_setting) if isinstance(tone_setting, list) and tone_setting else DEFAULT_TONE
    rows = generate_for_video(session, video_id, count=count, tone=tone, now=clock(), env=env, suggester=suggester)
    return [suggestion_dict(s) for s in rows]
