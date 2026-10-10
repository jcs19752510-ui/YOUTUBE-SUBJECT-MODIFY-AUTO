"""잡 큐 · 워커."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from tests.conftest import FakeClock
from ytweb.core import jobs
from ytweb.core.errors import ProblemError
from ytweb.db.models import IdempotencyKey, Job, SessionRow
from ytweb.worker import Worker, load_domain_handlers

T0 = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clean_handlers():
    saved = dict(jobs._HANDLERS)
    jobs._HANDLERS.clear()
    yield
    jobs._HANDLERS.clear()
    jobs._HANDLERS.update(saved)


def test_enqueue_creates_queued_job(db):
    """TC-WA-098 enqueue 는 queued 상태·payload·total·run_after=now 인 작업을 만든다."""
    j = jobs.enqueue(db, type="videos.sync", payload={"a": 1}, total=5, now=T0)
    assert len(j.id) == 36 and j.status == "queued" and j.payload == {"a": 1}
    assert j.total == 5 and j.progress == 0 and j.attempts == 0 and j.run_after == T0


def test_claim_marks_running_once(db):
    """TC-WA-099 claim 은 running/locked_by/attempts=1 로 바꾸고, 같은 작업을 두 번 주지 않는다."""
    j = jobs.enqueue(db, type="t", payload={}, now=T0)
    got = jobs.claim(db, worker_id="w1", now=T0)
    assert got.id == j.id and got.status == "running" and got.locked_by == "w1" and got.attempts == 1 and got.locked_at == T0
    assert jobs.claim(db, worker_id="w2", now=T0) is None


def test_claim_respects_run_after_and_fifo(db):
    """TC-WA-100 run_after 이전 작업은 건너뛰고, due 작업은 오래된 순서로 가져간다."""
    later = jobs.enqueue(db, type="t", payload={"n": "later"}, now=T0 + timedelta(hours=1))
    first = jobs.enqueue(db, type="t", payload={"n": 1}, now=T0)
    second = jobs.enqueue(db, type="t", payload={"n": 2}, now=T0 + timedelta(seconds=1))
    assert jobs.claim(db, worker_id="w", now=T0 + timedelta(seconds=5)).id == first.id
    assert jobs.claim(db, worker_id="w", now=T0 + timedelta(seconds=5)).id == second.id
    assert jobs.claim(db, worker_id="w", now=T0 + timedelta(seconds=5)) is None
    assert jobs.claim(db, worker_id="w", now=T0 + timedelta(hours=2)).id == later.id


def test_process_next_success_records_result(factory):
    """TC-WA-101 핸들러 반환값이 result 로 저장되고 succeeded/finished_at 이 기록된다."""
    jobs.register_handler("t", lambda f, job: {"ok": job.payload["x"]})
    with factory() as s:
        j = jobs.enqueue(s, type="t", payload={"x": 7}, now=T0)
        s.commit()
        jid = j.id
    assert jobs.process_next(factory, worker_id="w", clock=FakeClock()) is True
    with factory() as s:
        row = s.get(Job, jid)
        assert row.status == "succeeded" and row.result == {"ok": 7} and row.finished_at is not None
        assert row.locked_by is None and row.error is None
    assert jobs.process_next(factory, worker_id="w", clock=FakeClock()) is False


def test_process_next_failure_recorded_without_trace(factory, caplog):
    """TC-WA-102 핸들러 예외는 작업을 failed 로 만들고, 저장되는 error 에는 예외 메시지·경로가 없다."""
    def boom(f, job):
        raise RuntimeError("secret /home/user/x.py")

    jobs.register_handler("t", boom)
    with factory() as s:
        jid = jobs.enqueue(s, type="t", payload={}, now=T0).id
        s.commit()
    assert jobs.process_next(factory, worker_id="w", clock=FakeClock()) is True
    with factory() as s:
        row = s.get(Job, jid)
        assert row.status == "failed" and row.error == "internal_error: RuntimeError"
        assert "secret" not in row.error and "/home" not in row.error


def test_process_next_problem_error_uses_code(factory):
    """TC-WA-103 ProblemError 로 실패하면 error 에 code 와 제목이 남는다."""
    def boom(f, job):
        raise ProblemError(409, "limit_reached", "한도 도달")

    jobs.register_handler("t", boom)
    with factory() as s:
        jid = jobs.enqueue(s, type="t", payload={}, now=T0).id
        s.commit()
    jobs.process_next(factory, worker_id="w", clock=FakeClock())
    with factory() as s:
        assert s.get(Job, jid).error == "limit_reached: 한도 도달"


def test_process_next_without_handler_fails(factory):
    """TC-WA-104 처리기가 없는 작업 유형은 failed(no_handler)."""
    with factory() as s:
        jid = jobs.enqueue(s, type="unknown.type", payload={}, now=T0).id
        s.commit()
    jobs.process_next(factory, worker_id="w", clock=FakeClock())
    with factory() as s:
        row = s.get(Job, jid)
        assert row.status == "failed" and row.error.startswith("no_handler")


def test_requeue_stale_running_job(db):
    """TC-WA-105 임계 시간 넘게 running 인 작업은 queued 로 재큐되고 잠금이 풀린다. 최근 작업은 그대로."""
    old = jobs.enqueue(db, type="t", payload={}, now=T0)
    fresh = jobs.enqueue(db, type="t", payload={}, now=T0)
    jobs.claim(db, worker_id="w1", now=T0)
    jobs.claim(db, worker_id="w1", now=T0 + timedelta(minutes=9))
    db.commit()
    assert jobs.requeue_stale(db, now=T0 + timedelta(minutes=11)) == (1, 0)
    db.commit()
    db.expire_all()
    assert db.get(Job, old.id).status == "queued" and db.get(Job, old.id).locked_by is None
    assert db.get(Job, fresh.id).status == "running"
    assert jobs.claim(db, worker_id="w2", now=T0 + timedelta(minutes=11)).id == old.id


def test_requeue_stale_gives_up_after_max_attempts(db):
    """TC-WA-106 재시도 횟수를 넘은 stale 작업은 failed(worker_lost) 로 끝낸다."""
    j = jobs.enqueue(db, type="t", payload={}, now=T0)
    jobs.claim(db, worker_id="w", now=T0)
    db.execute(update(Job).where(Job.id == j.id).values(attempts=jobs.MAX_ATTEMPTS))
    db.commit()
    assert jobs.requeue_stale(db, now=T0 + timedelta(minutes=30)) == (0, 1)
    db.commit()
    db.expire_all()
    row = db.get(Job, j.id)
    assert row.status == "failed" and row.error == "worker_lost" and row.finished_at is not None


def test_update_progress_and_heartbeat(db):
    """TC-WA-107 update_progress 는 progress/total 을 갱신하고 running 작업의 locked_at 도 갱신한다."""
    j = jobs.enqueue(db, type="t", payload={}, total=3, now=T0)
    jobs.claim(db, worker_id="w", now=T0)
    jobs.update_progress(db, j.id, progress=2, total=9)
    db.commit()
    db.expire_all()
    row = db.get(Job, j.id)
    assert row.progress == 2 and row.total == 9 and row.locked_at > T0


def test_complete_and_fail_only_touch_running(db):
    """TC-WA-108 complete/fail 은 running 상태에서만 반영된다(이미 끝난 작업을 덮어쓰지 않음)."""
    j = jobs.enqueue(db, type="t", payload={}, now=T0)
    jobs.complete(db, j.id, result={"a": 1}, now=T0)
    db.expire_all()
    assert db.get(Job, j.id).status == "queued"
    jobs.claim(db, worker_id="w", now=T0)
    jobs.complete(db, j.id, result={"a": 1}, now=T0)
    jobs.fail(db, j.id, error="late", now=T0)
    db.expire_all()
    assert db.get(Job, j.id).status == "succeeded"


def test_worker_tick_processes_all_due_and_calls_scheduler(factory):
    """TC-WA-109 tick 은 due 작업을 모두 처리하고 배치 스케줄러(run_due_items)를 호출한다."""
    seen = []
    jobs.register_handler("t", lambda f, job: seen.append(job.payload["i"]) or None)
    with factory() as s:
        for i in range(3):
            jobs.enqueue(s, type="t", payload={"i": i}, now=T0)
        s.commit()
    ticks = []
    w = Worker(factory, clock=FakeClock(), run_due_items=lambda f, now: ticks.append(now))
    assert w.tick() == 3
    assert seen == [0, 1, 2] and len(ticks) == 1


def test_worker_stop_finishes_current_job_then_exits(factory):
    """TC-WA-110 작업 도중 종료 신호(SIGTERM)가 와도 현재 작업은 끝까지 마치고(succeeded) 다음 작업은 시작하지 않는다."""
    w = Worker(factory, clock=FakeClock())

    def handler(f, job):
        w.request_stop()
        return {"finished": True}

    jobs.register_handler("t", handler)
    with factory() as s:
        a = jobs.enqueue(s, type="t", payload={}, now=T0).id
        b = jobs.enqueue(s, type="t", payload={}, now=T0 + timedelta(seconds=1)).id
        s.commit()
    assert w.tick() == 1
    with factory() as s:
        assert s.get(Job, a).status == "succeeded" and s.get(Job, a).result == {"finished": True}
        assert s.get(Job, b).status == "queued"


def test_worker_scheduler_error_does_not_crash(factory):
    """TC-WA-111 배치 스케줄러가 예외를 던져도 tick 은 계속된다."""
    def bad(f, now):
        raise RuntimeError("x")

    assert Worker(factory, clock=FakeClock(), run_due_items=bad).tick() == 0


def test_worker_run_loop_stops_on_request(factory):
    """TC-WA-112 run() 루프는 request_stop 후 종료한다."""
    w = Worker(factory, clock=FakeClock(), poll_seconds=0.01)
    t = threading.Thread(target=w.run)
    t.start()
    w.request_stop()
    t.join(timeout=5)
    assert not t.is_alive()


def test_worker_maintenance_purges_expired(factory):
    """TC-WA-113 유지보수 틱이 만료 세션·오래된 멱등성 키를 지우고 stale 작업을 재큐한다."""
    clock = FakeClock()
    with factory() as s:
        s.add(SessionRow(id="a" * 64, csrf_token="c", created_at=T0 - timedelta(days=2), expires_at=T0 - timedelta(days=1), last_seen=T0))
        s.add(SessionRow(id="b" * 64, csrf_token="c", created_at=T0, expires_at=T0 + timedelta(days=1), last_seen=T0))
        s.add(IdempotencyKey(key="old-key-0001", route="r", request_hash="h", created_at=clock.now - timedelta(days=3)))
        s.add(IdempotencyKey(key="new-key-0001", route="r", request_hash="h", created_at=clock.now))
        jid = jobs.enqueue(s, type="t", payload={}, now=clock.now - timedelta(hours=1)).id
        jobs.claim(s, worker_id="dead", now=clock.now - timedelta(hours=1))
        s.commit()
    Worker(factory, clock=clock).maintenance()
    with factory() as s:
        assert [r.id[0] for r in s.execute(select(SessionRow)).scalars()] == ["b"]
        assert [k.key for k in s.execute(select(IdempotencyKey)).scalars()] == ["new-key-0001"]
        assert s.get(Job, jid).status == "queued"


def test_load_domain_handlers_never_raises():
    """TC-WA-114 도메인 모듈이 없거나 일부 깨져 있어도 워커 시작 로직은 예외 없이 (함수|None)을 돌려준다."""
    fn = load_domain_handlers()
    assert fn is None or callable(fn)
