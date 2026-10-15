from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from ytweb.core.deps import get_session, require_session
from ytweb.core.errors import ProblemError
from ytweb.db.models import Job
from ytweb.domain.schemas import JobOut
from ytweb.domain.serialize import job_dict

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str = Path(pattern=r"^[0-9a-fA-F-]{36}$"), session: Session = Depends(get_session), _=Depends(require_session)):
    job = session.get(Job, job_id)
    if job is None:
        raise ProblemError(404, "job_not_found", "작업을 찾을 수 없습니다.", hint="작업 번호를 확인하세요.")
    return job_dict(job)
