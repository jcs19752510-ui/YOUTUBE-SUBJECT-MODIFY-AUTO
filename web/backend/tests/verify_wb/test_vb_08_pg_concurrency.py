"""6단계 독립 검증 8: 실제 PostgreSQL 16 에서의 동시성 실측(S-W12). YTWEB_TEST_PG_URL(전용 DB ytweb_test_b)이 없으면 건너뛴다(PASS 로 세지 않음).

두 워커 틱 동시 실행에서 일일 상한 초과·이중 반영이 없고, 쿼터가 초과 예약되지 않으며, 감사 해시 체인이 갈라지지 않음을 확인한다.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, text, update

from ytweb.core import audit
from ytweb.core.errors import ProblemError
from ytweb.core.settings_store import set_web_setting
from ytweb.db.models import Approval, AuditLog, Base, Batch, BatchItem, Change, Job, QuotaUsage
from ytweb.db.session import make_engine, make_session_factory
from ytweb.domain.batches import _APPLY_LOCK_KEY, apply_one, cancel_batch, create_draft, execute_batch, run_due_items
from ytweb.domain.changes import rollback_change
from ytweb.domain.limits_quota import _QUOTA_LOCK_KEY, applied_today
from ytweb.domain.seed import seed_demo
from ytweb.domain.suggestions import approve
from ytweb.youtube.mock import MockYouTubeGateway

from tests.verify_wb.vbh import fill_quota, life_ids, make_sug, ok_sug

pytestmark = pytest.mark.postgres


@pytest.fixture
def pgf(pg_url):
    engine = make_engine(pg_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()
    cleanup = make_engine(pg_url)
    Base.metadata.drop_all(cleanup)
    cleanup.dispose()


@pytest.fixture
def pg(pgf, env, clock):
    with pgf() as s:
        seed_demo(s, clock(), env.policy, count=120)
        s.commit()
    return pgf


def _make_queue(pg, env, clock, n, *, cap=None, skip=0, due_today=True):
    with pg() as s:
        if cap is not None:
            set_web_setting(s, "daily_apply_cap", cap, now=clock())
            s.commit()
        sugs = [ok_sug(s, env, clock(), v) for v in life_ids(s, n, skip)]
        b, pre = create_draft(s, [x.id for x in sugs], None, now=clock(), env=env)
        b, _ = execute_batch(s, b.id, pre["confirm_text"], now=clock(), env=env)
        if due_today:
            s.execute(update(BatchItem).where(BatchItem.batch_id == b.id).values(scheduled_date=clock().date()))
        s.commit()
        return b.id, [i.id for i in b.items], [x.id for x in sugs]


def _race(fns):
    barrier = threading.Barrier(len(fns))
    out = [None] * len(fns)

    def run(i):
        barrier.wait()
        try:
            out[i] = fns[i]()
        except BaseException as exc:  # noqa: BLE001 - 결과로 돌려 판정한다
            out[i] = exc

    with ThreadPoolExecutor(max_workers=len(fns)) as ex:
        list(ex.map(run, range(len(fns))))
    return out


def _count(pg, model, *conds):
    with pg() as s:
        return s.execute(select(func.count()).select_from(model).where(*conds)).scalar_one()


def _apply_in_thread(pg, env, clock, item_id):
    def go():
        with pg() as s:
            return apply_one(s, item_id, now=clock(), env=env, gateway=MockYouTubeGateway(s, clock))
    return go


def test_tc_vb_250_same_item_six_threads_exactly_one_apply(pg, env, clock):
    bid, items, _ = _make_queue(pg, env, clock, 1)
    res = _race([_apply_in_thread(pg, env, clock, items[0]) for _ in range(6)])
    assert all(not isinstance(r, BaseException) for r in res), res
    assert sorted(r.status for r in res) == ["not_pending"] * 5 + ["success"]
    assert _count(pg, Change) == 1 and _count(pg, Change, Change.result == "success") == 1
    with pg() as s:
        assert s.execute(select(func.sum(QuotaUsage.units))).scalar_one() == 52


@pytest.mark.parametrize("round_no", range(3))
def test_tc_vb_251_four_concurrent_ticks_never_exceed_daily_cap_3(pg, env, clock, round_no):
    """두 워커 틱(여기서는 4개) 동시 실행: 항목 10건이 오늘 도래해도 일일 상한 3건을 넘기지 않는다."""
    bid, items, _ = _make_queue(pg, env, clock, 10, cap=3)
    res = _race([lambda: run_due_items(pg, clock(), env) for _ in range(4)])
    assert all(not isinstance(r, BaseException) for r in res), res
    assert sum(r.success for r in res) == 3
    assert _count(pg, Change, Change.result == "success") == 3 and _count(pg, Change, Change.result == "planned") == 0
    with pg() as s:
        assert applied_today(s, clock()) == 3
        statuses = [i.status for i in s.get(Batch, bid).items]
    assert statuses.count("success") == 3 and statuses.count("running") == 0
    # DEF-VB-01 수정 후: 경쟁에서 밀린 항목은 skipped 가 아니라 pending(다음 날 이월)으로 남는다
    assert statuses.count("pending") == 7 and statuses.count("skipped") == 0


def test_tc_vb_251b_skip_locked_lets_second_session_take_a_different_due_item(pg, env, clock):
    """FOR UPDATE SKIP LOCKED: 첫 세션이 잡고 있는 항목을 기다리지 않고 다른 항목을 받는다(잠금 대기 2초 제한으로 대기를 오류로 드러냄)."""
    from ytweb.domain.batches import _next_due_item
    _make_queue(pg, env, clock, 3, cap=10)
    today = clock().date()
    with pg() as s1, pg() as s2:
        first = _next_due_item(s1, today, None)
        s2.execute(text("SET lock_timeout = '2s'"))
        second = _next_due_item(s2, today, None)
        assert first is not None and second is not None and first.id != second.id


def test_tc_vb_252_concurrent_ticks_cap_5_two_batches(pg, env, clock):
    _make_queue(pg, env, clock, 6, cap=5)
    _make_queue(pg, env, clock, 6, cap=5, skip=6)
    res = _race([lambda: run_due_items(pg, clock(), env) for _ in range(3)])
    assert all(not isinstance(r, BaseException) for r in res), res
    assert _count(pg, Change, Change.result == "success") == 5
    with pg() as s:
        videos = s.execute(select(Change.video_id)).scalars().all()
    assert len(videos) == len(set(videos))            # 같은 영상 이중 반영 없음


def test_tc_vb_253_two_suggestions_same_video_concurrent_only_one_applies(pg, env, clock):
    with pg() as s:
        vid = life_ids(s, 1)[0]
        s1 = make_sug(s, env, clock(), vid)
        s2 = make_sug(s, env, clock(), vid, "냉장고 정리 쉽게 따라 하는 순서 천천히 알려드립니다 둘")
        for x in (s1, s2):
            approve(s, x.id, "검수자", now=clock(), env=env)
        batches = []
        for x in (s1, s2):
            b, pre = create_draft(s, [x.id], None, now=clock(), env=env)
            b, _ = execute_batch(s, b.id, pre["confirm_text"], now=clock(), env=env)
            batches.append(b.items[0].id)
        s.commit()
    res = _race([_apply_in_thread(pg, env, clock, i) for i in batches])
    assert all(not isinstance(r, BaseException) for r in res), res
    assert sorted(r.status for r in res) == ["skipped", "success"]
    assert _count(pg, Change, Change.video_id == vid) == 1


def test_tc_vb_254_quota_reservation_race_never_over_reserves(pg, env, clock):
    """동시 반영 8건, 잔여 쿼터는 3건 분량+10: 정확히 3건만 성공, 나머지는 호출 없이 quota_exhausted."""
    bid, items, _ = _make_queue(pg, env, clock, 8, cap=20)
    with pg() as s:
        fill_quota(s, clock(), env.policy.daily_limit_units - 52 * 3 - 10)
    res = _race([_apply_in_thread(pg, env, clock, i) for i in items])
    assert all(not isinstance(r, BaseException) for r in res), res
    ok = [r for r in res if r.status == "success"]
    skipped = [r for r in res if r.status == "skipped"]
    assert len(ok) == 3 and len(skipped) == 5 and {r.code for r in skipped} == {"quota_exhausted"}
    with pg() as s:
        used = s.execute(select(func.sum(QuotaUsage.units))).scalar_one()
    assert used == env.policy.daily_limit_units - 10 and used <= env.policy.daily_limit_units


def test_tc_vb_255_execute_batch_concurrent_only_one_wins(pg, env, clock):
    with pg() as s:
        sugs = [ok_sug(s, env, clock(), v) for v in life_ids(s, 3)]
        b, pre = create_draft(s, [x.id for x in sugs], None, now=clock(), env=env)
        s.commit()
        bid, confirm = b.id, pre["confirm_text"]

    def ex():
        with pg() as s:
            try:
                r = execute_batch(s, bid, confirm, now=clock(), env=env)
                s.commit()
                return r
            except ProblemError as e:
                s.rollback()
                return e

    res = _race([ex, ex, ex])
    oks = [r for r in res if isinstance(r, tuple)]
    errs = [r for r in res if isinstance(r, ProblemError)]
    assert len(oks) == 1 and len(errs) == 2 and {e.code for e in errs} == {"batch_not_draft"}
    assert _count(pg, Job, Job.type == "batch.execute") == 1


def test_tc_vb_256_double_approve_concurrent_single_approval_row(pg, env, clock):
    with pg() as s:
        sg = make_sug(s, env, clock(), life_ids(s, 1)[0])
        s.commit()
        sid = sg.id

    def ap(name):
        def go():
            with pg() as s:
                try:
                    approve(s, sid, name, now=clock(), env=env)
                    s.commit()
                    return "ok"
                except ProblemError as e:
                    s.rollback()
                    return e.code
        return go

    res = _race([ap("가"), ap("나"), ap("다")])
    assert sorted(res) == ["ok", "suggestion_state", "suggestion_state"]
    assert _count(pg, Approval, Approval.suggestion_id == sid) == 1


def test_tc_vb_257_concurrent_rollback_only_one(pg, env, clock):
    bid, items, _ = _make_queue(pg, env, clock, 1)
    with pg() as s:
        out = apply_one(s, items[0], now=clock(), env=env, gateway=MockYouTubeGateway(s, clock))
        cid = out.change_id
        vid = s.get(Change, cid).video_id

    def rb():
        with pg() as s:
            try:
                rollback_change(s, cid, vid, "담당", now=clock(), env=env, gateway=MockYouTubeGateway(s, clock))
                s.commit()
                return "ok"
            except ProblemError as e:
                s.rollback()
                return e.code

    res = _race([rb, rb, rb])
    assert res.count("ok") == 1 and all(r in ("later_change_exists", "pending_change_exists", "already_restored") for r in res if r != "ok"), res
    assert _count(pg, Change, Change.change_type == "rollback") == 1


@pytest.mark.parametrize("round_no", range(3))
def test_tc_vb_258_cancel_vs_tick_race_leaves_consistent_state(pg, env, clock, round_no):
    """취소와 워커 틱이 동시에: 어떤 순서든 이중 반영 없음, running/planned 잔여 없음, 항목 상태와 변경 기록이 일치."""
    bid, items, sugs = _make_queue(pg, env, clock, 6, cap=20)

    def cancel():
        with pg() as s:
            cancel_batch(s, bid, now=clock(), env=env)
            s.commit()
            return "cancelled"

    res = _race([lambda: run_due_items(pg, clock(), env), cancel])
    assert not isinstance(res[0], BaseException), res
    with pg() as s:
        b = s.get(Batch, bid)
        succ_changes = {c.video_id for c in s.execute(select(Change).where(Change.result == "success")).scalars()}
        planned = s.execute(select(func.count()).select_from(Change).where(Change.result == "planned")).scalar_one()
        by_video = {}
        for it in b.items:
            by_video.setdefault(it.status, []).append(it)
    assert planned == 0 and "running" not in by_video
    for it in by_video.get("success", []):
        assert it.video_id in succ_changes
    cancelled_with_change = [it for it in by_video.get("cancelled", []) if it.video_id in succ_changes]
    assert cancelled_with_change == [], "취소로 표시된 항목이 실제로는 반영됨(상태 불일치)"
    assert len(succ_changes) == len(by_video.get("success", []))


def test_tc_vb_259_audit_chain_intact_after_concurrent_ticks(pg, env, clock):
    _make_queue(pg, env, clock, 8, cap=8)
    res = _race([lambda: run_due_items(pg, clock(), env) for _ in range(4)])
    assert all(not isinstance(r, BaseException) for r in res), res
    with pg() as s:
        assert audit.verify_chain(s) is True
        n_apply = s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "change.apply")).scalar_one()
    assert n_apply == 8


def test_tc_vb_260_pg_constraints_exist_and_enforce(pg, env, clock):
    with pg() as s:
        names = {r[0] for r in s.execute(text("select indexname from pg_indexes where schemaname='public'"))}
    assert {"uq_changes_planned_per_video", "uq_batch_items_active_suggestion"} <= names
    from sqlalchemy.exc import IntegrityError
    with pg() as s:
        vid = life_ids(s, 1)[0]
        for _ in range(2):
            s.add(Change(video_id=vid, change_type="apply", previous_title="a", new_title="b", result="planned", mode="demo", created_at=clock()))
        with pytest.raises(IntegrityError):
            s.flush()


def test_tc_vb_261_apply_lock_actually_serializes_critical_section(pg, env, clock):
    """advisory lock(7340003)을 다른 연결이 쥐고 있으면 반영이 기다린다(잠금이 실제로 임계 구간을 직렬화). 풀리면 진행."""
    bid, items, _ = _make_queue(pg, env, clock, 1)
    holder = pg()
    holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _APPLY_LOCK_KEY})
    done = {}

    def run():
        with pg() as s:
            done["r"] = apply_one(s, items[0], now=clock(), env=env, gateway=MockYouTubeGateway(s, clock))

    t = threading.Thread(target=run)
    t.start()
    time.sleep(1.5)
    assert t.is_alive() and "r" not in done           # 잠금 때문에 대기 중
    holder.rollback()
    holder.close()
    t.join(timeout=20)
    assert not t.is_alive() and done["r"].status == "success"


def test_tc_vb_262_quota_lock_serializes_reservation(pg, env, clock):
    from ytweb.domain.limits_quota import reserve_calls
    holder = pg()
    holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _QUOTA_LOCK_KEY})
    done = {}

    def run():
        with pg() as s:
            reserve_calls(s, clock(), env.policy, [("videos.list", 1)])
            s.commit()
            done["ok"] = True

    t = threading.Thread(target=run)
    t.start()
    time.sleep(1.2)
    assert t.is_alive() and not done
    holder.rollback()
    holder.close()
    t.join(timeout=20)
    assert done.get("ok") is True


def test_tc_vb_263_idempotent_batch_create_concurrent_same_key_single_batch(pg, env, clock):
    from ytweb.domain.deps import idempotent
    with pg() as s:
        sugs = [ok_sug(s, env, clock(), v) for v in life_ids(s, 2)]
        s.commit()
        ids = [x.id for x in sugs]

    def create():
        with pg() as s:
            try:
                st, payload = idempotent(s, key="same-key-12345", route="POST /api/v1/batches", request={"suggestion_ids": ids, "note": None}, now=clock(),
                                         handler=lambda: (201, {"id": create_draft(s, ids, None, now=clock(), env=env)[0].id}))
                s.commit()
                return st
            except ProblemError as e:
                s.rollback()
                return e.code

    res = _race([create, create, create])
    assert res.count(201) >= 1
    assert all(r in (201, "idempotency_in_progress", "already_in_batch", "batch_empty") for r in res), res
    assert _count(pg, Batch) == 1
