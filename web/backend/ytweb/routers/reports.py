from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ytweb.core.deps import get_session, require_session
from ytweb.domain.common import VIDEO_ID_PATTERN, Env
from ytweb.domain.deps import get_env
from ytweb.domain.reports import build_reports, export_csv
from ytweb.domain.schemas import ReportsOut

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/changes", response_model=ReportsOut)
def report_changes(video_id: str | None = Query(default=None, pattern=VIDEO_ID_PATTERN), session: Session = Depends(get_session), env: Env = Depends(get_env), _=Depends(require_session)):
    return build_reports(session, env, video_id)


@router.get("/export.csv")
def report_csv(video_id: str | None = Query(default=None, pattern=VIDEO_ID_PATTERN), session: Session = Depends(get_session), env: Env = Depends(get_env), _=Depends(require_session)):
    return Response(export_csv(session, env, video_id).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="youtube-title-report.csv"', "Cache-Control": "no-store"})
