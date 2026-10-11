"""내 채널 영상 목록 가져오기(M2 단위 3). 읽기 전용: 유튜브에서 읽은 값을 videos 테이블에 저장만 한다(source='youtube').

데모 영상(source='demo')과 섞이지 않게, 불러오기 전에 **기록이 전혀 없는** 데모 영상만 지운다. 데모 영상에 제안·배치·변경 기록이 있으면
데이터를 잃지 않도록 불러오기를 거부하고 초기화 방법(reset-demo.ps1)을 안내한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from youtube_title.config import Settings

from ytweb.core.errors import ProblemError
from ytweb.db.models import BatchItem, Change, MetricsSnapshot, Suggestion, Video
from ytweb.domain.exclusions import exclusion_reasons
from ytweb.youtube import google_oauth as oauth
from ytweb.youtube.live_read import GoogleAccess, YouTubeReader


@dataclass(frozen=True)
class LiveSyncResult:
    created: int
    updated: int
    total: int
    demo_removed: int


def google_access_from_env(secrets_dir: Path) -> GoogleAccess:
    client = Path(os.environ.get("YTWEB_GOOGLE_CLIENT_FILE", "/run/secrets/google_client"))
    return GoogleAccess(client, oauth.TokenStore(secrets_dir / "google_token.json"))


def purge_pristine_demo(session: Session) -> int:
    demo_ids = set(session.execute(select(Video.video_id).where(Video.source == "demo")).scalars())
    if not demo_ids:
        return 0
    used = set()
    for col in (Suggestion.video_id, BatchItem.video_id, Change.video_id):
        used |= set(session.execute(select(col).where(col.in_(demo_ids)).distinct()).scalars())
    if used:
        raise ProblemError(409, "demo_data_in_use", "데모 기록이 있어 불러올 수 없습니다",
                           "데모 영상에 제안·배치·변경 기록이 있어 실제 영상과 섞이지 않게 막았습니다.",
                           hint="PowerShell 에서 .\\web\\scripts\\reset-demo.ps1 로 데모 데이터를 초기화한 뒤 다시 불러오세요.")
    session.execute(delete(MetricsSnapshot).where(MetricsSnapshot.video_id.in_(demo_ids)))
    session.execute(delete(Video).where(Video.video_id.in_(demo_ids)))
    session.flush()
    return len(demo_ids)


def sync_live(session: Session, reader: YouTubeReader, now: datetime, policy: Settings) -> LiveSyncResult:
    removed = purge_pristine_demo(session)
    rows = reader.fetch_all()
    existing = {v.video_id: v for v in session.execute(select(Video).where(Video.video_id.in_([r["video_id"] for r in rows]))).scalars()}
    touched = set(session.execute(select(Change.video_id).where(Change.video_id.in_(list(existing) or [""])).distinct()).scalars())
    created = updated = 0
    for r in rows:
        v = existing.get(r["video_id"])
        if v is None:
            v = Video(**r, is_short=False, exclusion_reasons=[], fetched_at=now)
            session.add(v)
            created += 1
        else:
            v.fetched_at, v.views = now, r["views"]
            if v.video_id not in touched:  # 이 프로그램이 바꾼 적이 있는 영상은 보존된 값(롤백 기준)을 건드리지 않는다
                for k, val in r.items():
                    setattr(v, k, val)
            updated += 1
        v.is_short = (v.duration_sec is not None) and v.duration_sec <= policy.shorts_max_seconds
        v.exclusion_reasons = exclusion_reasons(v, policy)
    session.flush()
    return LiveSyncResult(created, updated, len(rows), removed)
