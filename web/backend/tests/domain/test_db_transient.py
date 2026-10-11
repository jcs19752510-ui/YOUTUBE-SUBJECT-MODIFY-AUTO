"""DEF-8-001 조치 시험(TC-M3-050~): DB 연결이 잠깐 끊겨도(planned 기록 전) 항목은 실패가 아니라 대기로 돌아가 다음 틱에 반영된다."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from tests.domain.helpers import queued_batch
from ytweb.db.models import BatchItem, Change
from ytweb.domain.batches import apply_one, run_due_items
from ytweb.youtube.mock import MockYouTubeGateway


class FlakyGateway(MockYouTubeGateway):
    """처음 read_snippet 에서 DB 연결 끊김(OperationalError)을 흉내 낸다."""

    def __init__(self, *a, fail_times=1, **kw):
        super().__init__(*a, **kw)
        self.fail_times = fail_times

    def read_snippet(self, video_id):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))
        return super().read_snippet(video_id)


def test_tc_m3_050_transient_db_error_before_planned_returns_item_to_pending(seeded, env, clock):
    batch, _, _ = queued_batch(seeded, env, clock(), 1)
    item = seeded.execute(select(BatchItem).where(BatchItem.batch_id == batch.id)).scalars().one()
    out = apply_one(seeded, item.id, now=clock(), env=env, gateway=FlakyGateway(seeded, clock=clock))
    assert (out.status, out.code) == ("deferred", "db_unavailable")
    seeded.expire_all()
    assert seeded.get(BatchItem, item.id).status == "pending" and seeded.query(Change).count() == 0  # 쓰기 전이므로 기록·이중 반영 없음
    out2 = apply_one(seeded, item.id, now=clock(), env=env, gateway=MockYouTubeGateway(seeded, clock=clock))  # 다음 틱: 정상 처리
    assert out2.status == "success" and seeded.query(Change).count() == 1


def test_tc_m3_051_tick_stops_on_db_unavailable_and_next_tick_finishes(seeded, env, clock, engine):
    from sqlalchemy.orm import sessionmaker
    batch, _, _ = queued_batch(seeded, env, clock(), 3)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    flaky = {"n": 1}

    def gf(session, now):
        return FlakyGateway(session, clock=lambda: now, fail_times=flaky.pop("n", 0))

    r1 = run_due_items(factory, clock(), env, gateway_factory=gf)
    assert r1.stopped_by == "db_unavailable" and r1.success == 0
    r2 = run_due_items(factory, clock(), env, gateway_factory=gf)
    assert r2.success == 3 and r2.failed == 0
