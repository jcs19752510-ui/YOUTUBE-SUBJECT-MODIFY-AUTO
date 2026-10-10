"""PostgreSQL 전용 동작(137-143): 부분 고유 인덱스, 동시 반영 차단, 행 잠금, 쿼터 직렬화. YTWEB_TEST_PG_URL 이 없으면 건너뛴다."""
from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from ytweb.core.settings_store import set_web_setting
from ytweb.db.models import Base, Batch, BatchItem, Change, QuotaUsage
from ytweb.db.session import make_engine, make_session_factory
from ytweb.domain.batches import _next_due_item, apply_one, run_due_items
from ytweb.domain.limits_quota import reserve_calls
from ytweb.domain.seed import seed_demo
from ytweb.domain.common import StepFailure
from ytweb.youtube.mock import MockYouTubeGateway

from tests.domain.helpers import queued_batch

pytestmark = pytest.mark.postgres


@pytest.fixture
def pgf(pg_url):
    engine = make_engine(pg_url)
    Base.metadata.drop_all(engine)   # 이 테스트 전용 DB 안의 테이블만 만들고 지운다(DB 자체는 건드리지 않음)
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()
    cleanup = make_engine(pg_url)
    Base.metadata.drop_all(cleanup)
    cleanup.dispose()


@pytest.fixture
def pg(pgf, env, clock):
    with pgf() as s:
        seed_demo(s, clock(), env.policy, count=40)
        s.commit()
    return pgf


def _queue(pg, env, clock, n, cap=None, skip=0):
    with pg() as s:
        if cap:
            set_web_setting(s, "daily_apply_cap", cap, now=clock())
            s.commit()
        batch, sugs, _ = queued_batch(s, env, clock(), n, skip)
        ids = [i.id for i in batch.items]
        s.execute(update(BatchItem).where(BatchItem.batch_id == batch.id).values(scheduled_date=batch.items[0].scheduled_date))  # 전부 오늘 도래
        s.commit()
        return batch.id, ids


def test_tc_wb_137_partial_unique_index_one_planned_change_per_video(pg, clock):
    with pg() as s:
        for result in ("planned", "success", "failed"):
            s.add(Change(video_id="demoVid0001", change_type="apply", previous_title="a", new_title="b", result=result, mode="demo", created_at=clock()))
        s.commit()
        s.add(Change(video_id="demoVid0001", change_type="apply", previous_title="a", new_title="c", result="planned", mode="demo", created_at=clock()))
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()


def test_tc_wb_138_active_batch_item_unique_per_suggestion(pg, env, clock):
    bid, ids = _queue(pg, env, clock, 2)
    with pg() as s:
        item = s.get(BatchItem, ids[0])
        s.add(BatchItem(batch_id=bid, suggestion_id=item.suggestion_id, video_id=item.video_id, seq=99, status="pending", updated_at=clock()))
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()
        item = s.get(BatchItem, ids[0])
        item.status = "success"
        other = Batch(status="draft", created_at=clock(), updated_at=clock())
        s.add(other)
        s.flush()
        s.add(BatchItem(batch_id=other.id, suggestion_id=item.suggestion_id, video_id=item.video_id, seq=1, status="pending", updated_at=clock()))
        s.flush()  # 끝난 항목은 같은 제안의 새 항목을 막지 않는다
        s.rollback()


def test_tc_wb_139_concurrent_apply_of_same_item_applies_once(pg, env, clock):
    _, ids = _queue(pg, env, clock, 1)

    def run(_):
        with pg() as s:
            return apply_one(s, ids[0], now=clock(), env=env, gateway=MockYouTubeGateway(s, clock)).status

    with ThreadPoolExecutor(6) as ex:
        outcomes = list(ex.map(run, range(6)))
    assert sorted(outcomes) == ["not_pending"] * 5 + ["success"]
    with pg() as s:
        assert s.execute(select(func.count()).select_from(Change)).scalar_one() == 1
        assert s.execute(select(func.sum(QuotaUsage.units))).scalar_one() == 52


def test_tc_wb_140_two_workers_never_double_apply(pg, env, clock):
    bid, ids = _queue(pg, env, clock, 8, cap=20)
    with ThreadPoolExecutor(3) as ex:
        results = list(ex.map(lambda _: run_due_items(pg, clock(), env), range(3)))
    assert sum(r.success for r in results) == 8 and sum(r.failed + r.skipped for r in results) == 0
    with pg() as s:
        assert s.execute(select(func.count()).select_from(Change).where(Change.result == "success")).scalar_one() == 8
        assert s.execute(select(func.count(func.distinct(Change.video_id)))).scalar_one() == 8
        assert {i.status for i in s.execute(select(BatchItem)).scalars()} == {"success"}


def test_tc_wb_141_daily_cap_holds_under_concurrency(pg, env, clock):
    _, ids = _queue(pg, env, clock, 8, cap=3)
    with pg() as s:   # 8건 모두 오늘 도래하도록 강제(밀린 예약 상황)
        s.execute(update(BatchItem).values(scheduled_date=clock().date()))
        s.commit()
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda _: run_due_items(pg, clock(), env), range(4)))
    with pg() as s:
        assert s.execute(select(func.count()).select_from(Change).where(Change.result.in_(("success", "planned")))).scalar_one() == 3
        assert s.execute(select(func.count()).select_from(BatchItem).where(BatchItem.status == "success")).scalar_one() == 3
    assert sum(r.success for r in results) == 3


def test_tc_wb_142_skip_locked_hands_out_different_items(pg, env, clock):
    _, ids = _queue(pg, env, clock, 3)
    today = clock().date()
    a, b = pg(), pg()
    try:
        first = _next_due_item(a, today, None)
        second = _next_due_item(b, today, None)   # 첫 세션이 행을 잠근 채라도 기다리지 않고 다음 행을 받는다
        assert first is not None and second is not None and first.id != second.id
    finally:
        a.rollback(); b.rollback(); a.close(); b.close()


def test_tc_wb_143_quota_reservation_is_serialized(pg, env, clock):
    tight = dataclasses.replace(env.policy, daily_limit_units=520)    # 52단위 반영 10건분

    def reserve(_):
        with pg() as s:
            try:
                reserve_calls(s, clock(), tight, [("videos.list", 1), ("videos.update", 50), ("videos.list", 1)])
                s.commit()
                return True
            except StepFailure:
                s.rollback()
                return False

    with ThreadPoolExecutor(8) as ex:
        got = list(ex.map(reserve, range(16)))
    assert sum(got) == 10
    with pg() as s:
        assert s.execute(select(func.sum(QuotaUsage.units))).scalar_one() == 520
