"""TC-VFB-050~: 복구 반영의 감사 기록(DEF-7B-002) — 정상 경로와 같은 필드가 남는지, 반영되지 않은 경우엔 남지 않는지."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from ytweb.core import audit
from ytweb.db.models import AuditLog, BatchItem, Change, Suggestion, Video
from ytweb.domain.batches import apply_one, create_draft, execute_batch, recover_running_items, run_due_items
from ytweb.domain.common import default_env, set_default_env

from tests.verify_fix_be.conftest import life_ids
from tests.verify_wb.vbh import Faulty, ok_sug


class Crash(BaseException):
    """프로세스 사망 흉내(except Exception 으로 잡히지 않는다)."""


def _queue(db, env, clock, n=1):
    sugs = [ok_sug(db, env, clock(), v) for v in life_ids(db, n)]
    b, pre = create_draft(db, [s.id for s in sugs], None, now=clock(), env=env)
    b, _ = execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
    db.commit()
    return b, sugs


def _crash(db, env, clock, item_id, at):
    g = Faulty(db, clock)
    if at == "update_before":
        g.on_update = lambda n, body: (_ for _ in ()).throw(Crash())
    elif at == "update_after":
        orig = g.update_snippet

        def upd(vid, body):
            orig(vid, body)
            db.commit()
            raise Crash()

        g.update_snippet = upd   # type: ignore[method-assign]
    with pytest.raises(Crash):
        apply_one(db, item_id, now=clock(), env=env, gateway=g)
    db.rollback()


def _audits(db, action):
    db.expire_all()
    return list(db.execute(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)).scalars())


def test_tc_vfb_050_original_repro_recovered_success_has_change_apply_audit(seeded, factory, env, clock):
    """IT-323 재현: 반영 직후 사망 → 재시작 복구가 success 확정 → 감사에 변경·영상·제안 ID 가 남아야 한다."""
    b, (sug,) = _queue(seeded, env, clock)
    item_id = b.items[0].id
    _crash(seeded, env, clock, item_id, "update_after")
    assert _audits(seeded, "change.apply") == []
    assert recover_running_items(factory, clock(), env, stale_after=timedelta(0)) == 1
    change = seeded.execute(select(Change)).scalars().one()
    (rec,) = _audits(seeded, "change.apply")
    assert rec.actor == "worker" and rec.target_type == "change" and rec.target_id == str(change.id)
    assert rec.detail == {"batch_id": b.id, "video_id": sug.video_id, "suggestion_id": sug.id, "verify_ok": True, "recovered": True, "reason": "restart_recovery"}
    (rr,) = _audits(seeded, "batch.item.recovered")
    assert rr.detail == {"status": "success", "batch_id": b.id, "video_id": sug.video_id, "change_id": change.id}
    assert audit.verify_chain(seeded)


def test_tc_vfb_051_recovered_audit_is_superset_of_normal_apply_audit_fields(seeded, factory, env, clock):
    b, sugs = _queue(seeded, env, clock, 2)
    first, second = sorted(b.items, key=lambda i: i.seq)
    apply_one(seeded, first.id, now=clock(), env=env, gateway=Faulty(seeded, clock))        # 정상 경로
    _crash(seeded, env, clock, second.id, "update_after")                                      # 복구 경로
    recover_running_items(factory, clock(), env, stale_after=timedelta(0))
    normal, recovered = _audits(seeded, "change.apply")
    assert set(normal.detail) <= set(recovered.detail)
    for k in normal.detail:
        if k not in ("batch_id", "video_id", "suggestion_id", "verify_ok"):
            continue
        assert type(recovered.detail[k]) is type(normal.detail[k])
    assert recovered.detail["batch_id"] == b.id and recovered.detail["verify_ok"] is True


def test_tc_vfb_052_audit_is_unique_per_change_recovery_twice_adds_nothing(seeded, factory, env, clock):
    b, _ = _queue(seeded, env, clock)
    _crash(seeded, env, clock, b.items[0].id, "update_after")
    recover_running_items(factory, clock(), env, stale_after=timedelta(0))
    n = len(_audits(seeded, "change.apply")), len(_audits(seeded, "batch.item.recovered"))
    assert recover_running_items(factory, clock() + timedelta(hours=1), env, stale_after=timedelta(0)) == 0
    assert (len(_audits(seeded, "change.apply")), len(_audits(seeded, "batch.item.recovered"))) == n == (1, 1)


def test_tc_vfb_053_verify_failed_recovery_records_verify_ok_false(seeded, factory, env, clock):
    b, (sug,) = _queue(seeded, env, clock)
    g = Faulty(seeded, clock)
    g.on_update = lambda n, body: (_ for _ in ()).throw(Crash()) if False else body
    orig = g.update_snippet

    def upd(vid, body):
        body = {**body, "snippet": {k: v for k, v in body["snippet"].items() if k != "description"}}     # 설명 소실 → 보존 검증 실패
        orig(vid, body)
        seeded.commit()
        raise Crash()

    g.update_snippet = upd   # type: ignore[method-assign]
    with pytest.raises(Crash):
        apply_one(seeded, b.items[0].id, now=clock(), env=env, gateway=g)
    seeded.rollback()
    assert recover_running_items(factory, clock(), env, stale_after=timedelta(0)) == 1
    (rec,) = _audits(seeded, "change.apply")
    assert rec.detail["verify_ok"] is False and rec.detail["recovered"] is True
    item = seeded.get(BatchItem, b.items[0].id)
    assert item.status == "failed" and "[verify_failed]" in item.skip_reason


def test_tc_vfb_054_aborted_recovery_writes_no_change_apply_only_recovered(seeded, factory, env, clock):
    b, _ = _queue(seeded, env, clock)
    _crash(seeded, env, clock, b.items[0].id, "update_before")
    recover_running_items(factory, clock(), env, stale_after=timedelta(0))
    assert _audits(seeded, "change.apply") == []                       # 반영되지 않았으므로 '반영' 감사 금지
    (rr,) = _audits(seeded, "batch.item.recovered")
    assert rr.detail["status"] == "failed" and rr.detail["change_id"] is not None


def test_tc_vfb_055_unknown_state_recovery_writes_no_change_apply(seeded, factory, env, clock):
    b, (sug,) = _queue(seeded, env, clock)
    _crash(seeded, env, clock, b.items[0].id, "update_before")
    v = seeded.get(Video, sug.video_id)
    v.title = "누군가 다른 제목으로 바꿈"
    v.snippet = {**v.snippet, "title": v.title}
    seeded.commit()
    recover_running_items(factory, clock(), env, stale_after=timedelta(0))
    assert _audits(seeded, "change.apply") == []
    assert seeded.execute(select(Change)).scalars().one().result == "planned"


def test_tc_vfb_056_crash_before_planned_records_recovered_with_null_change_id(seeded, factory, env, clock):
    b, _ = _queue(seeded, env, clock)
    g = Faulty(seeded, clock)
    g.on_read = lambda n, snap: (_ for _ in ()).throw(Crash())
    with pytest.raises(Crash):
        apply_one(seeded, b.items[0].id, now=clock(), env=env, gateway=g)
    seeded.rollback()
    recover_running_items(factory, clock(), env, stale_after=timedelta(0))
    (rr,) = _audits(seeded, "batch.item.recovered")
    assert rr.detail == {"status": "pending", "batch_id": b.id, "video_id": seeded.get(BatchItem, b.items[0].id).video_id, "change_id": None}
    assert _audits(seeded, "change.apply") == []
    r = run_due_items(factory, clock(), env)
    assert r.success == 1 and len(_audits(seeded, "change.apply")) == 1


def test_tc_vfb_057_audit_detail_has_no_titles_or_secrets(seeded, factory, env, clock):
    """감사 상세에 제목·원문 snippet 같은 큰/민감 값이 들어가지 않는다."""
    b, (sug,) = _queue(seeded, env, clock)
    _crash(seeded, env, clock, b.items[0].id, "update_after")
    recover_running_items(factory, clock(), env, stale_after=timedelta(0))
    blob = " ".join(str(r.detail) for r in _audits(seeded, "change.apply") + _audits(seeded, "batch.item.recovered"))
    assert sug.title not in blob and "description" not in blob


def test_tc_vfb_058_recovery_does_not_apply_twice_after_success_recovery(seeded, factory, env, clock):
    b, (sug,) = _queue(seeded, env, clock)
    _crash(seeded, env, clock, b.items[0].id, "update_after")
    recover_running_items(factory, clock(), env, stale_after=timedelta(0))
    assert run_due_items(factory, clock(), env).processed == 0
    assert len(seeded.execute(select(Change)).scalars().all()) == 1
    seeded.expire_all()
    assert seeded.get(Suggestion, sug.id).status == "applied"
