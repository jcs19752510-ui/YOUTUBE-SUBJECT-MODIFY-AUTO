"""수정 단위 W-FIX-BE(2026-10-11) PostgreSQL 시험 TC-WBX-034~: 초안 취소 경합, stale 재큐 경합, 재시작 후 이중 처리 없음.
YTWEB_TEST_PG_URL 이 없으면 건너뛴다."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from ytweb.core import audit, jobs
from ytweb.core.errors import ProblemError
from ytweb.core.settings_store import set_web_setting
from ytweb.db.models import AuditLog, Base, Batch, BatchItem, Change, Job, Suggestion
from ytweb.db.session import make_engine, make_session_factory
from ytweb.domain import handlers
from ytweb.domain.batches import apply_one, cancel_batch, create_draft, execute_batch, recover_running_items
from ytweb.domain.common import set_default_env
from ytweb.domain.seed import seed_demo
from ytweb.worker import Worker
from ytweb.youtube.mock import MockYouTubeGateway

from tests.domain.helpers import approved_many, queued_batch

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg(pg_url, env, clock):
    engine = make_engine(pg_url)
    Base.metadata.drop_all(engine)   # 이 테스트 전용 DB 안의 테이블만 만들고 지운다(DB 자체는 건드리지 않음)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=40)
        s.commit()
    yield factory
    engine.dispose()
    cleanup = make_engine(pg_url)
    Base.metadata.drop_all(cleanup)
    cleanup.dispose()


def _race(fns):
    barrier = threading.Barrier(len(fns))

    def run(fn):
        barrier.wait()
        try:
            return fn()
        except ProblemError as exc:
            return exc.code

    with ThreadPoolExecutor(len(fns)) as ex:
        return list(ex.map(run, fns))


def _draft(pg, env, clock, n, skip=0):
    with pg() as s:
        sugs = approved_many(s, env, clock(), n, skip)
        batch, pre = create_draft(s, [x.id for x in sugs], None, now=clock(), env=env)
        s.commit()
        return batch.id, [x.id for x in sugs], pre


def test_tc_wbx_034_two_concurrent_cancels_of_one_draft_apply_exactly_once(pg, env, clock):
    bid, sids, _ = _draft(pg, env, clock, 3)

    def cancel():
        with pg() as s:
            out = cancel_batch(s, bid, now=clock(), env=env)
            s.commit()
            return out.status

    res = _race([cancel, cancel])
    assert sorted(map(str, res)) == ["batch_not_cancellable", "cancelled"], res
    with pg() as s:
        assert s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "batch.cancel")).scalar_one() == 1
        assert {i.status for i in s.get(Batch, bid).items} == {"cancelled"}
        assert audit.verify_chain(s)


@pytest.mark.parametrize("round_", range(6))
def test_tc_wbx_035_discard_draft_races_with_execute_without_leaving_stuck_state(pg, env, clock, round_):
    bid, sids, pre = _draft(pg, env, clock, 2, skip=round_ * 3)

    def execute():
        with pg() as s:
            execute_batch(s, bid, pre["confirm_text"], now=clock(), env=env)
            s.commit()
            return "executed"

    def cancel():
        with pg() as s:
            cancel_batch(s, bid, now=clock(), env=env)
            s.commit()
            return "cancelled"

    res = _race([execute, cancel])
    assert "cancelled" in res and set(res) <= {"cancelled", "executed", "batch_not_draft", "batch_not_cancellable"}, res
    with pg() as s:
        batch = s.get(Batch, bid)
        assert batch.status == "cancelled"
        assert {i.status for i in batch.items} == {"cancelled"}                       # 실행이 먼저 이겨도 취소가 대기 항목을 모두 닫는다
        assert {s.get(Suggestion, i).status for i in sids} == {"approved"}           # 'queued' 로 갇히지 않는다
        assert s.execute(select(func.count()).select_from(Change)).scalar_one() == 0
    with pg() as s:                                                                    # 풀려난 제안은 새 초안에 바로 담긴다
        again, pre2 = create_draft(s, sids, None, now=clock(), env=env)
        assert pre2["item_count"] == 2 and pre2["blocked"] == []


def test_tc_wbx_036_two_drafts_for_one_suggestion_only_one_wins_and_loser_is_told_why(pg, env, clock):
    with pg() as s:
        sug, other = approved_many(s, env, clock(), 2)
        s.commit()
        ids = (sug.id, other.id)

    def make(extra):
        def fn():
            with pg() as s:
                batch, pre = create_draft(s, [ids[0], *extra], None, now=clock(), env=env)
                s.commit()
                return ("ok", batch.id, pre["blocked"])
        return fn

    res = _race([make([]), make([ids[1]])])
    winners = [r for r in res if isinstance(r, tuple)]
    losers = [r for r in res if not isinstance(r, tuple)]
    assert len(winners) + len(losers) == 2
    assert len(winners) >= 1
    with pg() as s:
        holders = s.execute(select(BatchItem.batch_id).where(BatchItem.suggestion_id == ids[0], BatchItem.status == "pending")).scalars().all()
        assert len(holders) == 1                                                        # 부분 고유 인덱스가 둘째 점유를 막았다
    for kind, _, blocked in winners:
        for b in blocked:
            assert b["code"] == "already_in_batch" and b["batch_id"] == holders[0] and f"초안 배치 #{holders[0]}" in b["reason"]
    for code in losers:
        assert code in ("batch_empty", "already_in_batch")


def test_tc_wbx_037_concurrent_requeue_stale_never_double_counts(pg, clock):
    now = clock()
    with pg() as s:
        for _ in range(12):
            j = jobs.enqueue(s, type="batch.execute", payload={"batch_id": 1}, now=now)
            s.execute(update(Job).where(Job.id == j.id).values(status="running", locked_by="dead:1", locked_at=now - timedelta(minutes=6), attempts=1))
        s.commit()

    def reap():
        with pg() as s:
            out = jobs.requeue_stale(s, now=now)
            s.commit()
            return out

    res = _race([reap, reap, reap])
    assert sum(r[0] for r in res) == 12 and sum(r[1] for r in res) == 0, res
    with pg() as s:
        assert {(j.status, j.attempts) for j in s.execute(select(Job)).scalars()} == {("queued", 1)}


def test_tc_wbx_038_restart_requeues_job_and_finishes_batch_without_double_apply(pg, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    with pg() as s:
        set_web_setting(s, "daily_apply_cap", 20, now=clock())
        s.commit()
        batch, sugs, job = queued_batch(s, env, clock(), 6)
        bid, jid = batch.id, job.id
        item_ids = [i.id for i in batch.items]
        s.execute(update(BatchItem).where(BatchItem.batch_id == bid).values(scheduled_date=batch.items[0].scheduled_date))
        s.commit()
    with pg() as s:   # 앞의 2건은 정상 반영
        for item_id in item_ids[:2]:
            assert apply_one(s, item_id, now=clock(), env=env, gateway=MockYouTubeGateway(s, clock)).status == "success"
    with pg() as s:   # 3번째는 갱신 직후 프로세스가 죽는다
        g = MockYouTubeGateway(s, clock)
        orig = g.update_snippet

        class Crash(BaseException):
            pass

        def upd(video_id, body):
            orig(video_id, body)
            s.commit()
            raise Crash()

        g.update_snippet = upd   # type: ignore[method-assign]
        with pytest.raises(Crash):
            apply_one(s, item_ids[2], now=clock(), env=env, gateway=g)
        s.rollback()
    with pg() as s:   # 작업 행은 죽은 워커의 running 으로 남는다
        s.execute(update(Job).where(Job.id == jid).values(status="running", locked_by="dead:1", locked_at=clock() - timedelta(seconds=20), attempts=1))
        s.commit()

    worker = Worker(pg, clock=clock, startup_recover=recover_running_items)
    worker.stop_event.set()
    worker.run()                                   # 항목 복구 → 작업 재큐
    with pg() as s:
        assert s.get(Job, jid).status == "queued"
        assert s.get(BatchItem, item_ids[2]).status == "success"
    assert jobs.process_next(pg, worker_id="w", clock=clock) is True
    with pg() as s:
        job = s.get(Job, jid)
        assert job.status == "succeeded" and job.attempts == 2 and job.result["success"] == 3
        assert s.get(Batch, bid).status == "done" and {i.status for i in s.get(Batch, bid).items} == {"success"}
        assert s.execute(select(func.count()).select_from(Change).where(Change.result == "success")).scalar_one() == 6
        assert s.execute(select(func.count(func.distinct(Change.video_id)))).scalar_one() == 6
        applies = s.execute(select(AuditLog).where(AuditLog.action == "change.apply")).scalars().all()
        assert len(applies) == 6 and sum(1 for a in applies if a.detail.get("recovered")) == 1
        assert audit.verify_chain(s)
