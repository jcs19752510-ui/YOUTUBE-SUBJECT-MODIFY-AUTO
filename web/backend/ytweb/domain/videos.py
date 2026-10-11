"""영상 목록(서버측 검색·필터·정렬·페이지네이션)과 상세, workflow_status 계산."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ytweb.core.errors import ProblemError
from ytweb.core.settings_store import effective_daily_cap
from ytweb.db.models import Change, Suggestion, Video
from ytweb.domain.common import Env, clamp_page
from ytweb.domain.changes import rollbackable_map
from ytweb.domain.limits_quota import check_video_limits, summarize_limits
from ytweb.domain.serialize import change_dict, suggestion_dict
from ytweb.domain.suggestions import expire_stale_approvals

SORT_FIELDS = ("title", "views", "duration_sec", "last_change_at", "video_id", "suggestion_count", "workflow_status")
WORKFLOW_STATUSES = ("none", "suggested", "approved", "queued", "applied", "rolled_back")
_WORKFLOW_ORDER = {s: i for i, s in enumerate(WORKFLOW_STATUSES)}


def workflow_maps(session: Session) -> tuple[dict[str, str], dict[str, int], dict[str, datetime]]:
    """영상별 (workflow_status, 제안 수, 마지막 성공 변경 시각). 우선순위: queued > approved > 마지막 변경(applied/rolled_back) > suggested > none."""
    by_video: dict[str, dict[str, int]] = defaultdict(dict)
    for vid, status, n in session.execute(select(Suggestion.video_id, Suggestion.status, func.count()).group_by(Suggestion.video_id, Suggestion.status)):
        by_video[vid][status] = n
    last: dict[str, tuple[datetime, int, str]] = {}
    for vid, ctype, ts, cid in session.execute(select(Change.video_id, Change.change_type, func.coalesce(Change.applied_at, Change.created_at), Change.id).where(Change.result == "success")):
        key = (ts, cid, ctype)
        if vid not in last or key[:2] > last[vid][:2]:
            last[vid] = key
    status_map: dict[str, str] = {}
    counts: dict[str, int] = {}
    for vid in set(by_video) | set(last):
        sc = by_video.get(vid, {})
        counts[vid] = sum(sc.values())
        if sc.get("queued"):
            st = "queued"
        elif sc.get("approved"):
            st = "approved"
        elif vid in last:
            st = "applied" if last[vid][2] == "apply" else "rolled_back"
        elif any(sc.get(k) for k in ("candidate", "blocked", "expired")):
            st = "suggested"
        else:
            st = "none"
        status_map[vid] = st
    return status_map, counts, {v: t[0] for v, t in last.items()}


def _summary(v, status: str, count: int, last_change: datetime | None) -> dict:
    reasons = list(v.exclusion_reasons or [])
    return {
        "video_id": v.video_id, "title": v.title, "privacy_status": v.privacy_status, "duration_sec": v.duration_sec, "is_short": v.is_short,
        "excluded": bool(reasons), "exclusion_reasons": reasons, "workflow_status": status, "suggestion_count": count, "last_change_at": last_change, "views": v.views,
    }


def list_videos(session: Session, *, now: datetime, q: str | None, status: str | None, excluded: bool | None, sort: str, order: str, page: int, page_size: int) -> tuple[list[dict], int]:
    expire_stale_approvals(session, now)
    page, page_size = clamp_page(page, page_size)
    status_map, counts, last_map = workflow_maps(session)
    cols = (Video.video_id, Video.title, Video.privacy_status, Video.duration_sec, Video.is_short, Video.exclusion_reasons, Video.views)
    needle = q.strip().casefold() if q else ""
    rows = []
    for row in session.execute(select(*cols)):
        reasons = list(row.exclusion_reasons or [])
        wf = status_map.get(row.video_id, "none")
        if needle and needle not in row.title.casefold() and needle not in row.video_id.casefold():
            continue
        if status and wf != status:
            continue
        if excluded is not None and bool(reasons) != excluded:
            continue
        rows.append(_summary(row, wf, counts.get(row.video_id, 0), last_map.get(row.video_id)))
    key = {"workflow_status": lambda r: _WORKFLOW_ORDER[r["workflow_status"]]}.get(sort, lambda r: r[sort])
    present = sorted((r for r in rows if key(r) is not None), key=key, reverse=(order == "desc"))
    ordered = present + [r for r in rows if key(r) is None]  # 값이 없는 행은 정렬 방향과 무관하게 맨 뒤
    start = (page - 1) * page_size
    return ordered[start:start + page_size], len(ordered)


def video_detail(session: Session, video_id: str, *, now: datetime, env: Env) -> dict:
    expire_stale_approvals(session, now)
    video = session.get(Video, video_id)
    if video is None:
        raise ProblemError(404, "video_not_found", "영상을 찾을 수 없습니다.", hint="영상 목록을 새로고침하세요.")
    status_map, counts, last_map = workflow_maps(session)
    out = _summary(video, status_map.get(video_id, "none"), counts.get(video_id, 0), last_map.get(video_id))
    sugs = session.execute(select(Suggestion).where(Suggestion.video_id == video_id).order_by(Suggestion.id.desc())).scalars().all()
    changes = session.execute(select(Change).where(Change.video_id == video_id).order_by(Change.id.desc())).scalars().all()
    rb = rollbackable_map(session, list(changes))
    cap = effective_daily_cap(session, env.policy)
    snippet = video.snippet if isinstance(video.snippet, dict) else {}
    out.update({
        "description_excerpt": video.description_excerpt,
        "suggestions": [suggestion_dict(s) for s in sugs],
        "changes": [change_dict(c, video.title, rb[c.id]) for c in changes],
        "limits": summarize_limits(check_video_limits(session, video_id, now, env.limits_policy, cap)),
        "preserved": {
            "category_id": snippet.get("categoryId"), "tags": snippet.get("tags") or [], "default_language": snippet.get("defaultLanguage"),
            "default_audio_language": snippet.get("defaultAudioLanguage"), "description_chars": len(snippet.get("description") or ""),
        },
    })
    return out
