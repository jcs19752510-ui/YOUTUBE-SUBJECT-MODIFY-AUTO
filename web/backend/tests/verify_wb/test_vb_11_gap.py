"""6단계 독립 검증 11: 커버리지 틈 보강 + 결함 수정(DEF-VB-01/02) 회귀."""
from __future__ import annotations

from datetime import timedelta, timezone

import pytest
from sqlalchemy import select

from ytweb.db.models import AuditLog, BatchItem, Change
from ytweb.domain import batches as B
from ytweb.domain.batches import apply_one
from ytweb.domain.changes import rollback_change
from ytweb.youtube.base import GatewayError

from tests.verify_wb.vbh import Faulty, changes, life_ids, queued, quota_units, set_cap


def test_tc_vb_300_body_not_preserving_fresh_snippet_is_refused_before_any_write(seeded, db, env, clock, monkeypatch):
    """요청 본문이 재조회한 snippet 을 전부 보존하지 않으면 body_invalid 로 쓰기 전에 중단(쓰기 0, planned 없음)."""
    b, sugs = queued(db, env, clock(), 1)
    real = B.build_update_body

    def bad(video_id, fresh, title):
        out = real(video_id, fresh, title)
        out["snippet"].pop("description", None)
        return out
    monkeypatch.setattr(B, "build_update_body", bad)
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("failed", "body_invalid") and g.updates == 0 and changes(db) == []


def test_tc_vb_301_body_wrong_title_is_refused(seeded, db, env, clock, monkeypatch):
    b, sugs = queued(db, env, clock(), 1)
    real = B.build_update_body
    monkeypatch.setattr(B, "build_update_body", lambda v, f, t: real(v, f, "다른 제목"))
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("failed", "body_invalid") and g.updates == 0


def test_tc_vb_302_rollback_verify_read_failure_is_reported_not_silent(seeded, db, env, clock):
    """롤백 갱신은 됐으나 검증 재조회가 실패 -> 롤백 변경은 success+verify_failed, 검증 불가(checked False)로 정직하게 기록."""
    b, sugs = queued(db, env, clock(), 1)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=Faulty(db, clock))
    c = db.get(Change, out.change_id)
    g = Faulty(db, clock)

    def on_read(n, snap):
        if n == 2:
            raise GatewayError("net", "끊김")
        return snap
    g.on_read = on_read
    rb = rollback_change(db, c.id, c.video_id, "담당", now=clock(), env=env, gateway=g)
    assert rb.result == "success" and rb.error_code == "verify_failed" and rb.verify_result["ok"] is False
    assert rb.verify_result["checked"] is False


def test_tc_vb_303_deferred_item_writes_audit_and_no_failure_record(seeded, db, env, clock):
    set_cap(db, clock, 1)
    b, sugs = queued(db, env, clock(), 2)
    from tests.verify_wb.vbh import set_all_due
    set_all_due(db, b.id, clock().date())
    g = Faulty(db, clock)
    apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    out = apply_one(db, b.items[1].id, now=clock(), env=env, gateway=g)
    assert out.status == "deferred"
    row = db.execute(select(AuditLog).where(AuditLog.action == "batch.item.deferred")).scalars().one()
    assert row.detail["code"] == "limit_daily"
    assert not db.execute(select(AuditLog).where(AuditLog.action == "batch.item.skipped")).scalars().all()
    assert quota_units(db) == 52 and len(changes(db)) == 1


def test_tc_vb_304_daily_plus_interval_failure_still_skips_not_defers(seeded, db, env, clock):
    """상한 초과가 유일한 사유일 때만 이월한다. 간격 위반이 함께 있으면 기존대로 skipped(limit_*)."""
    from tests.verify_wb.vbh import add_change, set_all_due
    set_cap(db, clock, 1)
    b, sugs = queued(db, env, clock(), 2)
    set_all_due(db, b.id, clock().date())
    add_change(db, sugs[1].video_id, clock() - timedelta(hours=5))
    g = Faulty(db, clock)
    apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    out = apply_one(db, b.items[1].id, now=clock(), env=env, gateway=g)
    assert out.status == "skipped" and out.code.startswith("limit_")
    assert db.get(BatchItem, b.items[1].id).status == "skipped"
