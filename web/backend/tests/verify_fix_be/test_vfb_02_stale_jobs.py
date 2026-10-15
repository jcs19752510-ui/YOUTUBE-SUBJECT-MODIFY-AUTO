"""TC-VFB-020~: 워커 stale 작업 복구(DEF-7B-001) — 판정 경계, 유형별 기준, 기동 직후 즉시 재큐, 재큐 뒤 이중 반영 없음."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from ytweb.core import jobs
from ytweb.db.models import Batch, BatchItem, Change, Job
from ytweb.domain import handlers
from ytweb.domain.batches import recover_running_items, run_due_items
from ytweb.domain.common import set_default_env
from ytweb.worker import REAP_EVERY, Worker

from tests.verify_fix_be.conftest import life_ids
from tests.verify_wb.vbh import ok_sug
from ytweb.domain.batches import create_draft, execute_batch

T0 = datetime(2026, 10, 10, 3, 0, 0, tzinfo=timezone.utc)
US = timedelta(microseconds=1)


def _job(db, *, type="batch.execute", status="running", locked_at=T0, attempts=1, locked_by="w-old"):
    j = Job(type=type, status=status, payload={"batch_id": 1}, total=1, progress=0, attempts=attempts, run_after=T0, created_at=T0,
            locked_by=locked_by, locked_at=locked_at)
    db.add(j)
    db.commit()
    return j


@pytest.mark.parametrize("age,expect", [
    (timedelta(minutes=5) - US, False), (timedelta(minutes=5), False), (timedelta(minutes=5) + US, True), (timedelta(minutes=9), True),
])
def test_tc_vfb_020_batch_execute_uses_5_minute_limit_boundary(db, age, expect):
    j = _job(db, type="batch.execute", locked_at=T0)
    r = jobs.requeue_stale(db, now=T0 + age)
    db.commit(); db.refresh(j)
    assert (r == (1, 0)) is expect
    assert j.status == ("queued" if expect else "running")


@pytest.mark.parametrize("typ", ["videos.sync", "suggestions.generate"])
@pytest.mark.parametrize("age,expect", [
    (timedelta(minutes=9, seconds=59), False), (timedelta(minutes=10), False), (timedelta(minutes=10) + US, True), (timedelta(minutes=6), False),
])
def test_tc_vfb_021_other_job_types_keep_10_minute_limit(db, typ, age, expect):
    """5분 단축이 batch.execute 에만 적용된다(다른 유형까지 5분으로 번지면 정상 작업이 재큐된다)."""
    j = _job(db, type=typ)
    r = jobs.requeue_stale(db, now=T0 + age)
    db.commit(); db.refresh(j)
    assert (r == (1, 0)) is expect


def test_tc_vfb_022_requeue_clears_lock_keeps_attempts_and_can_be_reclaimed(db):
    j = _job(db, attempts=2)
    assert jobs.requeue_stale(db, now=T0 + timedelta(minutes=6)) == (1, 0)
    db.commit(); db.refresh(j)
    assert (j.status, j.locked_by, j.locked_at, j.attempts, j.finished_at) == ("queued", None, None, 2, None)
    got = jobs.claim(db, worker_id="w-new", now=T0 + timedelta(minutes=7))
    db.commit()
    assert got is not None and got.id == j.id and got.attempts == 3 and got.locked_by == "w-new"


@pytest.mark.parametrize("attempts,expect", [(2, (1, 0)), (3, (0, 1)), (4, (0, 1))])
def test_tc_vfb_023_attempt_cap_fails_with_worker_lost(db, attempts, expect):
    j = _job(db, attempts=attempts)
    assert jobs.requeue_stale(db, now=T0 + timedelta(hours=1)) == expect
    db.commit(); db.refresh(j)
    if expect[1]:
        assert j.status == "failed" and j.error == "worker_lost" and j.finished_at is not None and j.locked_at is None
    else:
        assert j.status == "queued"


def test_tc_vfb_024_job_without_heartbeat_is_always_orphan_even_when_fresh(db):
    """locked_at 이 비어 있는 running 작업은 시간과 무관하게 고아."""
    j = _job(db, locked_at=None)
    assert jobs.requeue_stale(db, now=T0) == (1, 0)
    db.commit(); db.refresh(j)
    assert j.status == "queued"


@pytest.mark.parametrize("status", ["queued", "succeeded", "failed"])
def test_tc_vfb_025_only_running_jobs_are_touched(db, status):
    j = _job(db, status=status)
    assert jobs.requeue_stale(db, now=T0 + timedelta(days=1)) == (0, 0)
    db.refresh(j)
    assert j.status == status


def test_tc_vfb_026_explicit_stale_after_overrides_type_defaults(db):
    a = _job(db, type="batch.execute", locked_at=T0)
    b = _job(db, type="videos.sync", locked_at=T0)
    assert jobs.requeue_stale(db, now=T0 + timedelta(minutes=30), stale_after=timedelta(hours=1)) == (0, 0)
    assert jobs.requeue_stale(db, now=T0 + timedelta(minutes=30), stale_after=timedelta(minutes=29)) == (2, 0)
    db.commit(); db.refresh(a); db.refresh(b)
    assert a.status == b.status == "queued"


def test_tc_vfb_027_stale_after_zero_means_every_running_job_is_orphan_but_not_future_locks(db):
    old = _job(db, locked_at=T0 - timedelta(seconds=1))
    same = _job(db, locked_at=T0)            # now 와 같은 시각: 아직 생존 신호가 있는 것으로 본다(>=)
    fut = _job(db, locked_at=T0 + timedelta(seconds=5))
    assert jobs.requeue_stale(db, now=T0, stale_after=timedelta(0)) == (1, 0)
    db.commit()
    for j in (old, same, fut):
        db.refresh(j)
    assert (old.status, same.status, fut.status) == ("queued", "running", "running")


def test_tc_vfb_028_heartbeat_via_update_progress_prevents_requeue(db, monkeypatch):
    """진행 보고가 locked_at 을 갱신하므로 오래 걸리지만 살아 있는 작업은 재큐되지 않는다."""
    j = _job(db, locked_at=T0)
    fresh = T0 + timedelta(minutes=20)
    monkeypatch.setattr("ytweb.core.jobs.utcnow", lambda: fresh)
    jobs.update_progress(db, j.id, progress=3)
    db.commit(); db.refresh(j)
    assert j.locked_at.replace(tzinfo=timezone.utc) == fresh if j.locked_at.tzinfo is None else j.locked_at == fresh
    assert jobs.requeue_stale(db, now=fresh + timedelta(minutes=4, seconds=59)) == (0, 0)
    assert jobs.requeue_stale(db, now=fresh + timedelta(minutes=5) + timedelta(seconds=1)) == (1, 0)


def test_tc_vfb_029_update_progress_does_not_resurrect_non_running_job(db, monkeypatch):
    j = _job(db, status="queued", locked_at=None)
    monkeypatch.setattr("ytweb.core.jobs.utcnow", lambda: T0)
    jobs.update_progress(db, j.id, progress=1)
    db.commit(); db.refresh(j)
    assert j.locked_at is None and j.progress == 1


# ───────────── Worker ─────────────

def _worker(factory, clock, **kw):
    return Worker(factory, clock=clock, worker_id="vfb", poll_seconds=0.01, **kw)


def test_tc_vfb_030_reap_is_throttled_to_once_a_minute_and_force_bypasses(factory, clock, db):
    j = _job(db, type="videos.sync", locked_at=clock() - timedelta(hours=1))
    w = _worker(factory, clock)
    assert w.reap_stale_jobs() == (1, 0)
    db.expire_all(); assert db.get(Job, j.id).status == "queued"
    j2 = _job(db, type="videos.sync", locked_at=clock() - timedelta(hours=1))
    clock.advance(seconds=59)
    assert w.reap_stale_jobs() == (0, 0)                                   # 59초: 건너뜀
    db.expire_all(); assert db.get(Job, j2.id).status == "running"
    clock.advance(seconds=1)
    assert w.reap_stale_jobs() == (1, 0)                                   # 정확히 60초: 실행(경계 포함)
    j3 = _job(db, type="videos.sync", locked_at=clock() - timedelta(hours=1))
    assert w.reap_stale_jobs() == (0, 0)
    assert w.reap_stale_jobs(force=True) == (1, 0)
    assert REAP_EVERY == timedelta(minutes=1)


def test_tc_vfb_031_tick_reaps_stale_batch_job_between_polls(factory, clock, db):
    j = _job(db, locked_at=clock() - timedelta(minutes=6))
    w = _worker(factory, clock)
    w.tick()
    db.expire_all()
    got = db.get(Job, j.id)
    assert got.status != "running" and got.attempts >= 1       # 재큐되어 같은 틱에서 다시 잡혔거나(attempts+1) 처리기 오류로 failed


def test_tc_vfb_032_reap_failure_does_not_stop_the_tick(factory, clock, monkeypatch):
    calls = []
    w = _worker(factory, clock, run_due_items=lambda f, now: calls.append(now))
    monkeypatch.setattr(w, "reap_stale_jobs", lambda **kw: (_ for _ in ()).throw(RuntimeError("x")))
    w.tick()
    assert calls, "reap 실패가 배치 스케줄러 틱을 막으면 안 된다"


def test_tc_vfb_033_run_startup_reaps_everything_running_immediately_and_recovers_items_first(factory, clock, db):
    order = []
    j = _job(db, type="videos.sync", locked_at=clock() - timedelta(seconds=1))      # 1초 전에 잡힌 작업도 기동 직후엔 고아
    w = _worker(factory, clock, startup_recover=lambda f, now, stale_after: order.append(("recover", stale_after)))
    orig = w.reap_stale_jobs

    def spy(**kw):
        order.append(("reap", kw))
        return orig(**kw)

    w.reap_stale_jobs = spy
    w.tick = lambda: w.stop_event.set() or 0       # 한 번만 돌고 종료
    w.run()
    assert order[0] == ("recover", timedelta(0))
    assert order[1] == ("reap", {"force": True, "stale_after": timedelta(0)})
    db.expire_all()
    assert db.get(Job, j.id).status == "queued"


def test_tc_vfb_034_startup_reap_error_is_swallowed_and_loop_still_starts(factory, clock):
    w = _worker(factory, clock)
    w.reap_stale_jobs = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
    ticks = []
    w.tick = lambda: (ticks.append(1), w.stop_event.set())[1] or 0
    w.run()
    assert ticks == [1]


def test_tc_vfb_035_startup_attempt_cap_fails_job_instead_of_looping_forever(factory, clock, db):
    j = _job(db, type="videos.sync", attempts=3, locked_at=clock() - timedelta(seconds=1))
    w = _worker(factory, clock)
    w.tick = lambda: w.stop_event.set() or 0
    w.run()
    db.expire_all()
    got = db.get(Job, j.id)
    assert got.status == "failed" and got.error == "worker_lost"


# ───────────── 재시작 시나리오(원래 재현 IT-318) ─────────────

@pytest.fixture
def two_item_batch(seeded, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    sugs = [ok_sug(seeded, env, clock(), v) for v in life_ids(seeded, 3)]
    b, pre = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=env)
    b, job = execute_batch(seeded, b.id, pre["confirm_text"], now=clock(), env=env)
    seeded.commit()
    return b.id, job.id, sugs


def _n(db, model):
    db.expire_all()
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def test_tc_vfb_036_worker_killed_mid_job_then_restart_finishes_without_double_apply(two_item_batch, factory, db, clock):
    """IT-318 재현: 작업이 running 인 채 워커가 죽음(항목 1건만 반영) → 새 워커 기동 시 즉시 재큐 → 나머지만 반영, 이중 반영 0."""
    bid, jid, sugs = two_item_batch
    claimed = jobs.claim(db, worker_id="dead-worker", now=clock()); db.commit()
    assert claimed.id == jid
    run_due_items(factory, clock(), batch_id=bid, job_id=jid)                           # 3건 모두 반영된 상태(상한 안)
    done_changes = _n(db, Change)
    # 죽은 워커가 항목 반영은 끝냈지만 작업 완료 기록 전에 종료 → 작업은 running 으로 남음
    assert db.get(Job, jid).status == "running"
    clock.advance(seconds=2)
    w = _worker(factory, clock, startup_recover=recover_running_items)
    w.tick = lambda: (jobs.process_next(factory, worker_id="vfb", clock=clock), w.stop_event.set())[1] or 0
    w.run()
    db.expire_all()
    job = db.get(Job, jid)
    assert job.status == "succeeded" and job.attempts == 2
    assert _n(db, Change) == done_changes == 3            # 재처리해도 변경 기록이 늘지 않는다
    assert db.get(Batch, bid).status == "done"
    vids = db.execute(select(Change.video_id)).scalars().all()
    assert len(vids) == len(set(vids))


def test_tc_vfb_037_requeue_of_unfinished_job_continues_remaining_items_only(two_item_batch, factory, db, clock):
    bid, jid, sugs = two_item_batch
    jobs.claim(db, worker_id="dead-worker", now=clock()); db.commit()
    # 첫 항목만 반영된 뒤 사망 상태를 만든다
    from ytweb.domain.batches import apply_one
    from ytweb.youtube.mock import MockYouTubeGateway
    first = db.execute(select(BatchItem).where(BatchItem.batch_id == bid).order_by(BatchItem.seq)).scalars().first()
    apply_one(db, first.id, now=clock(), env=__import__("ytweb.domain.common", fromlist=["default_env"]).default_env(), gateway=MockYouTubeGateway(db, clock))
    assert _n(db, Change) == 1
    clock.advance(minutes=6)
    w = _worker(factory, clock)
    assert w.reap_stale_jobs() == (1, 0)
    assert jobs.process_next(factory, worker_id="vfb", clock=clock)
    assert _n(db, Change) == 3
    assert db.get(Job, jid).status == "succeeded"
    ids = db.execute(select(Change.video_id)).scalars().all()
    assert len(ids) == len(set(ids))


def test_tc_vfb_038_live_job_just_heartbeated_is_not_requeued_by_tick(two_item_batch, factory, db, clock):
    bid, jid, sugs = two_item_batch
    jobs.claim(db, worker_id="other", now=clock()); db.commit()
    clock.advance(minutes=4, seconds=59)
    w = _worker(factory, clock)
    assert w.reap_stale_jobs(force=True) == (0, 0)
    db.expire_all()
    assert db.get(Job, jid).status == "running"


# ───────────── PostgreSQL ─────────────

pg_mark = pytest.mark.postgres


@pg_mark
def test_tc_vfb_040_pg_requeue_skips_row_locked_by_another_transaction(pg, clock):
    with pg() as s:
        j = _job(s, locked_at=T0)
        jid = j.id
    holder = pg()
    holder.execute(select(Job).where(Job.id == jid).with_for_update()).scalar_one()      # 다른 처리자가 행을 잡고 있음
    try:
        with pg() as s2:
            s2.execute(__import__("sqlalchemy").text("SET LOCAL lock_timeout = '2s'"))
            assert jobs.requeue_stale(s2, now=T0 + timedelta(hours=1)) == (0, 0)         # 막히지 않고 건너뛴다
            s2.commit()
    finally:
        holder.rollback(); holder.close()
    with pg() as s3:
        assert jobs.requeue_stale(s3, now=T0 + timedelta(hours=1)) == (1, 0)
        s3.commit()


@pg_mark
def test_tc_vfb_041_pg_concurrent_requeue_counts_each_job_once(pg):
    with pg() as s:
        ids = [_job(s, locked_at=T0).id for _ in range(6)]
    results = []

    def run():
        with pg() as s:
            results.append(jobs.requeue_stale(s, now=T0 + timedelta(hours=1)))
            s.commit()

    ts = [threading.Thread(target=run) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sum(r[0] for r in results) == 6 and sum(r[1] for r in results) == 0
    with pg() as s:
        assert {s.get(Job, i).status for i in ids} == {"queued"}


@pg_mark
def test_tc_vfb_042_pg_null_locked_at_is_orphan(pg):
    with pg() as s:
        j = _job(s, locked_at=None); jid = j.id
        assert jobs.requeue_stale(s, now=T0) == (1, 0)
        s.commit()
        assert s.get(Job, jid).status == "queued"
