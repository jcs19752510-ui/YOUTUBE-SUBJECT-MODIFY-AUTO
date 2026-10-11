"""TC-VFB-001~: 초안 배치 버리기(DEF-7-009) — HTTP 로 원래 재현 절차(IT-601)를 다시 밟고, 안전 로직 회귀를 본다."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from ytweb.core import audit, jobs
from ytweb.db.models import AuditLog, Batch, BatchItem, Change, Job, QuotaUsage, Suggestion
from ytweb.domain import handlers
from ytweb.domain.batches import run_due_items
from ytweb.domain.common import set_default_env
from ytweb.domain.seed import seed_demo
from tests.conftest import ORIGIN
from tests.verify_fix_be.conftest import hdr
from tests.verify_fix_be.http_helpers import approved_via_api, cancel, draft, execute


@pytest.fixture
def world(api, csrf, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
    return api


def _count(factory, model):
    with factory() as s:
        return s.execute(select(func.count()).select_from(model)).scalar_one()


def test_tc_vfb_001_original_repro_draft_can_be_discarded_and_resuggestions_reusable(world, csrf, factory):
    """원래 재현(IT-601): 초안을 만든 뒤 버릴 수단이 없었고 같은 제안을 새 배치에 못 담았다 → 이제 취소 후 다시 담긴다."""
    ids = approved_via_api(world, csrf, factory, 3)
    r1 = draft(world, csrf, ids)
    assert r1.status_code == 201 and r1.json()["batch"]["status"] == "draft"
    bid = r1.json()["batch"]["id"]
    # 취소 전에는 같은 제안을 새 배치에 담으면 막히고, 사유에 초안 번호가 있다
    blocked = draft(world, csrf, ids)
    assert blocked.status_code == 422 and blocked.json()["code"] == "batch_empty"
    assert f"초안 배치 #{bid}" in blocked.json()["detail"]
    c = cancel(world, csrf, bid)
    assert c.status_code == 200, c.text
    body = c.json()
    assert body["status"] == "cancelled"
    assert [i["status"] for i in body["items"]] == ["cancelled"] * 3
    assert all(i["skip_reason"].startswith("[cancelled]") and "초안" in i["skip_reason"] for i in body["items"])
    r2 = draft(world, csrf, ids)
    assert r2.status_code == 201 and r2.json()["precheck"]["item_count"] == 3 and r2.json()["precheck"]["blocked"] == []
    assert r2.json()["batch"]["id"] != bid


def test_tc_vfb_002_cancelling_draft_has_no_side_effects_on_money_paths(world, csrf, factory):
    """취소는 작업·변경·쿼터·승인 소진에 영향이 없고 제안은 approved 로 남는다."""
    ids = approved_via_api(world, csrf, factory, 2)
    bid = draft(world, csrf, ids).json()["batch"]["id"]
    before = (_count(factory, Job), _count(factory, Change), _count(factory, QuotaUsage))
    assert cancel(world, csrf, bid).status_code == 200
    assert (_count(factory, Job), _count(factory, Change), _count(factory, QuotaUsage)) == before
    with factory() as s:
        for sid in ids:
            sug = s.get(Suggestion, sid)
            assert sug.status == "approved" and sug.approval.used_at is None


def test_tc_vfb_003_audit_records_was_draft_and_chain_stays_valid(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 2)
    bid = draft(world, csrf, ids).json()["batch"]["id"]
    cancel(world, csrf, bid)
    with factory() as s:
        (rec,) = s.execute(select(AuditLog).where(AuditLog.action == "batch.cancel")).scalars().all()
        assert rec.target_id == str(bid) and rec.detail == {"cancelled_items": 2, "was_draft": True}
        assert audit.verify_chain(s)


def test_tc_vfb_004_second_cancel_is_409_and_adds_no_audit(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 1)
    bid = draft(world, csrf, ids).json()["batch"]["id"]
    assert cancel(world, csrf, bid).status_code == 200
    n = _count(factory, AuditLog)
    r = cancel(world, csrf, bid)
    assert r.status_code == 409 and r.json()["code"] == "batch_not_cancellable"
    assert _count(factory, AuditLog) == n


def test_tc_vfb_005_cancelled_draft_cannot_be_executed_and_worker_applies_nothing(world, csrf, factory, env, clock):
    ids = approved_via_api(world, csrf, factory, 2)
    b = draft(world, csrf, ids).json()
    bid = b["batch"]["id"]
    cancel(world, csrf, bid)
    r = execute(world, csrf, bid, b["precheck"]["confirm_text"])
    assert r.status_code == 409 and r.json()["code"] == "batch_not_draft"
    assert _count(factory, Job) == 0
    res = run_due_items(factory, clock(), env)
    assert res.processed == 0 and _count(factory, Change) == 0


def test_tc_vfb_006_cancel_of_one_draft_leaves_other_draft_and_its_items_intact(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 4)
    a = draft(world, csrf, ids[:2]).json()["batch"]["id"]
    b = draft(world, csrf, ids[2:]).json()["batch"]["id"]
    cancel(world, csrf, a)
    got = world.get(f"/api/v1/batches/{b}").json()
    assert got["status"] == "draft" and [i["status"] for i in got["items"]] == ["pending", "pending"]


def test_tc_vfb_007_draft_overlap_reports_holder_and_only_free_ones_enter(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 3)
    a = draft(world, csrf, ids[:1]).json()["batch"]["id"]
    r = draft(world, csrf, ids)
    assert r.status_code == 201
    pre = r.json()["precheck"]
    assert pre["item_count"] == 2
    (blk,) = pre["blocked"]
    assert blk["suggestion_id"] == ids[0] and blk["code"] == "already_in_batch" and blk["batch_id"] == a
    assert "초안" in blk["reason"] and f"#{a}" in blk["reason"]


def test_tc_vfb_008_queued_holder_is_reported_as_not_approved_without_draft_wording(world, csrf, factory, env, clock):
    ids = approved_via_api(world, csrf, factory, 2)
    b = draft(world, csrf, ids[:1]).json()
    ex = execute(world, csrf, b["batch"]["id"], b["precheck"]["confirm_text"])
    assert ex.status_code == 202
    r = draft(world, csrf, ids)
    (blk,) = r.json()["precheck"]["blocked"]
    # 실행 확정된 배치의 제안은 queued 라 적격성 검사에서 먼저 not_approved 로 막힌다(초안 문구·batch_id 는 초안 보유자에게만 붙는다)
    assert blk["code"] == "not_approved" and "batch_id" not in blk and "초안" not in blk["reason"]


def test_tc_vfb_009_cancelling_queued_batch_still_restores_approved_and_marks_stop_not_discard(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 2)
    b = draft(world, csrf, ids).json()
    bid = b["batch"]["id"]
    assert execute(world, csrf, bid, b["precheck"]["confirm_text"]).status_code == 202
    got = cancel(world, csrf, bid).json()
    assert got["status"] == "cancelled" and all("중지" in i["skip_reason"] for i in got["items"])
    with factory() as s:
        assert [s.get(Suggestion, i).status for i in ids] == ["approved", "approved"]
        (rec,) = s.execute(select(AuditLog).where(AuditLog.action == "batch.cancel")).scalars().all()
        assert rec.detail["was_draft"] is False


def test_tc_vfb_010_running_item_survives_cancel_of_queued_batch(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 2)
    b = draft(world, csrf, ids).json()
    bid = b["batch"]["id"]
    execute(world, csrf, bid, b["precheck"]["confirm_text"])
    with factory() as s:
        it = s.execute(select(BatchItem).where(BatchItem.batch_id == bid).order_by(BatchItem.seq)).scalars().first()
        it.status = "running"
        s.commit()
    got = cancel(world, csrf, bid).json()
    assert [i["status"] for i in got["items"]] == ["running", "cancelled"]


def test_tc_vfb_011_cancel_auth_csrf_origin_and_unknown_ids(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 1)
    bid = draft(world, csrf, ids).json()["batch"]["id"]
    assert world.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": ORIGIN}).status_code == 403          # CSRF 없음
    assert world.post(f"/api/v1/batches/{bid}/cancel", headers={"X-CSRF-Token": csrf}).status_code == 403     # Origin 없음
    assert world.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": "http://evil.example", "X-CSRF-Token": csrf}).status_code == 403
    assert world.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": ORIGIN, "X-CSRF-Token": "x" * 40}).status_code == 403
    assert world.get(f"/api/v1/batches/{bid}").json()["status"] == "draft"                                       # 위 시도가 아무것도 바꾸지 못함
    assert cancel(world, csrf, 999999).status_code == 404
    world.cookies.clear()
    r = world.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert r.status_code == 401 and r.json()["code"] == "session_required"


def test_tc_vfb_012_cancelled_draft_with_expired_approval_still_cancels_cleanly(world, csrf, factory, clock):
    ids = approved_via_api(world, csrf, factory, 1)
    bid = draft(world, csrf, ids).json()["batch"]["id"]
    clock.advance(hours=25)
    c = world.post("/api/v1/auth/session", json=None, headers={"Origin": ORIGIN})   # 유휴(30분) 만료 뒤 새 세션
    assert c.status_code == 200
    token = c.json()["csrf_token"]
    r = cancel(world, token, bid)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


def test_tc_vfb_013_done_batch_cannot_be_cancelled(world, csrf, factory, env, clock):
    ids = approved_via_api(world, csrf, factory, 1)
    b = draft(world, csrf, ids).json()
    bid = b["batch"]["id"]
    execute(world, csrf, bid, b["precheck"]["confirm_text"])
    assert jobs.process_next(factory, worker_id="vfb", clock=clock)
    assert world.get(f"/api/v1/batches/{bid}").json()["status"] == "done"
    r = cancel(world, csrf, bid)
    assert r.status_code == 409 and r.json()["code"] == "batch_not_cancellable"
    assert _count(factory, Change) == 1


def test_tc_vfb_014_approval_not_consumed_by_discard_so_discarded_then_rebatched_applies_once(world, csrf, factory, env, clock):
    ids = approved_via_api(world, csrf, factory, 1)
    bid = draft(world, csrf, ids).json()["batch"]["id"]
    cancel(world, csrf, bid)
    b2 = draft(world, csrf, ids).json()
    assert execute(world, csrf, b2["batch"]["id"], b2["precheck"]["confirm_text"]).status_code == 202
    assert jobs.process_next(factory, worker_id="vfb", clock=clock)
    assert _count(factory, Change) == 1
    run_due_items(factory, clock(), env)
    assert _count(factory, Change) == 1       # 두 번째 틱에서도 이중 반영 없음
    with factory() as s:
        assert s.get(Batch, b2["batch"]["id"]).status == "done"
