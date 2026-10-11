"""워커 프로세스: due 작업 처리 + 배치 항목 스케줄러 틱. SIGTERM/SIGINT 에서는 현재 작업을 마치고 종료한다."""
from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import signal
import socket
import sys
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from ytweb.config import load_web_settings
from ytweb.core import jobs
from ytweb.core.clock import utcnow
from ytweb.core.logsetup import setup_logging
from ytweb.core.sessions import purge_expired
from ytweb.db.models import IdempotencyKey
from ytweb.db.session import make_engine, make_session_factory

log = logging.getLogger("ytweb.worker")

POLL_SECONDS = 2.0
MAINTENANCE_EVERY = timedelta(minutes=10)
REAP_EVERY = timedelta(minutes=1)    # 작업 유형별 stale 기준(배치 5분)을 정비 주기(10분)보다 촘촘히 확인한다
IDEMPOTENCY_RETENTION = timedelta(hours=48)


def load_domain_handlers() -> Callable[[sessionmaker, datetime], object] | None:
    """ytweb.domain 하위 모듈을 임포트해 작업 처리기를 등록시키고, 배치 스케줄러 함수를 찾아 돌려준다(없으면 None)."""
    try:
        pkg = importlib.import_module("ytweb.domain")
    except ModuleNotFoundError:
        log.warning("ytweb.domain 이 없어 작업 처리기와 배치 스케줄러 없이 동작합니다.")
        return None
    for mod in pkgutil.iter_modules(pkg.__path__):
        try:
            importlib.import_module(f"ytweb.domain.{mod.name}")
        except Exception:
            log.error("도메인 모듈 로드 실패: %s", mod.name, exc_info=True)
    batches = sys.modules.get("ytweb.domain.batches")
    return getattr(batches, "run_due_items", None) if batches else None


class Worker:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        clock: Callable[[], datetime] = utcnow,
        worker_id: str | None = None,
        run_due_items: Callable[[sessionmaker, datetime], object] | None = None,
        poll_seconds: float = POLL_SECONDS,
        startup_recover: Callable[..., object] | None = None,
        session_idle_timeout: timedelta | None = None,
    ) -> None:
        self.factory = factory
        self.clock = clock
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.run_due_items = run_due_items
        self.poll_seconds = poll_seconds
        self.startup_recover = startup_recover
        self.session_idle_timeout = session_idle_timeout
        self.stop_event = threading.Event()
        self._last_maintenance: datetime | None = None
        self._last_reap: datetime | None = None

    def request_stop(self, *_: object) -> None:
        self.stop_event.set()

    def maintenance(self) -> None:
        now = self.clock()
        if self._last_maintenance and now - self._last_maintenance < MAINTENANCE_EVERY:
            return
        self._last_maintenance = now
        with self.factory() as s:
            requeued, failed = jobs.requeue_stale(s, now=now)
            purge_expired(s, now=now, idle_timeout=self.session_idle_timeout)
            s.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < now - IDEMPOTENCY_RETENTION))
            s.commit()
        if requeued or failed:
            log.warning("stale 작업 정리", extra={"requeued": requeued, "failed": failed})

    def reap_stale_jobs(self, *, force: bool = False, stale_after: timedelta | None = None) -> tuple[int, int]:
        """생존 신호가 끊긴 running 작업을 재큐/실패 처리한다(DEF-7B-001). force 가 아니면 REAP_EVERY 간격으로만 실행한다."""
        now = self.clock()
        if not force and self._last_reap and now - self._last_reap < REAP_EVERY:
            return 0, 0
        self._last_reap = now
        with self.factory() as s:
            requeued, failed = jobs.requeue_stale(s, now=now, stale_after=stale_after)
            s.commit()
        if requeued or failed:
            log.warning("stale 작업 정리", extra={"requeued": requeued, "failed": failed})
        return requeued, failed

    def tick(self) -> int:
        """한 번의 순회. 처리한 작업 수를 돌려준다. 중지 요청이 오면 현재 작업만 마치고 멈춘다."""
        self.maintenance()
        try:
            self.reap_stale_jobs()
        except Exception:
            log.error("stale 작업 정리 실패", exc_info=True)
        done = 0
        while not self.stop_event.is_set():
            if not jobs.process_next(self.factory, worker_id=self.worker_id, clock=self.clock):
                break
            done += 1
        if self.run_due_items and not self.stop_event.is_set():
            try:
                self.run_due_items(self.factory, self.clock())
            except Exception:
                log.error("배치 스케줄러 틱 실패", exc_info=True)
        return done

    def run(self) -> None:
        log.info("worker start", extra={"worker_id": self.worker_id})
        if self.startup_recover:
            # 워커는 compose 에서 1개만 뜬다(전제). 비정상 종료로 running 에 남은 배치 항목을 기동 직후 즉시 재조회로 확정한다.
            try:
                fixed = self.startup_recover(self.factory, self.clock(), stale_after=timedelta(0))
                log.info("기동 시 running 항목 정리", extra={"fixed": fixed})
            except Exception:
                log.error("기동 시 running 항목 정리 실패", exc_info=True)
        # 같은 전제(워커 1개)로, 기동 직후 running 으로 남은 작업은 전부 이전 워커가 죽으며 남긴 것이다 → 기다리지 않고 바로 재큐(시도 3회 초과면 실패 처리).
        # 항목 정리 뒤에 하므로 재큐된 batch.execute 는 이미 정리된 항목 위에서 남은 예약만 이어서 처리한다.
        try:
            self.reap_stale_jobs(force=True, stale_after=timedelta(0))
        except Exception:
            log.error("기동 시 running 작업 정리 실패", exc_info=True)
        while not self.stop_event.is_set():
            self.tick()
            self.stop_event.wait(self.poll_seconds)
        log.info("worker stopped", extra={"worker_id": self.worker_id})


def main() -> None:
    settings = load_web_settings()
    setup_logging(json_format=settings.log_json)
    engine = make_engine(settings.database_url)
    run_due = load_domain_handlers()
    batches = sys.modules.get("ytweb.domain.batches")
    worker = Worker(
        make_session_factory(engine),
        run_due_items=run_due,
        startup_recover=getattr(batches, "recover_running_items", None) if batches else None,
        session_idle_timeout=settings.session_idle_timeout,
    )
    signal.signal(signal.SIGTERM, worker.request_stop)
    signal.signal(signal.SIGINT, worker.request_stop)
    try:
        worker.run()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
