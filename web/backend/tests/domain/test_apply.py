"""배치 항목 1건 반영 apply_one: 게이트·실패 격리·이중 반영 방지(063-080)."""
from __future__ import annotations

import copy
import dataclasses
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ytweb.db.models import AuditLog, Batch, BatchItem, Change, QuotaUsage, Suggestion, Video
from ytweb.domain import batches
from ytweb.domain.batches import apply_one
from ytweb.domain.changes import rollbackable_map
from ytweb.youtube.base import GatewayError

from tests.domain.helpers import FaultyGateway, queued_batch


def _setup(db, env, clock, n=1):
    batch, sugs, _ = queued_batch(db, env, clock(), n)
    return batch, sugs, [i.id for i in batch.items]


def _apply(db, env, clock, item_id, gw, **kw):
    return apply_one(db, item_id, now=kw.pop("now", clock()), env=kw.pop("env", env), gateway=gw, **kw)


def _faulty(db, clock):
    return FaultyGateway(db, clock)


def _quota(db):
    return [(q.method, q.units, q.status) for q in db.execute(select(QuotaUsage).order_by(QuotaUsage.id)).scalars()]


def test_tc_wb_063_apply_success_records_everything(seeded, env, clock, gw):
    batch, sugs, (item_id,) = _setup(seeded, env, clock)
    video = seeded.get(Video, sugs[0].video_id)
    before = copy.deepcopy(video.snippet)
    out = _apply(seeded, env, clock, item_id, gw)
    assert (out.status, out.code) == ("success", None)
    seeded.expire_all()
    video = seeded.get(Video, sugs[0].video_id)
    change = seeded.get(Change, out.change_id)
    assert video.title == sugs[0].title != before["title"]
    assert {k: v for k, v in video.snippet.items() if k not in ("title", "localized")} == {k: v for k, v in before.items() if k not in ("title", "localized")}
    assert (change.result, change.change_type, change.mode, change.previous_title, change.new_title) == ("success", "apply", "demo", before["title"], sugs[0].title)
    assert change.backup_snippet == before and change.verify_result["ok"] and change.applied_at == clock() and change.verified_at == clock() and change.error_code is None
    assert change.approver == "홍길동" and change.batch_id == batch.id and change.suggestion_id == sugs[0].id
    item = seeded.get(BatchItem, item_id)
    assert (item.status, item.change_id, item.skip_reason) == ("success", change.id, None)
    assert seeded.get(Suggestion, sugs[0].id).status == "applied" and seeded.get(Suggestion, sugs[0].id).approval.used_at == clock()
    assert seeded.get(Batch, batch.id).status == "done"
    assert _quota(seeded) == [("videos.list", 1, "ok"), ("videos.update", 50, "ok"), ("videos.list", 1, "ok")]
    assert seeded.execute(select(AuditLog).where(AuditLog.action == "change.apply")).scalar_one().detail["verify_ok"] is True


def test_tc_wb_064_double_execution_is_idempotent(seeded, env, clock, gw):
    _, _, (item_id,) = _setup(seeded, env, clock)
    first = _apply(seeded, env, clock, item_id, gw)
    second = _apply(seeded, env, clock, item_id, gw)
    assert first.status == "success" and (second.status, second.code) == ("not_pending", "not_pending") and second.change_id == first.change_id
    assert len(seeded.execute(select(Change)).scalars().all()) == 1 and len(_quota(seeded)) == 3


def test_tc_wb_065_draft_batch_items_never_apply(seeded, env, clock, gw):
    from ytweb.domain.batches import create_draft
    from tests.domain.helpers import approved
    sug = approved(seeded, env, clock(), "demoVid0001")
    batch, _ = create_draft(seeded, [sug.id], None, now=clock(), env=env)
    out = _apply(seeded, env, clock, batch.items[0].id, gw)
    assert (out.status, out.code) == ("skipped", "batch_not_active")
    assert seeded.get(Video, "demoVid0001").title != sug.title and seeded.execute(select(Change)).first() is None and batch.status == "draft"


def test_tc_wb_066_title_changed_before_write_aborts_without_side_effects(seeded, env, clock):
    _, sugs, (item_id,) = _setup(seeded, env, clock)
    gw = _faulty(seeded, clock)
    gw.read_override = lambda n, snap: {**snap, "title": "스튜디오에서 바꾼 제목"}
    out = _apply(seeded, env, clock, item_id, gw)
    assert (out.status, out.code) == ("skipped", "title_changed")
    assert gw.calls == ["read"] and seeded.execute(select(Change)).first() is None
    assert seeded.get(Video, sugs[0].video_id).title != sugs[0].title
    assert _quota(seeded) == [("videos.list", 1, "ok"), ("videos.update", 0, "failed"), ("videos.list", 0, "failed")]  # 안 쓴 예약은 환원
    assert seeded.get(Suggestion, sugs[0].id).status == "approved" and seeded.get(BatchItem, item_id).skip_reason.startswith("[title_changed]")


def test_tc_wb_067_other_field_changed_before_write(seeded, env, clock):
    _, sugs, (item_id,) = _setup(seeded, env, clock)
    gw = _faulty(seeded, clock)
    gw.read_override = lambda n, snap: {**snap, "description": "밖에서 고친 설명"}
    out = _apply(seeded, env, clock, item_id, gw)
    assert (out.status, out.code) == ("skipped", "video_changed") and gw.calls == ["read"]
    assert seeded.get(Suggestion, sugs[0].id).status == "approved"


def test_tc_wb_068_plan_mismatch_when_stored_video_changed(seeded, env, clock, gw):
    _, sugs, (item_id,) = _setup(seeded, env, clock)
    video = seeded.get(Video, sugs[0].video_id)
    video.snippet = {**video.snippet, "tags": ["바뀜"]}
    seeded.commit()
    out = _apply(seeded, env, clock, item_id, gw)
    assert (out.status, out.code) == ("skipped", "plan_mismatch") and _quota(seeded) == []
    assert seeded.get(Suggestion, sugs[0].id).status == "expired"  # 영상이 바뀌면 승인은 무효


def test_tc_wb_069_approval_valid_at_execute_time_covers_later_days(seeded, env, clock, gw):
    _, sugs, (item_id,) = _setup(seeded, env, clock)
    out = _apply(seeded, env, clock, item_id, gw, now=clock() + timedelta(hours=60))  # TTL(24h) 뒤에 도래한 예약도 실행 확정 시각 기준으로 유효
    assert out.status == "success"


def test_tc_wb_070_tampered_or_used_approval_is_skipped(seeded, env, clock, gw):
    _, sugs, (a, b) = _setup(seeded, env, clock, 2)
    sugs[0].approval.approver = "위조"
    seeded.commit()
    assert _apply(seeded, env, clock, a, gw).code == "approval_tampered"
    sugs[1].approval.used_at = clock()
    seeded.commit()
    assert _apply(seeded, env, clock, b, gw).code == "approval_used"
    assert seeded.execute(select(Change)).first() is None


def test_tc_wb_071_limit_gates(seeded, env, clock, gw):
    from ytweb.core.settings_store import set_web_setting
    _, sugs, (a, b) = _setup(seeded, env, clock, 2)
    seeded.add(Change(video_id=sugs[0].video_id, change_type="apply", previous_title="x", new_title="y", result="success", mode="demo", applied_at=clock() - timedelta(hours=1), created_at=clock() - timedelta(hours=1)))
    seeded.commit()
    out = _apply(seeded, env, clock, a, gw)
    assert (out.status, out.code) == ("skipped", "limit_interval") and "72시간" in seeded.get(BatchItem, a).skip_reason
    set_web_setting(seeded, "daily_apply_cap", 1, now=clock())
    seeded.commit()
    assert _apply(seeded, env, clock, b, gw).code == "limit_daily"  # 위 변경이 오늘 1건으로 센다
    assert seeded.execute(select(Change).where(Change.batch_id.is_not(None))).first() is None


def test_tc_wb_072_quota_exhausted_skips_without_calling(seeded, env, clock):
    _, sugs, (item_id,) = _setup(seeded, env, clock)
    tight = dataclasses.replace(env, policy=dataclasses.replace(env.policy, daily_limit_units=51))
    gw = _faulty(seeded, clock)
    out = _apply(seeded, tight, clock, item_id, gw)
    assert (out.status, out.code) == ("skipped", "quota_exhausted") and gw.calls == [] and _quota(seeded) == []
    assert seeded.get(Suggestion, sugs[0].id).status == "approved"


def test_tc_wb_073_read_failure_fails_only_this_item(seeded, env, clock):
    _, sugs, (a, b) = _setup(seeded, env, clock, 2)
    gw = _faulty(seeded, clock)
    gw.read_exc = GatewayError("network", "연결 실패")
    assert (_apply(seeded, env, clock, a, gw).status, seeded.get(BatchItem, a).skip_reason[:13]) == ("failed", "[read_failed]")
    assert _quota(seeded)[0] == ("videos.list", 1, "failed")  # 호출을 시도한 예약은 차감 유지
    assert _apply(seeded, env, clock, b, _faulty(seeded, clock)).status == "success"  # 다른 항목은 영향 없음


def test_tc_wb_074_definite_update_failure(seeded, env, clock):
    _, sugs, (item_id,) = _setup(seeded, env, clock)
    gw = _faulty(seeded, clock)
    gw.update_exc = GatewayError("quotaExceeded", "쿼터")
    out = _apply(seeded, env, clock, item_id, gw)
    change = seeded.get(Change, out.change_id)
    assert (out.status, out.code) == ("failed", "update_failed") and (change.result, change.error_code) == ("failed", "update_failed")
    assert seeded.get(Video, sugs[0].video_id).title != sugs[0].title
    assert _quota(seeded) == [("videos.list", 1, "ok"), ("videos.update", 50, "failed"), ("videos.list", 0, "failed")]
    sug = seeded.get(Suggestion, sugs[0].id)
    assert sug.status == "expired" and sug.approval.used_at is not None  # 승인은 1회용: 다시 승인받아야 한다
    assert rollbackable_map(seeded, [change])[change.id] is False


def test_tc_wb_075_indeterminate_update_confirmed_by_reread_continues(seeded, env, clock):
    _, sugs, (item_id,) = _setup(seeded, env, clock)
    gw = _faulty(seeded, clock)
    gw.apply_then_raise = GatewayError("timeout", "응답 끊김", definite=False)  # 반영은 됐는데 응답이 끊김
    out = _apply(seeded, env, clock, item_id, gw)
    assert out.status == "success" and seeded.get(Change, out.change_id).verify_result["ok"]


def test_tc_wb_076_indeterminate_unconfirmed_keeps_planned_and_blocks_video(seeded, env, clock, gw):
    _, sugs, (a,) = _setup(seeded, env, clock)
    faulty = _faulty(seeded, clock)
    faulty.update_exc = GatewayError("timeout", "응답 없음", definite=False)
    out = _apply(seeded, env, clock, a, faulty)
    change = seeded.get(Change, out.change_id)
    assert (out.status, out.code) == ("failed", "result_unknown") and change.result == "planned"
    # 같은 영상의 다음 시도는 planned 기록 때문에 막힌다(이중 반영 방지)
    other = Change(video_id=sugs[0].video_id, change_type="apply", previous_title="a", new_title="b", result="planned", mode="demo", created_at=clock())
    seeded.add(other)
    with pytest.raises(IntegrityError):
        seeded.flush()
    seeded.rollback()


def test_tc_wb_077_verify_failure_when_fields_are_lost(seeded, env, clock):
    _, sugs, (item_id,) = _setup(seeded, env, clock)
    gw = _faulty(seeded, clock)
    gw.drop_on_update = ("description", "tags")  # 유튜브가 부분 갱신으로 필드를 지우는 상황
    out = _apply(seeded, env, clock, item_id, gw)
    change = seeded.get(Change, out.change_id)
    assert (out.status, out.code) == ("failed", "verify_failed")
    assert change.result == "success" and change.error_code == "verify_failed"  # 제목은 실제로 바뀌었으므로 이력·한도에는 반영
    assert change.verify_result["preserved"]["description"] is False and change.verify_result["preserved"]["tags"] is False and change.verify_result["title_ok"]
    assert seeded.get(Suggestion, sugs[0].id).status == "applied" and rollbackable_map(seeded, [change])[change.id] is True
    assert "롤백" in seeded.get(BatchItem, item_id).skip_reason


def test_tc_wb_078_buggy_body_builder_is_caught_before_calling(seeded, env, clock, monkeypatch):
    _, sugs, (item_id,) = _setup(seeded, env, clock)
    monkeypatch.setattr(batches, "build_update_body", lambda vid, snip, title: {"id": vid, "snippet": {k: v for k, v in {**snip, "title": title}.items() if k != "description"}})
    gw = _faulty(seeded, clock)
    out = _apply(seeded, env, clock, item_id, gw)
    assert (out.status, out.code) == ("failed", "body_invalid") and gw.calls == ["read"]
    assert "description" in seeded.get(Video, sugs[0].video_id).snippet and seeded.execute(select(Change)).first() is None


def test_tc_wb_079_existing_planned_change_blocks_item(seeded, env, clock, gw):
    _, sugs, (item_id,) = _setup(seeded, env, clock)
    seeded.add(Change(video_id=sugs[0].video_id, change_type="apply", previous_title="a", new_title="b", result="planned", mode="demo", created_at=clock()))
    seeded.commit()
    out = _apply(seeded, env, clock, item_id, gw)
    assert (out.status, out.code) == ("skipped", "pending_change_exists")


def test_tc_wb_080_unexpected_error_fails_item_but_not_the_rest(seeded, env, clock, gw):
    _, sugs, (a, b) = _setup(seeded, env, clock, 2)
    boom = _faulty(seeded, clock)
    boom.update_exc = RuntimeError("boom")
    out = _apply(seeded, env, clock, a, boom)
    assert (out.status, out.code) == ("failed", "internal_error")
    assert seeded.get(Change, out.change_id).result == "planned"  # 결과를 모르므로 자동 정리하지 않는다
    assert "boom" not in (seeded.get(BatchItem, a).skip_reason or "")  # 내부 오류 문구는 노출하지 않는다
    assert _apply(seeded, env, clock, b, gw).status == "success"
