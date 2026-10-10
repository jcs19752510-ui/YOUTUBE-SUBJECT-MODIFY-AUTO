"""홈 요약(WEB_DESIGN §3 /dashboard)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ytweb.core.clock import kst_today
from ytweb.core.settings_store import effective_daily_cap
from ytweb.db.models import Batch, BatchItem, Job, Video
from ytweb.domain.common import Env
from ytweb.domain.limits_quota import applied_today, quota_state
from ytweb.domain.serialize import job_dict
from ytweb.domain.suggestions import expire_stale_approvals
from ytweb.domain.videos import workflow_maps

GOOGLE_STATUS = {"mode": "demo", "connected": False, "message": "데모 모드입니다. 구글(유튜브)에 연결되어 있지 않고, 아래 영상은 모두 시연용 가상 데이터입니다."}


def build_dashboard(session: Session, now: datetime, env: Env) -> dict:
    expire_stale_approvals(session, now)
    status_map, _, _ = workflow_maps(session)
    videos = session.execute(select(Video.exclusion_reasons)).scalars().all()
    tally = {k: 0 for k in ("suggested", "approved", "queued", "applied")}
    for st in status_map.values():
        if st in tally:
            tally[st] += 1
    qs = quota_state(session, now, env.policy)
    today = kst_today(now)
    job = session.execute(select(Job).where(Job.status.in_(("queued", "running"))).order_by(Job.created_at.desc()).limit(1)).scalar_one_or_none()
    pending = session.execute(
        select(func.count(), func.min(BatchItem.scheduled_date)).select_from(BatchItem).join(Batch, Batch.id == BatchItem.batch_id)
        .where(BatchItem.status == "pending", Batch.status.in_(("queued", "running")))
    ).one()
    next_run = max(pending[1], today) if pending[1] is not None else None
    return {
        "mode": "demo",
        "live_enabled": False,
        "google": {"mode": GOOGLE_STATUS["mode"], "connected": GOOGLE_STATUS["connected"]},
        "counts": {"videos": len(videos), "excluded": sum(1 for r in videos if r), **tally},
        "today": {"applied": applied_today(session, now), "cap": effective_daily_cap(session, env.policy)},
        "quota": {"used": qs.used, "limit": qs.limit, "remaining": qs.remaining, "pt_date": qs.pt_date},
        "active_job": job_dict(job) if job else None,
        "queue": {"pending_items": int(pending[0]), "next_run_date": next_run},
    }
