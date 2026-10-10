"""작업(jobs) 핸들러 등록: videos.sync, suggestions.generate, batch.execute. 모듈을 임포트하면 등록된다.

핸들러는 워커가 부르며 (session_factory, job)을 받는다. 정책·사전은 환경변수에서 만든 기본 Env 를 쓴다(common.default_env).
"""
from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from ytweb.ai.factory import get_suggester
from ytweb.core import audit, jobs
from ytweb.core.clock import utcnow
from ytweb.core.errors import ProblemError
from ytweb.core.settings_store import DEFAULT_SUGGESTIONS_PER_VIDEO, get_web_setting
from ytweb.db.models import Job
from ytweb.domain.batches import run_due_items
from ytweb.domain.common import default_env
from ytweb.domain.seed import seed_demo
from ytweb.domain.suggestions import generate_for_video

DEFAULT_TONE = "friendly"


def _progress(factory: sessionmaker, job_id: str, n: int, total: int | None = None) -> None:
    with factory() as s:
        jobs.update_progress(s, job_id, progress=n, total=total)
        s.commit()


def handle_videos_sync(factory: sessionmaker, job: Job) -> dict:
    env, now = default_env(), utcnow()
    with factory() as s:
        result = seed_demo(s, now, env.policy)
        audit.record(s, actor="worker", action="videos.sync", target_type="job", target_id=job.id, detail={"created": result.created, "updated": result.updated, "total": result.total}, now=now)
        s.commit()
    _progress(factory, job.id, result.total, result.total)
    return {"created": result.created, "updated": result.updated, "snapshots_created": result.snapshots_created, "total": result.total}


def handle_suggestions_generate(factory: sessionmaker, job: Job) -> dict:
    env = default_env()
    video_ids = list(job.payload.get("video_ids") or [])
    with factory() as s:
        count = job.payload.get("count") or get_web_setting(s, "suggestions_per_video", DEFAULT_SUGGESTIONS_PER_VIDEO)
        tone_setting = get_web_setting(s, "tone", [])
    tone = ", ".join(tone_setting) if isinstance(tone_setting, list) and tone_setting else DEFAULT_TONE  # 설정 화면의 tone 은 문자열 목록
    suggester = get_suggester("demo")
    created = 0
    skipped: list[dict] = []
    for idx, video_id in enumerate(video_ids, 1):
        with factory() as s:
            try:
                created += len(generate_for_video(s, video_id, count=count, tone=tone, now=utcnow(), env=env, suggester=suggester, actor="worker"))
                s.commit()
            except ProblemError as exc:  # 한 영상의 실패가 나머지를 막지 않는다
                s.rollback()
                skipped.append({"video_id": video_id, "code": exc.code})
        _progress(factory, job.id, idx)
    return {"videos": len(video_ids), "suggestions": created, "skipped": skipped}


def handle_batch_execute(factory: sessionmaker, job: Job) -> dict:
    result = run_due_items(factory, utcnow(), default_env(), batch_id=int(job.payload["batch_id"]), job_id=job.id, on_progress=lambda n: _progress(factory, job.id, n))
    return {"processed": result.processed, "success": result.success, "failed": result.failed, "skipped": result.skipped, "stopped_by": result.stopped_by,
            "note": "남은 예약 항목은 워커가 예정일에 맞춰 하루 상한 안에서 자동 처리합니다."}


jobs.register_handler("videos.sync", handle_videos_sync)
jobs.register_handler("suggestions.generate", handle_suggestions_generate)
jobs.register_handler("batch.execute", handle_batch_execute)
