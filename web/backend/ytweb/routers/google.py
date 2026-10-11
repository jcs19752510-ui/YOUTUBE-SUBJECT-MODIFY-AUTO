from __future__ import annotations

from fastapi import APIRouter, Depends

from ytweb.core.deps import require_session
from ytweb.domain.dashboard import GOOGLE_STATUS
from ytweb.domain.schemas import GoogleStatusOut

router = APIRouter(prefix="/api/v1/google", tags=["google"])


@router.get("/status", response_model=GoogleStatusOut)
def google_status(_=Depends(require_session)):
    return GOOGLE_STATUS
