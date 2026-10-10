"""6단계 독립 검증 4: 항목 1건 반영(재조회·사후 검증·실패 격리·이중 반영 방지)과 재시작 복구(W-010, 안전 정책 6-3-6)."""
from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from ytweb.core.errors import ProblemError
from ytweb.db.models import AuditLog, Batch, BatchItem, Change, QuotaUsage, Suggestion, Video
from ytweb.domain import batches as B
from ytweb.domain.batches import apply_one, recover_running_items, run_due_items
from ytweb.domain.limits_quota import applied_today
from ytweb.youtube.base import GatewayError

from tests.verify_wb.vbh import Faulty, changes, life_ids, queued, quota_units, snippet_of


def _before(db, vid):
    return copy.deepcopy(db.get(Video, vid).snippet)


def test_tc_vb_130_happy_path_records_everything(seeded, db, env, clock, gw):
    b, sugs = queued(db, env, clock(), 1)
    vid, sug = sugs[0].video_id, sugs[0]
    before = _before(db, vid)
    old_title = db.get(Video, vid).title
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    assert (out.status, out.code) == ("success", None)
    db.expire_all()
    c = changes(db, vid)[0]
    assert c.result == "success" and c.change_type == "apply" and c.mode == "demo" and c.error_code is None
    assert (c.previous_title, c.new_title) == (old_title, sug.title)
    assert c.backup_snippet == before                         # 백업은 반영 직전 재조회 snippet 전체
    assert c.approver == "검수자" and c.plan_hash == db.get(Suggestion, sug.id).plan_hash and c.approved_at is not None
    assert c.applied_at == clock() and c.verified_at == clock() and c.verify_result["ok"] is True and c.suggestion_id == sug.id and c.batch_id == b.id
    assert db.get(Video, vid).title == sug.title
    assert db.get(Suggestion, sug.id).status == "applied"
    item = db.get(BatchItem, b.items[0].id)
    assert item.status == "success" and item.change_id == c.id and item.skip_reason is None
    assert db.get(Batch, b.id).status == "done"
    assert db.execute(select(AuditLog).where(AuditLog.action == "change.apply")).scalars().one().detail["verify_ok"] is True


def test_tc_vb_131_everything_but_title_is_preserved(seeded, db, env, clock, gw):
    """안전 정책 6-3-6: snippet 전체(설명·태그·카테고리·언어·썸네일 등)는 제목 외 그대로."""
    b, sugs = queued(db, env, clock(), 1)
    vid = sugs[0].video_id
    before = _before(db, vid)
    sent = {}
    g = Faulty(db, clock)
    g.after_update = None
    orig = g.update_snippet

    def spy(video_id, body):
        sent["body"] = copy.deepcopy(body)
        return orig(video_id, body)

    g.update_snippet = spy   # type: ignore[method-assign]
    apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    after = snippet_of(db, vid)
    diff = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert diff <= {"title", "localized"}
    assert after["title"] == sugs[0].title and after["description"] == before["description"] and after["tags"] == before["tags"]
    assert after["categoryId"] == before["categoryId"] and after["defaultLanguage"] == before["defaultLanguage"]
    assert set(sent["body"]) == {"id", "snippet"} and sent["body"]["id"] == vid
    assert {k: v for k, v in sent["body"]["snippet"].items() if k not in ("title", "localized")} == {k: v for k, v in before.items() if k not in ("title", "localized")}


def test_tc_vb_132_description_lost_on_update_is_verify_failed_and_rollbackable(seeded, db, env, clock):
    """인수5: 반영 후 설명 소실 → verify_failed 로 알림. 변경은 success(제목이 실제로 바뀜)+error_code, 항목은 failed, 롤백 가능."""
    b, sugs = queued(db, env, clock(), 1)
    vid = sugs[0].video_id

    def drop_desc(n, body):
        body = copy.deepcopy(body)
        body["snippet"].pop("description", None)
        return body

    g = Faulty(db, clock)
    g.on_update = drop_desc
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("failed", "verify_failed")
    db.expire_all()
    c = changes(db, vid)[0]
    assert c.result == "success" and c.error_code == "verify_failed" and c.verify_result["ok"] is False and c.verify_result["preserved"]["description"] is False
    item = db.get(BatchItem, b.items[0].id)
    assert item.status == "failed" and item.skip_reason.startswith("[verify_failed]")
    assert db.get(Suggestion, sugs[0].id).status == "applied"
    assert applied_today(db, clock()) == 1   # 제목이 바뀌었으므로 한도에 산입
    from ytweb.domain.changes import rollbackable_map
    assert rollbackable_map(db, [c])[c.id] is True


def test_tc_vb_133_verification_read_failure_is_reported_not_silent(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 1)

    def boom(n, snap):
        if n == 2:
            raise GatewayError("net", "재조회 실패")
        return snap

    g = Faulty(db, clock)
    g.on_read = boom
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("failed", "verify_failed")
    c = changes(db)[0]
    assert c.result == "success" and c.verify_result["checked"] is False
    assert [r.status for r in db.execute(select(QuotaUsage).order_by(QuotaUsage.id)).scalars()] == ["ok", "ok", "failed"]


def test_tc_vb_134_indeterminate_update_but_applied_continues(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    g = Faulty(db, clock)
    orig = g.update_snippet

    def apply_then_raise(video_id, body):
        orig(video_id, body)
        raise GatewayError("timeout", "응답 없음", definite=False)

    g.update_snippet = apply_then_raise   # type: ignore[method-assign]
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert out.status == "success"
    assert changes(db)[0].result == "success"


def test_tc_vb_135_indeterminate_update_not_applied_keeps_planned_no_auto_cleanup(seeded, db, env, clock):
    """결과 불명: 자동 정리 없이 planned 유지(이중 반영 금지 우선), 같은 영상 후속 반영은 pending_change_exists 로 차단."""
    b, sugs = queued(db, env, clock(), 1)
    vid = sugs[0].video_id
    g = Faulty(db, clock)
    g.update_snippet = lambda video_id, body: (_ for _ in ()).throw(GatewayError("timeout", "응답 없음", definite=False))   # type: ignore[method-assign]
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("failed", "result_unknown")
    c = changes(db, vid)[0]
    assert c.result == "planned" and c.applied_at is None
    assert applied_today(db, clock()) == 1       # planned 도 한도에 산입(보수적)
    assert db.get(Video, vid).title != sugs[0].title
    # 같은 영상의 다른 제안을 새 배치로 반영 시도 → 차단
    from tests.verify_wb.vbh import make_sug, ok_sug
    from ytweb.domain.batches import create_draft, execute_batch
    s2 = make_sug(db, env, clock(), vid, "냉장고 정리 쉽게 따라 하는 순서 천천히 알려드립니다 둘")
    from ytweb.domain.suggestions import approve
    approve(db, s2.id, "검수자", now=clock(), env=env)
    with pytest.raises(ProblemError) as e2:     # 사전 점검 단계에서 이미 한도(미확정 변경이 간격/횟수에 산입)로 거부
        create_draft(db, [s2.id], None, now=clock(), env=env)
    assert e2.value.code == "batch_empty" and "72시간" in (e2.value.detail or "")
    db.commit()


def test_tc_vb_136_unexpected_exception_isolated_and_planned_preserved(seeded, db, factory, env, clock):
    """예상 밖 예외: 항목만 failed(internal_error), 변경은 planned 로 남고 내부 정보는 노출하지 않으며 틱의 다른 항목은 계속 처리."""
    b, sugs = queued(db, env, clock(), 3)
    victim = sugs[1].video_id
    from tests.verify_wb.vbh import Faulty as F

    def gwf(session, now):
        g = F(session, lambda: now)
        orig = g.update_snippet

        def upd(video_id, body):
            if video_id == victim:
                raise RuntimeError("DB password=hunter2 /srv/secret/path")
            return orig(video_id, body)

        g.update_snippet = upd   # type: ignore[method-assign]
        return g

    res = run_due_items(factory, clock(), env, gateway_factory=gwf)
    assert (res.success, res.failed) == (2, 1)
    db.expire_all()
    bad = next(i for i in db.get(Batch, b.id).items if i.video_id == victim)
    assert bad.status == "failed" and bad.skip_reason.startswith("[internal_error]") and "hunter2" not in bad.skip_reason and "/srv" not in bad.skip_reason
    c = changes(db, victim)[0]
    assert c.result == "planned"
    logs = " ".join(str(a.detail) for a in db.execute(select(AuditLog)).scalars())
    assert "hunter2" not in logs


def test_tc_vb_137_video_missing_or_snippet_invalid_at_reread(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 2)
    g = Faulty(db, clock)
    g.on_read = lambda n, snap: None
    o1 = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (o1.status, o1.code) == ("failed", "video_not_found")
    g2 = Faulty(db, clock)
    g2.on_read = lambda n, snap: {k: v for k, v in snap.items() if k != "categoryId"}
    o2 = apply_one(db, b.items[1].id, now=clock(), env=env, gateway=g2)
    assert (o2.status, o2.code) == ("failed", "snippet_invalid")
    assert g.updates == g2.updates == 0 and changes(db) == []


def test_tc_vb_138_body_guard_blocks_incomplete_request_body(seeded, db, env, clock, monkeypatch):
    """요청 본문 가드(live_guard 9단계): 본문이 재조회 snippet 을 전부 보존하지 않으면 쓰기 전에 중단."""
    b, sugs = queued(db, env, clock(), 1)
    real = B.build_update_body

    def lossy(video_id, fresh, title):
        body = real(video_id, fresh, title)
        body["snippet"].pop("tags", None)
        return body

    monkeypatch.setattr(B, "build_update_body", lossy)
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("failed", "body_invalid")
    assert g.updates == 0 and changes(db) == []
    db.expire_all()
    assert db.get(Suggestion, sugs[0].id).approval.used_at is None


def test_tc_vb_139_batch_not_active_and_suggestion_state_guards(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 2)
    db.execute(update(Batch).where(Batch.id == b.id).values(status="paused"))
    db.commit()
    g = Faulty(db, clock)
    o1 = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (o1.status, o1.code) == ("skipped", "batch_not_active")
    db.execute(update(Batch).where(Batch.id == b.id).values(status="queued"))
    sugs[1].status = "approved"       # 대기열 상태가 아닌 제안
    db.commit()
    o2 = apply_one(db, b.items[1].id, now=clock(), env=env, gateway=g)
    assert (o2.status, o2.code) == ("skipped", "suggestion_state")
    assert g.reads == g.updates == 0 and changes(db) == []


def test_tc_vb_140_existing_planned_change_blocks_apply(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    db.add(Change(video_id=sugs[0].video_id, change_type="apply", previous_title="a", new_title="b", result="planned", mode="demo", created_at=clock()))
    db.commit()
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("skipped", "pending_change_exists") and g.updates == 0


def test_tc_vb_141_same_item_cannot_be_applied_twice(seeded, db, env, clock, gw):
    b, sugs = queued(db, env, clock(), 1)
    o1 = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    o2 = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    assert o1.status == "success" and o2.status == "not_pending" and o2.change_id == o1.change_id
    assert len(changes(db)) == 1 and quota_units(db) == 52
    assert apply_one(db, 987654, now=clock(), env=env, gateway=gw).status == "not_pending"


def test_tc_vb_142_two_suggestions_same_video_only_one_applies(seeded, db, factory, env, clock):
    """영상당 이중 반영 금지: 서로 다른 제안·다른 배치로 같은 영상을 바꾸려 해도 72h 간격/횟수로 하나만 반영."""
    from tests.verify_wb.vbh import make_sug
    from ytweb.domain.batches import create_draft, execute_batch
    from ytweb.domain.suggestions import approve
    vid = life_ids(db, 1)[0]
    s1 = make_sug(db, env, clock(), vid)
    s2 = make_sug(db, env, clock(), vid, "냉장고 정리 쉽게 따라 하는 순서 천천히 알려드립니다 둘")
    for s in (s1, s2):
        approve(db, s.id, "검수자", now=clock(), env=env)
    db.commit()
    bs = []
    for s in (s1, s2):
        b, pre = create_draft(db, [s.id], None, now=clock(), env=env)
        b, _ = execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
        bs.append(b)
    db.commit()
    res = run_due_items(factory, clock(), env)
    assert (res.success, res.skipped) == (1, 1)
    assert len(changes(db, vid)) == 1
    db.expire_all()
    codes = [i.skip_reason for b in bs for i in db.get(Batch, b.id).items if i.status == "skipped"]
    assert codes and (codes[0].startswith("[limit_") or codes[0].startswith("[plan_mismatch]"))   # 어느 쪽이든 두 번째는 쓰기 없이 거부


def test_tc_vb_143_tick_isolates_failures_between_items(seeded, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 4)
    bad = sugs[1].video_id

    def gwf(session, now):
        g = Faulty(session, lambda: now)
        g.on_read = lambda n, snap: (_ for _ in ()).throw(GatewayError("net", "x")) if (n == 1 and False) else snap
        orig = g.read_snippet

        def rd(video_id):
            if video_id == bad:
                raise GatewayError("net", "일시 오류")
            return orig(video_id)

        g.read_snippet = rd   # type: ignore[method-assign]
        return g

    res = run_due_items(factory, clock(), env, gateway_factory=gwf)
    assert (res.success, res.failed, res.skipped) == (3, 1, 0)
    db.expire_all()
    st = {i.video_id: i.status for i in db.get(Batch, b.id).items}
    assert st[bad] == "failed" and list(st.values()).count("success") == 3 and db.get(Batch, b.id).status == "done"


# ───────────────────────── 재시작 복구 ─────────────────────────

class Crash(BaseException):
    """프로세스 강제 종료 흉내(except Exception 에 걸리지 않음)."""


def _crash_apply(db, env, clock, item_id, *, at):
    g = Faulty(db, clock)
    if at == "read":
        g.on_read = lambda n, snap: (_ for _ in ()).throw(Crash()) if n == 1 else snap
    elif at == "update_before":
        g.on_update = lambda n, body: (_ for _ in ()).throw(Crash())
    elif at == "update_after":
        orig = g.update_snippet

        def upd(video_id, body):
            orig(video_id, body)
            db.commit()   # 외부(유튜브) 쪽 변경은 이미 일어난 사실이므로 우리 프로세스가 죽어도 남는다
            raise Crash()

        g.update_snippet = upd   # type: ignore[method-assign]
    with pytest.raises(Crash):
        apply_one(db, item_id, now=clock(), env=env, gateway=g)
    db.rollback()   # 프로세스가 죽어 커밋되지 않은 것은 사라진다


def test_tc_vb_150_crash_before_planned_item_returns_to_pending_and_can_be_reapplied(seeded, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    _crash_apply(db, env, clock, b.items[0].id, at="read")
    db.expire_all()
    assert db.get(BatchItem, b.items[0].id).status == "running" and changes(db) == []
    assert recover_running_items(factory, clock(), env, stale_after=timedelta(0)) == 1
    db.expire_all()
    assert db.get(BatchItem, b.items[0].id).status == "pending"
    res = run_due_items(factory, clock(), env)
    assert res.success == 1 and len(changes(db)) == 1


def test_tc_vb_151_crash_after_planned_before_update_aborts_without_double_apply(seeded, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    vid = sugs[0].video_id
    title0 = db.get(Video, vid).title
    _crash_apply(db, env, clock, b.items[0].id, at="update_before")
    db.expire_all()
    c = changes(db, vid)[0]
    assert c.result == "planned" and db.get(Video, vid).title == title0
    assert db.get(Suggestion, sugs[0].id).approval.used_at is not None      # planned 와 함께 커밋된 승인 소진
    assert recover_running_items(factory, clock(), env, stale_after=timedelta(0)) == 1
    db.expire_all()
    c = changes(db, vid)[0]
    assert c.result == "aborted" and c.error_code == "interrupted"
    item = db.get(BatchItem, b.items[0].id)
    assert item.status == "failed" and "[interrupted]" in item.skip_reason
    assert db.get(Video, vid).title == title0
    assert db.get(Suggestion, sugs[0].id).status == "expired"                # 소진된 승인 → 재승인 필요(재사용 불가)
    assert applied_today(db, clock()) == 0                                   # aborted 는 한도에 산입 안 됨
    assert run_due_items(factory, clock(), env).processed == 0               # 재시작이 다시 반영하지 않음


def test_tc_vb_152_crash_after_update_before_final_is_confirmed_by_reread(seeded, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    vid = sugs[0].video_id
    _crash_apply(db, env, clock, b.items[0].id, at="update_after")
    db.expire_all()
    assert changes(db, vid)[0].result == "planned" and db.get(Video, vid).title == sugs[0].title
    assert recover_running_items(factory, clock(), env, stale_after=timedelta(0)) == 1
    db.expire_all()
    c = changes(db, vid)[0]
    assert c.result == "success" and c.verify_result["ok"] is True and "재시작" in c.verify_result["note"]
    assert db.get(BatchItem, b.items[0].id).status == "success"
    assert db.get(Suggestion, sugs[0].id).status == "applied"
    assert len(changes(db, vid)) == 1


def test_tc_vb_153_recovery_unknown_state_stays_planned_failed_item(seeded, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    vid = sugs[0].video_id
    _crash_apply(db, env, clock, b.items[0].id, at="update_before")
    v = db.get(Video, vid)
    v.title = "누군가 완전히 다른 제목으로 바꿈"
    v.snippet = {**v.snippet, "title": v.title}
    db.commit()
    assert recover_running_items(factory, clock(), env, stale_after=timedelta(0)) == 1
    db.expire_all()
    item = db.get(BatchItem, b.items[0].id)
    assert item.status == "failed" and "[result_unknown]" in item.skip_reason
    assert changes(db, vid)[0].result == "planned"                           # 사람이 확인할 때까지 유지


def test_tc_vb_154_recover_stale_threshold_boundary(seeded, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    _crash_apply(db, env, clock, b.items[0].id, at="read")
    t0 = clock()
    stale = timedelta(minutes=10)
    assert recover_running_items(factory, t0 + stale - timedelta(seconds=1), env, stale_after=stale) == 0
    assert recover_running_items(factory, t0 + stale, env, stale_after=stale) == 1


def test_tc_vb_155_tick_recovers_old_running_items_but_not_fresh_ones(seeded, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 2)
    _crash_apply(db, env, clock, b.items[0].id, at="read")
    r = run_due_items(factory, clock(), env)         # 방금 선점된 항목은 건드리지 않음(다른 워커가 처리 중일 수 있음)
    db.expire_all()
    assert db.get(BatchItem, b.items[0].id).status == "running"
    assert r.success == 1
    clock.advance(minutes=11)
    r2 = run_due_items(factory, clock(), env)
    assert r2.success == 1
    db.expire_all()
    assert all(i.status == "success" for i in db.get(Batch, b.items[0].batch_id).items)
    assert len(changes(db)) == 2


def test_tc_vb_156_recover_ignores_non_running_and_is_idempotent(seeded, db, factory, env, clock, gw):
    b, sugs = queued(db, env, clock(), 1)
    apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    assert recover_running_items(factory, clock() + timedelta(days=1), env, stale_after=timedelta(0)) == 0
    assert len(changes(db)) == 1
