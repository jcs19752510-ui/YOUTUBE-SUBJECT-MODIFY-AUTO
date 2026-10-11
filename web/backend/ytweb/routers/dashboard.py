from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ytweb.core.deps import get_clock, get_session, require_session
from ytweb.domain.common import Env
from ytweb.domain.dashboard import build_dashboard
from ytweb.domain.deps import get_env
from ytweb.domain.schemas import DashboardOut

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def get_dashboard(session: Session = Depends(get_session), clock: Callable[[], datetime] = Depends(get_clock), env: Env = Depends(get_env), _=Depends(require_session)):
    return build_dashboard(session, clock(), env)
