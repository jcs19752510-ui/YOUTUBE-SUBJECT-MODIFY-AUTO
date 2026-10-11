"""6단계 독립 검증 12: 변이 점검 1회전에서 놓친 항목을 잡는 보강 시험(2회전 대상)."""
from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from ytweb.core.errors import ProblemError
from ytweb.db.models import Batch, BatchItem, Suggestion, Video
from ytweb.domain import reports as R
from ytweb.domain.batches import apply_one, cancel_batch, create_draft, run_due_items
from ytweb.domain.dashboard import build_dashboard
from ytweb.domain.suggestions import MAX_TITLE_CHARS, approve, edit_title, release_after_item
from ytweb.domain.videos import list_videos

from tests.verify_wb.test_vb_04_apply_recover import _crash_apply
from tests.verify_wb.vbh import Faulty, add_change, life_ids, make_sug, ok_sug, queued, set_all_due, set_cap, fill_quota


def _edit_db_snippet(db, vid, **kw):
    v = db.get(Video, vid)
    snip = copy.deepcopy(v.snippet)
    snip.update(kw)
    v.snippet = snip
    db.commit()


def test_tc_vb_310_snippet_changed_in_db_after_approval_is_plan_mismatch_at_precheck_and_apply(seeded, db, env, clock):
    """승인 뒤 저장된 영상 snippet(설명)이 바뀌면 plan_hash 재계산이 달라 승인 무효(제목은 그대로여도)."""
    vids = life_ids(db, 2)
    s1, s2 = ok_sug(db, env, clock(), vids[0]), ok_sug(db, env, clock(), vids[1])
    b, pre = create_draft(db, [s1.id], None, now=clock(), env=env)
    db.commit()
    _edit_db_snippet(db, vids[1], description="승인 뒤 바뀐 설명")
    with pytest.raises(ProblemError) as e:
        create_draft(db, [s2.id], None, now=clock(), env=env)
    assert e.value.code == "batch_empty" and "계획 해시" in e.value.detail
    # 반영 경로
    from ytweb.domain.batches import execute_batch
    execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
    db.commit()
    _edit_db_snippet(db, vids[0], description="승인 뒤 바뀐 설명 2")
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("skipped", "plan_mismatch") and g.updates == 0 and g.reads == 0


def test_tc_vb_311_approve_of_status_blocked_suggestion_is_refused_even_if_revalidation_passes(seeded, db, env, clock):
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    s.status = "blocked"
    db.commit()
    with pytest.raises(ProblemError) as e:
        approve(db, s.id, "검수자", now=clock(), env=env)
    assert (e.value.status, e.value.code) == (409, "suggestion_blocked") and "차단 판정이라 승인할 수 없습니다." in e.value.title
    assert s.approval is None


def test_tc_vb_312_apply_refuses_strict_mode_warn_state_even_if_stored_inconsistently(seeded, db, env, clock):
    """엄격 모드 + 경고(pass 아님)는 차단과 같다(is_blocking). 저장 상태가 이렇게 바뀌어 있어도 반영 직전에 거부."""
    b, sugs = queued(db, env, clock(), 1)
    db.execute(update(Suggestion).where(Suggestion.id == sugs[0].id).values(strict_mode=True, validation_result="warn"))
    db.commit()
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("skipped", "suggestion_blocked") and g.updates == 0


def test_tc_vb_313_release_after_item_ignores_non_queued_suggestions(seeded, db, env, clock):
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    for st in ("applied", "rejected", "candidate"):
        s.status = st
        release_after_item(s, db.get(Video, s.video_id), env, clock(), clock())
        assert s.status == st


def test_tc_vb_314_title_length_boundary_300_ok_301_rejected(seeded, db, env, clock):
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    t = "냉" * MAX_TITLE_CHARS
    assert edit_title(db, s.id, t, now=clock(), env=env).title == t
    with pytest.raises(ProblemError) as e:
        edit_title(db, s.id, t + "냉", now=clock(), env=env)
    assert e.value.code == "title_too_long"


def test_tc_vb_315_item_of_cancelled_batch_row_is_not_applied_even_if_item_still_pending(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    db.execute(update(Batch).where(Batch.id == b.id).values(status="cancelled"))
    db.commit()
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("skipped", "batch_not_active") and g.updates == 0


def test_tc_vb_316_tick_does_not_run_items_scheduled_for_tomorrow(seeded, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 2)
    set_all_due(db, b.id, clock().date() + timedelta(days=1))
    r = run_due_items(factory, clock(), env)
    assert r.processed == 0
    db.expire_all()
    assert all(i.status == "pending" for i in db.get(Batch, b.id).items)


def test_tc_vb_317_tick_runs_with_exactly_one_apply_of_quota_left_and_stops_with_one_less(seeded, db, factory, env, clock):
    need = env.policy.update_cost + 2 * env.policy.read_cost
    fill_quota(db, clock(), env.policy.daily_limit_units - need + 1)       # 51 남음: 1건 분량 부족
    b, sugs = queued(db, env, clock(), 1)
    r = run_due_items(factory, clock(), env)
    assert (r.processed, r.stopped_by) == (0, "quota_exhausted")
    from ytweb.db.models import QuotaUsage
    db.execute(update(QuotaUsage).values(units=env.policy.daily_limit_units - need))   # 정확히 52 남음: 처리 가능
    db.commit()
    r2 = run_due_items(factory, clock(), env)
    assert r2.success == 1


def test_tc_vb_318_default_stale_threshold_is_10_minutes_in_tick(seeded, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    _crash_apply(db, env, clock, b.items[0].id, at="read")
    clock.advance(minutes=5)
    run_due_items(factory, clock(), env)
    db.expire_all()
    assert db.get(BatchItem, b.items[0].id).status == "running"           # 5분 된 선점은 정리하지 않는다


def test_tc_vb_319_cancel_of_done_batch_is_409(seeded, db, env, clock, gw):
    b, sugs = queued(db, env, clock(), 1)
    apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    db.commit()
    assert db.get(Batch, b.id).status == "done"
    with pytest.raises(ProblemError) as e:
        cancel_batch(db, b.id, now=clock(), env=env)
    assert (e.value.status, e.value.code) == (409, "batch_not_cancellable")


def test_tc_vb_320_csv_notes_rows_are_also_formula_neutralized(seeded, db, env, clock, gw, monkeypatch):
    monkeypatch.setattr(R, "EXTRA_NOTE", "=HYPERLINK(\"http://x\")")
    text = R.export_csv(db, env, None)
    import csv, io
    cells = [c for row in csv.reader(io.StringIO(text[1:], newline="")) for c in row]
    assert "'=HYPERLINK(\"http://x\")" in cells and '=HYPERLINK("http://x")' not in cells


def test_tc_vb_321_search_is_case_insensitive_on_title_and_id(seeded, db, env, clock):
    vid = life_ids(db, 1)[0]
    db.get(Video, vid).title = "ABC Kitchen 정리"
    db.commit()
    kw = dict(now=clock(), status=None, excluded=None, sort="video_id", order="asc", page=1, page_size=200)
    assert [r["video_id"] for r in list_videos(db, q="abc kitchen", **kw)[0]] == [vid]
    assert [r["video_id"] for r in list_videos(db, q=vid.upper(), **kw)[0]] == [vid]
    assert list_videos(db, q="  ABC  ", **kw)[1] == 1


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_tc_vb_322_sort_puts_missing_values_last_in_both_directions(seeded, db, env, clock, gw, order):
    b, sugs = queued(db, env, clock(), 1)
    apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    db.commit()
    rows, total = list_videos(db, now=clock(), q=None, status=None, excluded=None, sort="last_change_at", order=order, page=1, page_size=200)
    assert rows[0]["video_id"] == sugs[0].video_id and rows[0]["last_change_at"] is not None
    assert all(r["last_change_at"] is None for r in rows[1:]) and total == len(rows)


def test_tc_vb_323_dashboard_ignores_pending_items_of_cancelled_batch(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 2)
    db.execute(update(Batch).where(Batch.id == b.id).values(status="cancelled"))
    db.commit()
    d = build_dashboard(db, clock(), env)
    assert d["queue"] == {"pending_items": 0, "next_run_date": None}


def test_tc_vb_324_mark_call_only_moves_reserved_rows_once(seeded, db, env, clock):
    from ytweb.db.models import QuotaUsage
    from ytweb.domain.limits_quota import mark_call, reserve_calls
    ids = reserve_calls(db, clock(), env.policy, [("videos.list", 1)])
    mark_call(db, ids[0], "ok")
    mark_call(db, ids[0], "failed")          # 이미 확정된 호출 기록은 바뀌지 않는다
    assert db.get(QuotaUsage, ids[0]).status == "ok"
    with pytest.raises(ValueError):
        mark_call(db, ids[0], "bogus")


def test_tc_vb_325_next_allowed_at_only_when_every_failure_has_a_retry_time(seeded, db, env, clock):
    from ytweb.domain.limits_quota import check_video_limits, summarize_limits
    vids = life_ids(db, 2)
    now = clock()
    add_change(db, vids[0], now - timedelta(hours=10))                            # 간격만 위반
    s1 = summarize_limits(check_video_limits(db, vids[0], now, env.limits_policy, 10))
    assert s1["allowed"] is False and s1["next_allowed_at"] is not None
    add_change(db, vids[1], now - timedelta(days=40))
    add_change(db, vids[1], now - timedelta(days=30))
    add_change(db, vids[1], now - timedelta(hours=10))                            # 3회 + 간격: 횟수는 풀리지 않음
    s2 = summarize_limits(check_video_limits(db, vids[1], now, env.limits_policy, 10))
    assert s2["allowed"] is False and len(s2["reasons"]) == 2 and s2["next_allowed_at"] is None


def test_tc_vb_326_workflow_status_queued_beats_approved(seeded, db, env, clock):
    from ytweb.ai.mock import MockSuggester
    from ytweb.domain.suggestions import generate_for_video
    from ytweb.domain.videos import workflow_maps
    vid = life_ids(db, 1)[0]
    a, b = generate_for_video(db, vid, count=2, tone="t", now=clock(), env=env, suggester=MockSuggester())[:2]
    a.status, b.status = "approved", "queued"
    db.commit()
    assert workflow_maps(db)[0][vid] == "queued"
    a.status, b.status = "candidate", "approved"
    db.commit()
    assert workflow_maps(db)[0][vid] == "approved"


def test_tc_vb_327_suggestion_in_running_item_cannot_join_another_batch(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    db.execute(update(BatchItem).where(BatchItem.id == b.items[0].id).values(status="running"))
    db.execute(update(Suggestion).where(Suggestion.id == sugs[0].id).values(status="approved"))
    db.commit()
    with pytest.raises(ProblemError) as e:
        create_draft(db, [sugs[0].id], None, now=clock(), env=env)
    assert e.value.code == "batch_empty" and "이미 담겨" in e.value.detail


def test_tc_vb_328_batch_stays_running_while_an_item_is_still_running(seeded, db, env, clock, gw):
    b, sugs = queued(db, env, clock(), 2)
    db.execute(update(BatchItem).where(BatchItem.id == b.items[1].id).values(status="running"))
    db.commit()
    apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    db.expire_all()
    assert db.get(Batch, b.id).status == "running"


def test_tc_vb_341_validator_never_yields_strict_mode_warn(seeded, db, env, clock):
    """변이 m08(승인 경로의 is_blocking 2번째 절)이 동치임을 받치는 전제: 엄격 모드에서는 경고가 항상 차단으로 바뀌어 (strict, warn) 조합이 나오지 않는다."""
    from ytweb.ai.base import VideoBrief
    from ytweb.ai.mock import MockSuggester
    from ytweb.domain.suggestions import validate_title
    seen = set()
    for v in db.execute(select(Video)).scalars():
        for d in MockSuggester().suggest(VideoBrief(v.video_id, v.title, v.description_excerpt or ""), count=5, tone="t"):
            r, _ = validate_title(env, v, d.title, d.evidence, d.topic)
            seen.add((r.strict, r.result))
    assert (True, "warn") not in seen and (True, "block") in seen and (False, "warn") in seen
