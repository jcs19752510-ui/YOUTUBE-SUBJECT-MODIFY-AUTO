"""독립 점검 6: 잡 큐 · 워커 (S-W12). SQLite 판(동시성은 PostgreSQL 파일에서)."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from ytweb.core import jobs
from ytweb.core.errors import ProblemError
from ytweb.db.models import IdempotencyKey, Job, SessionRow
from ytweb.worker import MAINTENANCE_EVERY, Worker

T0 = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)
US = timedelta(microseconds=1)


@pytest.fixture(autouse=True)
def _handlers(monkeypatch):
    monkeypatch.setattr(jobs, "_HANDLERS", {})


def _get(factory, jid) -> Job:
    with factory() as s:
        return s.get(Job, jid)


def test_enqueue_defaults_and_claim_due_boundary(db):
    """TC-VA-100 [S-W12] 새 작업은 queued/attempts=0, run_after 가 미래면 claim 되지 않고 정확히 run_after 시각부터 claim 된다."""
    j = jobs.enqueue(db, type="t", payload={"a": 1}, total=3, now=T0 + timedelta(minutes=5))
    db.commit()
    assert (j.status, j.attempts, j.progress, j.total) == ("queued", 0, 0, 3)
    assert jobs.claim(db, worker_id="w", now=T0 + timedelta(minutes=5) - US) is None
    got = jobs.claim(db, worker_id="w", now=T0 + timedelta(minutes=5))
    assert got is not None and got.id == j.id and got.status == "running" and got.attempts == 1 and got.locked_by == "w"


def test_claim_is_fifo_by_run_after_then_created_and_never_twice(db):
    """TC-VA-101 [S-W12] claim 순서는 run_after, created_at 순이고, 한 번 가져간 작업은 다시 claim 되지 않는다."""
    a = jobs.enqueue(db, type="t", payload={}, now=T0 + timedelta(seconds=2)).id
    b = jobs.enqueue(db, type="t", payload={}, now=T0).id
    c = jobs.enqueue(db, type="t", payload={}, now=T0 + timedelta(seconds=1)).id
    db.commit()
    order = []
    while True:
        j = jobs.claim(db, worker_id="w", now=T0 + timedelta(hours=1))
        db.commit()
        if j is None:
            break
        order.append(j.id)
    assert order == [b, c, a] and len(set(order)) == 3


def test_complete_and_fail_only_affect_running_jobs(db):
    """TC-VA-102 [S-W12] queued 작업에 complete/fail 을 호출해도 상태가 바뀌지 않고, 이미 끝난 작업도 되살아나지 않는다."""
    j = jobs.enqueue(db, type="t", payload={}, now=T0)
    db.commit()
    jobs.complete(db, j.id, result={"x": 1}, now=T0)
    jobs.fail(db, j.id, error="e", now=T0)
    db.commit(); db.refresh(j)
    assert j.status == "queued"
    jobs.claim(db, worker_id="w", now=T0); db.commit()
    jobs.complete(db, j.id, result={"x": 1}, now=T0); db.commit(); db.refresh(j)
    assert j.status == "succeeded" and j.result == {"x": 1} and j.locked_by is None
    jobs.fail(db, j.id, error="late", now=T0); db.commit(); db.refresh(j)
    assert j.status == "succeeded" and j.error is None


def test_error_text_is_truncated_and_handler_exception_text_not_stored(factory):
    """TC-VA-103 [S-W09, S-W12] 실패 사유는 300자로 잘리고, 핸들러의 일반 예외는 클래스명만 저장되어 메시지(경로·비밀)가 DB 에 남지 않는다."""
    with factory() as s:
        j1 = jobs.enqueue(s, type="boom", payload={}, now=T0).id
        j2 = jobs.enqueue(s, type="prob", payload={}, now=T0 + US).id
        j3 = jobs.enqueue(s, type="none", payload={}, now=T0 + 2 * US).id
        s.commit()
        jobs.claim(s, worker_id="w", now=T0 + timedelta(seconds=1))
        jobs.fail(s, j1, error="x" * 1000, now=T0)
        s.commit()
        assert len(s.get(Job, j1).error) == 300
        s.get(Job, j1).status = "queued"; s.commit()
    jobs.register_handler("boom", lambda f, j: (_ for _ in ()).throw(RuntimeError("/srv/secret.py password=hunter2")))
    jobs.register_handler("prob", lambda f, j: (_ for _ in ()).throw(ProblemError(409, "conflict_x", "충돌")))
    clock = lambda: T0 + timedelta(minutes=1)  # noqa: E731
    while jobs.process_next(factory, worker_id="w", clock=clock):
        pass
    e1, e2, e3 = (_get(factory, i) for i in (j1, j2, j3))
    assert (e1.status, e1.error) == ("failed", "internal_error: RuntimeError")
    assert (e2.status, e2.error) == ("failed", "conflict_x: 충돌")
    assert e3.status == "failed" and e3.error.startswith("no_handler")
    assert "hunter2" not in (e1.error or "") and "secret" not in (e1.error or "")


def test_failed_job_is_never_retried_automatically(factory):
    """TC-VA-104 [S-W12] 핸들러 예외로 failed 가 된 작업은 자동 재시도되지 않는다(부작용 있는 작업의 중복 실행 방지) -> 핸들러는 1회만 호출."""
    calls = []
    jobs.register_handler("t", lambda f, j: calls.append(j.id) or (_ for _ in ()).throw(RuntimeError("x")))
    with factory() as s:
        jobs.enqueue(s, type="t", payload={}, now=T0); s.commit()
    clk = lambda: T0 + timedelta(days=1)  # noqa: E731
    for _ in range(5):
        jobs.process_next(factory, worker_id="w", clock=clk)
    assert len(calls) == 1


@pytest.mark.parametrize("age,stale", [(timedelta(minutes=10), False), (timedelta(minutes=10) + US, True), (timedelta(minutes=9, seconds=59), False)])
def test_requeue_stale_time_boundary(db, age, stale):
    """TC-VA-105 [S-W12] stale 판정 경계: locked_at 이 정확히 10분 전이면 정상 실행 중, 10분+1µs 전이면 재큐."""
    j = jobs.enqueue(db, type="t", payload={}, now=T0)
    db.commit()
    jobs.claim(db, worker_id="w", now=T0); db.commit()
    now = T0 + age
    requeued, failed = jobs.requeue_stale(db, now=now); db.commit(); db.refresh(j)
    assert (requeued == 1) is stale and failed == 0
    assert j.status == ("queued" if stale else "running")


@pytest.mark.parametrize("attempts,expected", [(1, "queued"), (2, "queued"), (3, "failed"), (4, "failed")])
def test_requeue_stale_attempt_cap(db, attempts, expected):
    """TC-VA-106 [S-W12] 죽은 워커의 작업은 시도 3회 미만이면 재큐, 3회 이상이면 failed(worker_lost)."""
    j = jobs.enqueue(db, type="t", payload={}, now=T0)
    db.commit()
    jobs.claim(db, worker_id="w", now=T0)
    j.attempts = attempts
    db.commit()
    jobs.requeue_stale(db, now=T0 + timedelta(hours=1)); db.commit(); db.refresh(j)
    assert j.status == expected
    assert j.locked_by is None and j.locked_at is None
    if expected == "failed":
        assert j.error == "worker_lost" and j.finished_at is not None


def test_requeued_job_runs_again_and_dead_worker_result_is_replaced(factory):
    """TC-VA-107 [S-W12] 워커가 죽어 running 으로 남은 작업이 재큐 후 다른 워커에게 처리되어 succeeded 가 된다(attempts=2)."""
    with factory() as s:
        jid = jobs.enqueue(s, type="t", payload={}, now=T0).id
        jobs.claim(s, worker_id="dead", now=T0); s.commit()
        assert jobs.requeue_stale(s, now=T0 + timedelta(minutes=30)) == (1, 0); s.commit()
    jobs.register_handler("t", lambda f, j: {"by": j.locked_by})
    assert jobs.process_next(factory, worker_id="alive", clock=lambda: T0 + timedelta(minutes=31)) is True
    j = _get(factory, jid)
    assert j.status == "succeeded" and j.attempts == 2 and j.result == {"by": "alive"}


def test_update_progress_heartbeat_only_for_running(factory):
    """TC-VA-108 [S-W12] update_progress 는 running 작업의 locked_at 을 갱신(하트비트)하고 queued 작업은 locked_at 을 만들지 않는다."""
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)  # 하트비트는 실제 시계(utcnow)를 쓰므로 충분히 과거 기준으로 비교
    with factory() as s:
        q = jobs.enqueue(s, type="t", payload={}, total=10, now=past).id
        r = jobs.enqueue(s, type="t", payload={}, total=10, now=past + US).id
        s.commit()
        jobs.claim(s, worker_id="w", now=past + timedelta(seconds=1)); s.commit()  # q 가 claim 됨(먼저)
        running, queued = q, r
        old = s.get(Job, running).locked_at
        jobs.update_progress(s, running, progress=4, total=12)
        jobs.update_progress(s, queued, progress=1)
        s.commit(); s.expire_all()
        assert s.get(Job, running).progress == 4 and s.get(Job, running).total == 12
        assert s.get(Job, running).locked_at > old
        assert s.get(Job, queued).locked_at is None and s.get(Job, queued).progress == 1


def test_complete_without_fencing_lets_a_slow_old_worker_finish_a_reclaimed_job(db):
    """TC-VA-109 [S-W12] (특성화) complete() 는 locked_by 를 확인하지 않는다: stale 로 재큐되어 다른 워커가 재실행 중인 작업을 느린 옛 워커가 succeeded 로 닫을 수 있다 -> 부작용 핸들러는 멱등이어야 함(권고 R-3)."""
    j = jobs.enqueue(db, type="t", payload={}, now=T0)
    db.commit()
    jobs.claim(db, worker_id="old", now=T0); db.commit()
    jobs.requeue_stale(db, now=T0 + timedelta(minutes=11)); db.commit()
    jobs.claim(db, worker_id="new", now=T0 + timedelta(minutes=12)); db.commit()
    jobs.complete(db, j.id, result={"by": "old"}, now=T0 + timedelta(minutes=13)); db.commit(); db.refresh(j)
    assert j.status == "succeeded" and j.result == {"by": "old"}  # 새 워커는 아직 실행 중인데 닫혔다


# ---------------------------------------------------------------- 워커

def test_worker_stop_request_finishes_current_job_and_leaves_the_rest_queued(factory):
    """TC-VA-110 [S-W12] 종료 신호(stop)가 오면 실행 중인 작업은 끝까지 마쳐 succeeded 가 되고, 나머지 작업은 queued 로 남아 다음 워커가 처리한다."""
    w = Worker(factory, clock=lambda: T0 + timedelta(minutes=1), worker_id="w1", poll_seconds=0.01)
    seen = []

    def handler(f, j):
        seen.append(j.id)
        w.request_stop()  # 처리 도중 SIGTERM 이 왔다고 가정
        return {"done": True}
    jobs.register_handler("t", handler)
    with factory() as s:
        ids = [jobs.enqueue(s, type="t", payload={}, now=T0 + i * US).id for i in range(3)]
        s.commit()
    assert w.tick() == 1
    assert [_get(factory, i).status for i in ids] == ["succeeded", "queued", "queued"]
    assert seen == [ids[0]]


def test_worker_maintenance_purges_expired_sessions_and_old_idempotency_keys_with_boundaries(factory):
    """TC-VA-111 [S-W08, S-W12] 정비: 만료된 세션 삭제(만료 시각 정각 포함), 멱등성 키는 48시간 초과분만 삭제(정확히 48시간은 보존), 10분 안의 재정비는 건너뜀."""
    now = T0 + timedelta(days=3)
    with factory() as s:
        s.add_all([
            SessionRow(id="a" * 64, csrf_token="c", created_at=T0, expires_at=now, last_seen=T0),                    # 정각 만료 -> 삭제
            SessionRow(id="b" * 64, csrf_token="c", created_at=T0, expires_at=now + US, last_seen=T0),               # 유효
            IdempotencyKey(key="idem-old-00001", route="r", request_hash="h", created_at=now - timedelta(hours=48) - US),  # 삭제
            IdempotencyKey(key="idem-edge-0001", route="r", request_hash="h", created_at=now - timedelta(hours=48)),       # 보존
        ])
        s.commit()
    w = Worker(factory, clock=lambda: now)
    w.maintenance()
    with factory() as s:
        assert {r for (r,) in s.execute(select(SessionRow.id))} == {"b" * 64}
        assert {r for (r,) in s.execute(select(IdempotencyKey.key))} == {"idem-edge-0001"}
        s.add(SessionRow(id="c" * 64, csrf_token="c", created_at=T0, expires_at=T0, last_seen=T0)); s.commit()
    w.maintenance()  # 10분 이내 -> 건너뜀
    with factory() as s:
        assert s.get(SessionRow, "c" * 64) is not None
    w.clock = lambda: now + MAINTENANCE_EVERY
    w.maintenance()
    with factory() as s:
        assert s.get(SessionRow, "c" * 64) is None


def test_worker_tick_survives_scheduler_exception(factory):
    """TC-VA-112 [S-W12] 배치 스케줄러 함수가 예외를 던져도 tick 이 죽지 않고 작업 처리는 계속된다."""
    jobs.register_handler("t", lambda f, j: {})
    with factory() as s:
        jobs.enqueue(s, type="t", payload={}, now=T0); s.commit()

    def bad(*a):
        raise RuntimeError("scheduler down")
    w = Worker(factory, clock=lambda: T0 + timedelta(minutes=1), run_due_items=bad)
    assert w.tick() == 1


def _run_worker_process(tmp_path: Path, env_extra: dict[str, str]):
    # 하위 프로세스는 cwd 가 tmp_path 라 패키지가 설치돼 있지 않으면 ytweb 를 못 찾는다 -> 소스 루트를 PYTHONPATH 로 준다(2026-10-10 수정: 이전 버전은 이 줄이 없어 워커가 기동 즉시 죽었다).
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2]), **env_extra}
    return subprocess.Popen([sys.executable, "-m", "ytweb.worker"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(tmp_path))


def test_worker_process_handles_sigterm_gracefully_and_processes_jobs(tmp_path, web_settings):
    """TC-VA-113 [S-W12] 실제 워커 프로세스: 큐의 작업을 처리(처리기 없음 -> failed)하고, SIGTERM 에 즉시 정상 종료(코드 0, 5초 이내)한다."""
    from ytweb.db.models import Base
    from ytweb.db.session import make_engine, make_session_factory
    db_path = tmp_path / "w.db"
    url = f"sqlite:///{db_path}"
    eng = make_engine(url)
    Base.metadata.create_all(eng)
    f = make_session_factory(eng)
    with f() as s:
        jid = jobs.enqueue(s, type="zzz.unknown", payload={}, now=datetime.now(timezone.utc) - timedelta(seconds=1)).id
        s.commit()
    p = _run_worker_process(tmp_path, {"YTWEB_DATABASE_URL": url, "YTWEB_BASE_DIR": str(web_settings.base_dir),
                                       "YTWEB_SECRETS_DIR": str(tmp_path / "sec"), "YTWEB_LOG_JSON": "1"})
    try:
        deadline = time.time() + 20
        status = None
        while time.time() < deadline:
            with f() as s:
                status = s.get(Job, jid).status
            if status != "queued" and status != "running":
                break
            time.sleep(0.3)
        assert status == "failed"
        t0 = time.time()
        p.send_signal(signal.SIGTERM)
        rc = p.wait(timeout=10)
        assert rc == 0 and time.time() - t0 < 5
        err = p.stderr.read()
        assert "worker stopped" in err
    finally:
        if p.poll() is None:
            p.kill()
        eng.dispose()
