"""TC-VFB-150~: (a) 승인자 이름 서식 문자 거부(같은 커밋의 DEF-9-004 변경) (b) PostgreSQL 에서 취소/실행 경합·이중 취소·감사 체인."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from ytweb.core import audit
from ytweb.core.errors import ProblemError
from ytweb.db.models import AuditLog, Batch, BatchItem, Change, Job, Suggestion
from ytweb.domain.batches import cancel_batch, create_draft, execute_batch
from ytweb.domain.common import clean_approver

from tests.verify_fix_be.conftest import life_ids
from tests.verify_wb.vbh import ok_sug


@pytest.mark.parametrize("name", ["홍길동", "김 철수", "O'Brien", "Anna-Marie", "検査者", "a", "가" * 40])
def test_tc_vfb_150_ordinary_names_still_accepted(name):
    assert clean_approver(name) == name


@pytest.mark.parametrize("name", [
    "홍​길동", "홍‌길동", "홍‍길동", "‎홍길동", "홍길동‮", "홍­길동", "홍﻿길동", "홍 길동", "홍 길동",
    "홍\x00길동", "홍\n길동", "홍\t길동", "홍\u0085길동", "가" * 41, "", "   ", None, 5, ["a"],
])
def test_tc_vfb_151_invisible_control_overlong_or_wrong_type_rejected(name):
    with pytest.raises(ProblemError) as e:
        clean_approver(name)
    assert e.value.status == 422 and e.value.code in ("approver_required", "approver_invalid")


def test_tc_vfb_152_name_is_stripped_and_boundary_40_vs_41():
    assert clean_approver("  홍길동  ") == "홍길동"
    assert len(clean_approver("가" * 40)) == 40
    with pytest.raises(ProblemError):
        clean_approver("가" * 41)


# ───────────── PostgreSQL 경합 ─────────────

pytestmark_pg = pytest.mark.postgres


def _draft(pg, env, clock, n=2, skip=0):
    with pg() as s:
        sugs = [ok_sug(s, env, clock(), v) for v in life_ids(s, n, skip)]
        b, pre = create_draft(s, [x.id for x in sugs], None, now=clock(), env=env)
        s.commit()
        return b.id, pre["confirm_text"], [x.id for x in sugs]


@pytestmark_pg
@pytest.mark.parametrize("round_", range(6))
def test_tc_vfb_150b_pg_cancel_vs_execute_exactly_one_wins_and_state_is_consistent(pg, env, clock, round_):
    bid, text, sids = _draft(pg, env, clock, 2, skip=round_ * 3 % 9)
    barrier = threading.Barrier(2)
    out = {}

    def do_cancel():
        with pg() as s:
            barrier.wait()
            try:
                cancel_batch(s, bid, now=clock(), env=env); s.commit(); out["cancel"] = "ok"
            except ProblemError as e:
                s.rollback(); out["cancel"] = e.code

    def do_exec():
        with pg() as s:
            barrier.wait()
            try:
                execute_batch(s, bid, text, now=clock(), env=env); s.commit(); out["exec"] = "ok"
            except ProblemError as e:
                s.rollback(); out["exec"] = e.code

    with ThreadPoolExecutor(2) as ex:
        list(ex.map(lambda f: f(), [do_cancel, do_exec]))
    with pg() as s:
        batch = s.get(Batch, bid)
        jobs_n = s.execute(select(func.count()).select_from(Job)).scalar_one()
        stat = {sid: s.get(Suggestion, sid).status for sid in sids}
        item_status = {i.status for i in batch.items}
        if out["cancel"] == "ok" and out["exec"] == "ok":
            # 직렬화되어 둘 다 성공할 수 있다(실행 → 취소): 이때 취소가 대기 항목을 풀고 작업은 남는다
            assert batch.status == "cancelled" and item_status == {"cancelled"} and set(stat.values()) == {"approved"}
        elif out["exec"] == "ok":
            assert batch.status == "queued" and jobs_n == 1 and set(stat.values()) == {"queued"}
        else:
            assert out == {"cancel": "ok", "exec": "batch_not_draft"}
            assert batch.status == "cancelled" and jobs_n == 0 and set(stat.values()) == {"approved"}
        assert audit.verify_chain(s)


@pytestmark_pg
def test_tc_vfb_151b_pg_five_concurrent_cancels_one_ok_rest_409_one_audit_row(pg, env, clock):
    bid, _, _ = _draft(pg, env, clock, 2)
    barrier = threading.Barrier(5)
    res = []

    def go():
        with pg() as s:
            barrier.wait()
            try:
                cancel_batch(s, bid, now=clock(), env=env); s.commit(); res.append("ok")
            except ProblemError as e:
                s.rollback(); res.append(e.code)

    ts = [threading.Thread(target=go) for _ in range(5)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sorted(res) == ["batch_not_cancellable"] * 4 + ["ok"]
    with pg() as s:
        assert s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "batch.cancel")).scalar_one() == 1
        assert audit.verify_chain(s)


@pytestmark_pg
def test_tc_vfb_152b_pg_two_drafts_race_for_same_suggestion_loser_gets_409_or_422_never_500(pg, env, clock):
    _, _, sids = _draft(pg, env, clock, 1)          # 첫 초안이 sid 를 이미 잡음
    with pg() as s:
        with pytest.raises(ProblemError) as e:
            create_draft(s, sids, None, now=clock(), env=env)
        assert e.value.code == "batch_empty" and f"초안 배치" in (e.value.detail or "")


@pytestmark_pg
def test_tc_vfb_153b_pg_discard_then_new_draft_same_suggestions_then_execute_applies_once(pg, env, clock):
    bid, _, sids = _draft(pg, env, clock, 2)
    with pg() as s:
        cancel_batch(s, bid, now=clock(), env=env); s.commit()
    with pg() as s:
        b2, pre = create_draft(s, sids, None, now=clock(), env=env)
        execute_batch(s, b2.id, pre["confirm_text"], now=clock(), env=env)
        s.commit()
        assert {s.get(Suggestion, i).status for i in sids} == {"queued"}
        assert s.execute(select(func.count()).select_from(BatchItem).where(BatchItem.status == "pending")).scalar_one() == 2
