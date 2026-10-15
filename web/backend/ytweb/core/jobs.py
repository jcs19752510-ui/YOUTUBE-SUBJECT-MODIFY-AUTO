"""PostgreSQL 작업 큐(WEB_DESIGN §4-4, §10).

claim 은 PostgreSQL 에서 `SELECT ... FOR UPDATE SKIP LOCKED`, SQLite(단일 프로세스 개발·테스트)에서는
조건부 UPDATE(compare-and-set)로 같은 의미를 낸다.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from ytweb.core.clock import utcnow
from ytweb.core.errors import ProblemError
from ytweb.db.models import Job

log = logging.getLogger("ytweb.jobs")

MAX_ATTEMPTS = 3
STALE_AFTER = timedelta(minutes=10)
# 항목 단위 compare-and-set·planned 고유 인덱스로 중복 실행이 안전하고 항목마다 생존 신호(update_progress)를 남기는 작업은 더 짧게 본다(DEF-7B-001).
STALE_AFTER_BY_TYPE: dict[str, timedelta] = {"batch.execute": timedelta(minutes=5)}
_ERROR_MAX = 300

Handler = Callable[[sessionmaker, Job], "dict | None"]
_HANDLERS: dict[str, Handler] = {}


def register_handler(type: str, fn: Handler) -> None:
    _HANDLERS[type] = fn


def get_handler(type: str) -> Handler | None:
    return _HANDLERS.get(type)


def enqueue(session: Session, *, type: str, payload: dict, total: int = 0, now: datetime) -> Job:
    job = Job(type=type, status="queued", payload=payload, total=total, progress=0, attempts=0, run_after=now, created_at=now)
    session.add(job)
    session.flush()
    return job


def update_progress(session: Session, job_id: str, *, progress: int, total: int | None = None) -> None:
    values: dict = {"progress": progress}
    if total is not None:
        values["total"] = total
    session.execute(update(Job).where(Job.id == job_id).values(**values))
    # 진행 보고는 생존 신호도 겸한다(오래 걸리는 작업이 stale 로 오인되어 재큐되지 않게).
    session.execute(update(Job).where(Job.id == job_id, Job.status == "running").values(locked_at=utcnow()))
    session.flush()


def claim(session: Session, *, worker_id: str, now: datetime) -> Job | None:
    stmt = (
        select(Job)
        .where(Job.status == "queued", Job.run_after <= now)
        .order_by(Job.run_after, Job.created_at)
        .limit(1)
    )
    if session.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    job = session.execute(stmt).scalar_one_or_none()
    if job is None:
        return None
    res = session.execute(
        update(Job)
        .where(Job.id == job.id, Job.status == "queued")
        .values(status="running", locked_by=worker_id, locked_at=now, attempts=Job.attempts + 1)
    )
    if res.rowcount != 1:  # SQLite 에서 다른 처리자가 먼저 가져간 경우
        return None
    session.flush()
    session.refresh(job)
    return job


def complete(session: Session, job_id: str, *, result: dict | None, now: datetime) -> None:
    session.execute(
        update(Job).where(Job.id == job_id, Job.status == "running")
        .values(status="succeeded", result=result, finished_at=now, locked_by=None, locked_at=None, error=None)
    )
    session.flush()


def fail(session: Session, job_id: str, *, error: str, now: datetime) -> None:
    session.execute(
        update(Job).where(Job.id == job_id, Job.status == "running")
        .values(status="failed", error=error[:_ERROR_MAX], finished_at=now, locked_by=None, locked_at=None)
    )
    session.flush()


def requeue_stale(session: Session, *, now: datetime, stale_after: timedelta | None = None) -> tuple[int, int]:
    """비정상 종료로 running 에 남은 작업을 재큐(시도 횟수 초과면 failed). (재큐 수, 실패 처리 수) 반환.

    stale_after=None 이면 작업 유형별 기본값(STALE_AFTER_BY_TYPE, 없으면 STALE_AFTER)을 쓴다. 0 을 주면 running 인 작업을 전부 고아로 본다 —
    워커가 하나뿐인 기동 직후에만 쓴다. locked_at 이 비어 있는 running 작업은 생존 신호가 없으므로 항상 고아다.
    다른 처리자가 같은 행을 잡고 있으면(PostgreSQL SKIP LOCKED) 건너뛰어 같은 작업을 두 번 재큐하지 않는다."""
    def limit(job_type: str) -> timedelta:
        return stale_after if stale_after is not None else STALE_AFTER_BY_TYPE.get(job_type, STALE_AFTER)

    shortest = stale_after if stale_after is not None else min([STALE_AFTER, *STALE_AFTER_BY_TYPE.values()])
    stmt = select(Job).where(Job.status == "running", or_(Job.locked_at.is_(None), Job.locked_at < now - shortest))
    if session.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    requeued = failed = 0
    for job in session.execute(stmt).scalars().all():
        if job.locked_at is not None and job.locked_at >= now - limit(job.type):
            continue
        if job.attempts >= MAX_ATTEMPTS:
            job.status, job.error, job.finished_at = "failed", "worker_lost", now
            failed += 1
        else:
            job.status = "queued"
            requeued += 1
        job.locked_by = None
        job.locked_at = None
    session.flush()
    return requeued, failed


def _safe_error(exc: BaseException) -> str:
    if isinstance(exc, ProblemError):
        return f"{exc.code}: {exc.title}"
    return f"internal_error: {type(exc).__name__}"


def process_next(factory: sessionmaker, *, worker_id: str, clock: Callable[[], datetime]) -> bool:
    """due 작업 1건을 처리한다. 처리했으면 True. 핸들러 예외는 작업 실패로 기록하고 삼키지 않고 로그에 남긴다."""
    with factory() as s:
        job = claim(s, worker_id=worker_id, now=clock())
        s.commit()
    if job is None:
        return False
    handler = get_handler(job.type)
    try:
        if handler is None:
            raise ProblemError(500, "no_handler", f"처리기가 없는 작업 유형: {job.type}", hint="앱을 최신 버전으로 업데이트한 뒤 다시 시도하세요.")
        result = handler(factory, job)
    except Exception as exc:
        log.error("job failed id=%s type=%s", job.id, job.type, exc_info=True)
        with factory() as s:
            fail(s, job.id, error=_safe_error(exc), now=clock())
            s.commit()
    else:
        with factory() as s:
            complete(s, job.id, result=result, now=clock())
            s.commit()
    return True
