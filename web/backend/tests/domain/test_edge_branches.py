"""경계·방어 분기(145-158): 사전 점검 경고, 승인 후 상태 변경, 롤백 방어, 기본 Env."""
from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest
from sqlalchemy import select

from ytweb.core.errors import ProblemError
from ytweb.core.settings_store import set_web_setting
from ytweb.db.models import Batch, BatchItem, Change, Suggestion, Video
from ytweb.domain import common
from ytweb.domain.batches import apply_one, create_draft, execute_batch, recover_running_items, verify_snippet
from ytweb.domain.changes import rollback_change
from ytweb.domain.limits_quota import reserve_calls
from ytweb.domain.suggestions import approve, edit_title, release_after_item

from tests.domain.helpers import FaultyGateway, approved, approved_many, eligible_video_ids, queued_batch, suggest


def _problem(fn, *a, **kw) -> ProblemError:
    with pytest.raises(ProblemError) as e:
        fn(*a, **kw)
    return e.value


def test_tc_wb_145_precheck_warnings(seeded, env, clock, gw):
    set_web_setting(seeded, "daily_apply_cap", 1, now=clock())
    first, sugs0, _ = queued_batch(seeded, env, clock(), 1)
    apply_one(seeded, first.items[0].id, now=clock(), env=env, gateway=gw)          # 오늘 상한(1건) 소진
    sugs = approved_many(seeded, env, clock(), 2, skip=1)
    _, pre = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=env)
    assert any("이미 도달" in w for w in pre["warnings"]) and pre["schedule"][0]["date"] == "2026-10-11"
    tight = dataclasses.replace(env, policy=dataclasses.replace(env.policy, daily_limit_units=60))
    set_web_setting(seeded, "daily_apply_cap", 5, now=clock())
    more = approved_many(seeded, env, clock(), 2, skip=3)
    _, pre2 = create_draft(seeded, [s.id for s in more], None, now=clock(), env=tight)
    assert any("남은 쿼터" in w for w in pre2["warnings"])
    warn_env = dataclasses.replace(env, policy=dataclasses.replace(env.policy, daily_limit_units=1000, warn_ratio=0.05))
    one = approved_many(seeded, env, clock(), 1, skip=5)
    _, pre3 = create_draft(seeded, [one[0].id], None, now=clock(), env=warn_env)
    assert any("경고 비율" in w for w in pre3["warnings"])


def test_tc_wb_146_precheck_flags_warn_results(seeded, env, clock):
    for vid in eligible_video_ids(seeded, 30):
        sugs = suggest(seeded, env, clock(), vid, 5)
        warn = next((s for s in sugs if s.validation_result == "warn"), None)
        if warn:
            approve(seeded, warn.id, "홍길동", now=clock(), env=env)
            _, pre = create_draft(seeded, [warn.id], None, now=clock(), env=env)
            assert any("경고 판정" in w for w in pre["warnings"])
            return
    pytest.fail("경고 판정 제안을 찾지 못함")


def test_tc_wb_147_limit_failure_blocks_precheck(seeded, env_free, clock):
    sug = approved(seeded, env_free, clock(), eligible_video_ids(seeded, 1)[0])
    seeded.add(Change(video_id=sug.video_id, change_type="apply", previous_title="a", new_title="b", result="success", mode="demo", applied_at=clock() - timedelta(hours=2), created_at=clock()))
    seeded.flush()
    e = _problem(create_draft, seeded, [sug.id], None, now=clock(), env=env_free)
    assert e.code == "batch_empty" and "72시간" in e.detail


def test_tc_wb_148_apply_rechecks_state_after_queue(seeded, env, clock, gw):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 3)
    sugs[0].status = "approved"                     # 대기열 상태가 아닌 제안
    sugs[1].strict_mode, sugs[1].validation_result = False, "block"   # 대기 중에 차단 판정으로 바뀜
    seeded.commit()
    assert apply_one(seeded, batch.items[0].id, now=clock(), env=env, gateway=gw).code == "suggestion_state"
    assert apply_one(seeded, batch.items[1].id, now=clock(), env=env, gateway=gw).code == "suggestion_blocked"
    seeded.get(Suggestion, sugs[2].id).title = sugs[2].title + "<"      # 쓰기 직전 규격 점검(마지막 방어선)
    seeded.commit()
    assert apply_one(seeded, batch.items[2].id, now=clock(), env=env, gateway=gw).code in ("plan_mismatch", "title_invalid")


def test_tc_wb_149_same_title_and_missing_video_at_apply(seeded, env, clock, gw):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 1)
    video = seeded.get(Video, sugs[0].video_id)
    video.title = sugs[0].title
    video.snippet = {**video.snippet, "title": sugs[0].title}
    seeded.commit()
    out = apply_one(seeded, batch.items[0].id, now=clock(), env=env, gateway=gw)
    assert out.code in ("plan_mismatch", "same_as_current")
    b2, s2, _ = queued_batch(seeded, env, clock(), 1, skip=1)
    faulty = FaultyGateway(seeded, clock)
    faulty.read_override = lambda n, snap: None
    assert apply_one(seeded, b2.items[0].id, now=clock(), env=env, gateway=faulty).code == "video_not_found"
    b3, s3, _ = queued_batch(seeded, env, clock(), 1, skip=2)
    faulty3 = FaultyGateway(seeded, clock)
    faulty3.read_override = lambda n, snap: {k: v for k, v in snap.items() if k != "categoryId"}
    assert apply_one(seeded, b3.items[0].id, now=clock(), env=env, gateway=faulty3).code == "snippet_invalid"


def test_tc_wb_150_verify_reread_failure_is_reported_as_unchecked(seeded, env, clock):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 1)
    faulty = FaultyGateway(seeded, clock)
    from ytweb.youtube.base import GatewayError

    def flaky(n, snap):
        if n >= 2:
            raise GatewayError("net", "끊김")
        return snap
    faulty.read_override = flaky
    out = apply_one(seeded, batch.items[0].id, now=clock(), env=env, gateway=faulty)
    change = seeded.get(Change, out.change_id)
    assert (out.status, out.code) == ("failed", "verify_failed") and change.verify_result["checked"] is False
    assert verify_snippet({"title": "a"}, None, "b")["checked"] is False


def test_tc_wb_151_approve_inconsistent_and_same_as_current(seeded, env, clock):
    vids = eligible_video_ids(seeded, 2)
    s1 = suggest(seeded, env, clock(), vids[0])[0]
    video = seeded.get(Video, vids[0])
    video.snippet = {**video.snippet, "title": "다른 제목"}
    seeded.flush()
    assert _problem(approve, seeded, s1.id, "홍", now=clock(), env=env).code == "video_inconsistent"
    s2 = suggest(seeded, env, clock(), vids[1])[0]
    seeded.get(Video, vids[1]).title = s2.title
    seeded.get(Video, vids[1]).snippet = {**seeded.get(Video, vids[1]).snippet, "title": s2.title}
    seeded.flush()
    assert _problem(approve, seeded, s2.id, "홍", now=clock(), env=env).code in ("same_as_current", "suggestion_blocked")


def test_tc_wb_152_edit_rejects_non_string_title(seeded, env, clock):
    s = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    assert _problem(edit_title, seeded, s.id, 123, now=clock(), env=env).code == "title_invalid"


def test_tc_wb_153_release_after_item_without_video(seeded, env, clock):
    s = approved(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])
    s.status = "queued"
    release_after_item(s, None, env, clock(), clock())
    assert s.status == "expired"
    s.status = "applied"
    release_after_item(s, seeded.get(Video, s.video_id), env, clock(), clock())
    assert s.status == "applied"      # 대기열 상태가 아니면 건드리지 않는다


def test_tc_wb_154_rollback_defensive_branches(seeded, env, clock, gw):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 3)
    outs = [apply_one(seeded, i.id, now=clock(), env=env, gateway=gw) for i in batch.items]
    ch = [seeded.get(Change, o.change_id) for o in outs]
    ch[0].backup_snippet = {**ch[0].backup_snippet, "title": ch[0].previous_title + "<"}   # 복원할 제목이 규격 위반
    ch[0].previous_title = ch[0].backup_snippet["title"]
    seeded.commit()
    assert _problem(rollback_change, seeded, ch[0].id, ch[0].video_id, "홍", now=clock(), env=env, gateway=gw).code == "backup_invalid"
    faulty = FaultyGateway(seeded, clock)
    faulty.read_exc = __import__("ytweb.youtube.base", fromlist=["GatewayError"]).GatewayError("net", "x")
    e = _problem(rollback_change, seeded, ch[1].id, ch[1].video_id, "홍", now=clock(), env=env, gateway=faulty)
    assert (e.status, e.code) == (502, "gateway_error")
    seeded.rollback()
    gone = FaultyGateway(seeded, clock)
    gone.read_override = lambda n, snap: None
    assert _problem(rollback_change, seeded, ch[1].id, ch[1].video_id, "홍", now=clock(), env=env, gateway=gone).status == 404
    seeded.rollback()
    seeded.add(Change(video_id=ch[2].video_id, change_type="rollback", previous_title="a", new_title="b", result="planned", mode="demo", created_at=clock() - timedelta(days=9)))
    seeded.commit()
    # id 가 더 큰 진행 중 변경이 있으므로 later_change_exists 가 먼저 막는다
    assert _problem(rollback_change, seeded, ch[2].id, ch[2].video_id, "홍", now=clock(), env=env, gateway=gw).code == "later_change_exists"


def test_tc_wb_155_recover_batch_goes_back_to_queued(seeded, factory, env, clock):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 1)
    item = batch.items[0]
    item.status, item.updated_at = "running", clock()
    seeded.get(Batch, batch.id).status = "running"
    seeded.commit()
    assert recover_running_items(factory, clock() + timedelta(minutes=30), env) == 1
    seeded.expire_all()
    assert seeded.get(Batch, batch.id).status == "queued" and seeded.get(BatchItem, item.id).status == "pending"


def test_tc_wb_156_recover_item_whose_change_already_finished(seeded, factory, env, clock, gw):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 2)
    outs = [apply_one(seeded, i.id, now=clock(), env=env, gateway=gw) for i in batch.items]
    for item in batch.items:
        item.status, item.updated_at = "running", clock()     # 기록은 끝났는데 항목 상태만 못 바꾸고 끊김
    seeded.get(Change, outs[1].change_id).error_code = "verify_failed"
    seeded.commit()
    assert recover_running_items(factory, clock() + timedelta(minutes=30), env) == 2
    seeded.expire_all()
    assert [i.status for i in seeded.get(Batch, batch.id).items] == ["success", "failed"]


def test_tc_wb_157_default_env_builds_once_and_dictionary_cache(env, web_settings, monkeypatch):
    monkeypatch.setenv("YTWEB_DATABASE_URL", "sqlite://")
    monkeypatch.setenv("YTWEB_BASE_DIR", str(env.policy.base_dir))
    monkeypatch.setenv("YTWEB_SECRETS_DIR", str(env.secrets_dir))
    common.set_default_env(None)
    first = common.default_env()
    assert first is common.default_env() and first.policy.hard_max_chars == 100 and first.dictionary.version
    assert common.load_dictionary_cached(env.policy.config_dir / "banned_terms.yaml") is common.load_dictionary_cached(env.policy.config_dir / "banned_terms.yaml")
    with pytest.raises(Exception):
        common.load_dictionary_cached(env.policy.config_dir / "없는파일.yaml")


def test_tc_wb_158_batch_item_lookup_edge_in_serializer(seeded, env, clock):
    from ytweb.domain.serialize import batch_dict
    batch, sugs, _ = queued_batch(seeded, env, clock(), 1)
    out = batch_dict(seeded, batch)
    assert out["items"][0]["previous_title"] and out["items"][0]["new_title"] == sugs[0].title
    assert batch_dict(seeded, batch, with_items=False)["items"] == []


def test_tc_wb_159_batch_status_running_only_while_an_item_is_running(seeded, env, clock, gw):
    from ytweb.domain.batches import refresh_batch_status
    batch, sugs, _ = queued_batch(seeded, env, clock(), 2)
    apply_one(seeded, batch.items[0].id, now=clock(), env=env, gateway=gw)
    assert seeded.get(Batch, batch.id).status == "queued"          # 하나 끝났고 하나 대기: queued
    batch.items[1].status = "running"
    refresh_batch_status(batch, clock())
    assert batch.status == "running"
    batch.items[1].status = "success"
    refresh_batch_status(batch, clock())
    assert batch.status == "done"
