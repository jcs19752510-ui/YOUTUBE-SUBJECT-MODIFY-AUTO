"""6단계 독립 검증 10: 1차 커버리지에서 비어 있던 분기와 보존 항목별 사후 검증을 보강한다."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from ytweb.core.errors import ProblemError
from ytweb.db.models import Batch, Change, QuotaUsage
from ytweb.domain.batches import apply_one, recover_running_items, run_due_items, verify_snippet
from ytweb.domain.changes import rollback_change
from ytweb.youtube.base import GatewayError

from tests.verify_wb.vbh import Faulty, changes, queued


@pytest.mark.parametrize("field", ["description", "tags", "defaultLanguage", "defaultAudioLanguage"])
def test_tc_vb_280_each_preserved_field_loss_is_detected_after_write(seeded, db, env, clock, field):
    """사후 검증: 설명·태그·기본 언어·오디오 언어 중 하나만 사라져도 verify_failed(live_guard 13단계)."""
    b, sugs = queued(db, env, clock(), 1)
    g = Faulty(db, clock)
    g.on_update = lambda n, body: {**body, "snippet": {k: v for k, v in body["snippet"].items() if k != field}}
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("failed", "verify_failed")
    c = changes(db)[0]
    assert c.result == "success" and c.verify_result["preserved"][field] is False
    assert [k for k, v in c.verify_result["preserved"].items() if not v] == [field]


def test_tc_vb_281_title_not_reflected_after_write_is_flagged(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    g = Faulty(db, clock)
    g.after_update = lambda v: (setattr(v, "snippet", {**v.snippet, "title": "엉뚱한 제목"}), setattr(v, "title", "엉뚱한 제목"))
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert out.code == "verify_failed"
    assert changes(db)[0].verify_result["title_ok"] is False


def test_tc_vb_282_verify_snippet_pure_function_rules():
    before = {"title": "a", "description": "d", "tags": ["x"], "categoryId": "26", "defaultLanguage": "ko", "thumbnails": {"a": 1}}
    ok = verify_snippet(before, {**before, "title": "b", "localized": {"title": "b"}}, "b")
    assert ok["ok"] is True and ok["other_changed"] == []
    assert verify_snippet(before, None, "b") == {"ok": False, "checked": False, "reason": "재조회에 실패해 제목 반영과 보존을 확인하지 못함"}
    other = verify_snippet(before, {**before, "title": "b", "thumbnails": {"a": 2}}, "b")
    assert other["ok"] is True and other["other_changed"] == ["thumbnails"]          # 알림용 정보(합격 여부에는 영향 없음)
    empty_vs_missing = verify_snippet({**before, "tags": []}, {k: v for k, v in {**before, "title": "b"}.items() if k != "tags"}, "b")
    assert empty_vs_missing["ok"] is False                                           # 빈 값과 '없음'은 다르게 본다


def test_tc_vb_283_indeterminate_then_reread_fails_is_result_unknown(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    g = Faulty(db, clock)
    g.update_snippet = lambda vid, body: (_ for _ in ()).throw(GatewayError("timeout", "?", definite=False))   # type: ignore[method-assign]
    orig = g.read_snippet
    g.read_snippet = lambda vid: orig(vid) if g.reads == 0 else (_ for _ in ()).throw(GatewayError("net", "x"))   # type: ignore[method-assign]
    g.reads = 0
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("failed", "result_unknown")
    assert changes(db)[0].result == "planned"


def test_tc_vb_284_recover_running_with_finalized_change(seeded, db, factory, env, clock):
    """running 으로 남았지만 변경 기록이 이미 확정된 경우(항목 갱신 직전 종료): 변경 결과를 따른다."""
    b, sugs = queued(db, env, clock(), 3)
    c_succ = Change(video_id=sugs[0].video_id, change_type="apply", previous_title="a", new_title="b", result="success", mode="demo", created_at=clock(), applied_at=clock())
    c_fail = Change(video_id=sugs[1].video_id, change_type="apply", previous_title="a", new_title="b", result="failed", error_code="update_failed", mode="demo", created_at=clock())
    c_verify = Change(video_id=sugs[2].video_id, change_type="apply", previous_title="a", new_title="b", result="success", error_code="verify_failed", mode="demo", created_at=clock(), applied_at=clock())
    db.add_all([c_succ, c_fail, c_verify])
    db.flush()
    for it, ch in zip(b.items, (c_succ, c_fail, c_verify)):
        it.status, it.change_id = "running", ch.id
    db.commit()
    assert recover_running_items(factory, clock(), env, stale_after=timedelta(0)) == 3
    db.expire_all()
    st = [i.status for i in db.get(Batch, b.id).items]
    assert st == ["success", "failed", "failed"]
    reasons = [i.skip_reason for i in db.get(Batch, b.id).items]
    assert reasons[0] is None and "update_failed" in reasons[1] and "verify_failed" in reasons[2]


def test_tc_vb_285_tick_reports_progress_and_tags_quota_with_job_id(seeded200, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 3)
    seen = []
    res = run_due_items(factory, clock(), env, on_progress=seen.append, job_id="job-xyz", batch_id=b.id)
    assert seen == [1, 2, 3] and res.processed == 3
    assert {q.job_id for q in db.execute(select(QuotaUsage)).scalars()} == {"job-xyz"}
    assert run_due_items(factory, clock(), env, batch_id=b.id).processed == 0          # 할 일 없음


def test_tc_vb_286_tick_batch_id_filter_only_touches_that_batch(seeded200, db, factory, env, clock):
    b1, _ = queued(db, env, clock(), 2)
    b2, _ = queued(db, env, clock(), 2, skip=2)
    res = run_due_items(factory, clock(), env, batch_id=b2.id)
    assert res.success == 2
    db.expire_all()
    assert [i.status for i in db.get(Batch, b1.id).items] == ["pending", "pending"]


def test_tc_vb_287_rollback_when_video_vanished_at_reread_releases_quota(seeded, db, env, clock, gw):
    b, sugs = queued(db, env, clock(), 1)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    c = db.get(Change, out.change_id)
    g = Faulty(db, clock)
    g.on_read = lambda n, snap: None
    with pytest.raises(ProblemError) as e:
        rollback_change(db, c.id, c.video_id, "담당", now=clock(), env=env, gateway=g)
    assert (e.value.status, e.value.code) == (404, "video_not_found") and g.updates == 0
    rows = [(r.units, r.status) for r in db.execute(select(QuotaUsage).order_by(QuotaUsage.id)).scalars()][3:]
    assert rows == [(1, "ok"), (0, "failed"), (0, "failed")]          # 호출한 재조회 1단위만 남기고 나머지 해제
    assert [x for x in changes(db) if x.change_type == "rollback"] == []


def test_tc_vb_289_api_hint_and_detail_present_on_domain_errors(seeded, db, env, clock):
    """모든 도메인 오류는 한국어 hint 를 갖는다(사용자 조치 안내)."""
    from ytweb.domain.suggestions import approve, edit_title, reject
    from ytweb.domain.batches import create_draft, execute_batch, cancel_batch
    cases = [
        lambda: approve(db, 424242, "a", now=clock(), env=env),
        lambda: edit_title(db, 424242, "x", now=clock(), env=env),
        lambda: reject(db, 424242, now=clock()),
        lambda: create_draft(db, [], None, now=clock(), env=env),
        lambda: execute_batch(db, 424242, "실행 1건", now=clock(), env=env),
        lambda: cancel_batch(db, 424242, now=clock(), env=env),
    ]
    for fn in cases:
        with pytest.raises(ProblemError) as e:
            fn()
        assert e.value.hint and e.value.title
