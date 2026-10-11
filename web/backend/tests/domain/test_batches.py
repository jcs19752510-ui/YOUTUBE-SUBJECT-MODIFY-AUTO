"""배치 초안·사전 점검·실행 확정·취소(049-062)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ytweb.core.errors import ProblemError
from ytweb.core.settings_store import set_web_setting
from ytweb.db.models import Batch, BatchItem, Job, Suggestion, Video
from ytweb.domain.batches import apply_one, cancel_batch, create_draft, execute_batch
from ytweb.domain.suggestions import approve

from tests.domain.helpers import approved, approved_many, eligible_video_ids, queued_batch, suggest

TODAY = date(2026, 10, 10)


def _problem(fn, *a, **kw) -> ProblemError:
    with pytest.raises(ProblemError) as e:
        fn(*a, **kw)
    return e.value


def _cap(db, clock, n):
    set_web_setting(db, "daily_apply_cap", n, now=clock())
    db.commit()


def test_tc_wb_049_precheck_contents(seeded, env, clock):
    sugs = approved_many(seeded, env, clock(), 3)
    batch, pre = create_draft(seeded, [s.id for s in sugs], " 주간  정리 ", now=clock(), env=env)
    assert pre == {
        "item_count": 3, "estimated_units": 3 * (50 + 1 + 1), "daily_cap": 10, "quota_remaining_units": 6000,
        "schedule": [{"date": "2026-10-10", "count": 3}], "warnings": pre["warnings"], "blocked": [], "confirm_text": "실행 3건",
        "notice": "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.",
    }
    assert any("A/B" in w for w in pre["warnings"])
    assert batch.status == "draft" and batch.note == "주간 정리" and batch.precheck == pre
    assert [(i.seq, i.status, i.scheduled_date) for i in batch.items] == [(1, "pending", None), (2, "pending", None), (3, "pending", None)]
    assert {s.status for s in sugs} == {"approved"}  # 초안만으로는 제안 상태가 바뀌지 않는다


def test_tc_wb_050_schedule_three_three_two(seeded, env, clock):
    _cap(seeded, clock, 3)
    sugs = approved_many(seeded, env, clock(), 8)
    batch, pre = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=env)
    assert pre["daily_cap"] == 3 and pre["schedule"] == [{"date": "2026-10-10", "count": 3}, {"date": "2026-10-11", "count": 3}, {"date": "2026-10-12", "count": 2}]
    assert any("3일에 나눠" in w for w in pre["warnings"])
    execute_batch(seeded, batch.id, "실행 8건", now=clock(), env=env)
    assert [i.scheduled_date for i in batch.items] == [TODAY] * 3 + [TODAY + timedelta(days=1)] * 3 + [TODAY + timedelta(days=2)] * 2
    assert {s.status for s in sugs} == {"queued"}


def test_tc_wb_051_schedule_shares_capacity_with_queued_batches(seeded, env, clock):
    _cap(seeded, clock, 3)
    first, *_ = queued_batch(seeded, env, clock(), 3)
    sugs = approved_many(seeded, env, clock(), 2, skip=3)
    _, pre = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=env)
    assert pre["schedule"] == [{"date": "2026-10-11", "count": 2}]  # 오늘 몫은 앞선 배치가 이미 가졌다
    assert any("모두 내일 이후" not in w for w in pre["warnings"]) and first.status == "queued"


def test_tc_wb_052_size_and_duplicate_limits(seeded, env, clock):
    assert _problem(create_draft, seeded, [], None, now=clock(), env=env).code == "batch_empty"
    e = _problem(create_draft, seeded, list(range(1, 52)), None, now=clock(), env=env)
    assert (e.status, e.code) == (422, "batch_too_large") and "50" in e.title
    sug = approved(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])
    e = _problem(create_draft, seeded, [sug.id, sug.id], None, now=clock(), env=env)
    assert (e.status, e.code) == (422, "duplicate_suggestion") and str(sug.id) in e.detail
    assert seeded.execute(select(Batch)).first() is None


def test_tc_wb_053_exactly_fifty_is_allowed(seeded, env, clock):
    sugs = approved_many(seeded, env, clock(), 12)
    ids = [s.id for s in sugs]
    _, pre = create_draft(seeded, ids, None, now=clock(), env=env)
    assert pre["item_count"] == 12 and pre["confirm_text"] == "실행 12건"


def test_tc_wb_054_not_approved_items_are_blocked_in_precheck(seeded, env, clock):
    vids = eligible_video_ids(seeded, 3)
    good = approved(seeded, env, clock(), vids[0])
    cand = suggest(seeded, env, clock(), vids[1])[0]                          # 승인 안 됨
    blocked = [s for s in suggest(seeded, env, clock(), vids[2], 5) if s.status == "blocked"][0]
    _, pre = create_draft(seeded, [good.id, cand.id, blocked.id, 987654], None, now=clock(), env=env)
    assert pre["item_count"] == 1
    reasons = {b["suggestion_id"]: b["code"] for b in pre["blocked"]}
    assert reasons == {cand.id: "not_approved", blocked.id: "not_approved", 987654: "suggestion_not_found"}
    e = _problem(create_draft, seeded, [cand.id], None, now=clock(), env=env)
    assert e.code == "batch_empty" and "승인" in e.detail


def test_tc_wb_055_expired_and_excluded_items_are_blocked(seeded, env, clock):
    vids = eligible_video_ids(seeded, 3)
    old, excluded_later = approved(seeded, env, clock(), vids[0]), approved(seeded, env, clock() + timedelta(hours=2), vids[1])
    later = clock() + timedelta(hours=25)
    fresh = approved(seeded, env, later, vids[2])
    video = seeded.get(Video, vids[1])
    video.privacy_status, video.exclusion_reasons = "private", ["비공개 영상"]  # 승인 뒤에 비공개로 바뀜
    seeded.flush()
    _, pre = create_draft(seeded, [old.id, excluded_later.id, fresh.id], None, now=later, env=env)
    assert pre["item_count"] == 1
    assert {b["suggestion_id"]: b["code"] for b in pre["blocked"]} == {old.id: "not_approved", excluded_later.id: "video_excluded"}
    assert old.status == "expired"


def test_tc_wb_056_suggestion_already_in_another_batch(seeded, env, clock):
    sugs = approved_many(seeded, env, clock(), 2)
    create_draft(seeded, [sugs[0].id], None, now=clock(), env=env)
    _, pre = create_draft(seeded, [sugs[0].id, sugs[1].id], None, now=clock(), env=env)
    assert [(b["suggestion_id"], b["code"]) for b in pre["blocked"]] == [(sugs[0].id, "already_in_batch")]
    other = seeded.execute(select(Batch).order_by(Batch.id)).scalars().first()
    with pytest.raises(IntegrityError):  # DB 부분 고유 인덱스도 같은 제안의 동시 진행을 막는다
        seeded.add(BatchItem(batch_id=other.id, suggestion_id=sugs[0].id, video_id=sugs[0].video_id, seq=9, status="pending", updated_at=clock()))
        seeded.flush()
    seeded.rollback()


def test_tc_wb_057_same_video_twice_in_one_batch(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    s1, s2 = suggest(seeded, env, clock(), vid, 2)
    approve(seeded, s1.id, "홍길동", now=clock(), env=env)
    approve(seeded, s2.id, "홍길동", now=clock(), env=env)
    _, pre = create_draft(seeded, [s1.id, s2.id], None, now=clock(), env=env)
    assert pre["item_count"] == 1 and pre["blocked"][0]["code"] == "duplicate_video"


def test_tc_wb_058_execute_requires_exact_confirm_text(seeded, env, clock):
    sugs = approved_many(seeded, env, clock(), 3)
    batch, pre = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=env)
    for wrong in ("", "실행 2건", "실행 3건 ", "실행3건", "실행 3 건", "RUN 3", pre["confirm_text"].replace("실행", "실행 ")):
        e = _problem(execute_batch, seeded, batch.id, wrong, now=clock(), env=env)
        assert (e.status, e.code) == (422, "confirm_text_mismatch") and "실행 3건" in e.detail
    assert batch.status == "draft" and seeded.execute(select(Job)).first() is None and {s.status for s in sugs} == {"approved"}


def test_tc_wb_059_execute_assigns_dates_queues_and_creates_job(seeded, env, clock):
    batch, sugs, job = queued_batch(seeded, env, clock(), 3)
    assert batch.status == "queued" and batch.executed_at == clock()
    assert [i.scheduled_date for i in batch.items] == [TODAY] * 3 and {s.status for s in sugs} == {"queued"}
    assert (job.type, job.status, job.total, job.payload) == ("batch.execute", "queued", 3, {"batch_id": batch.id})


def test_tc_wb_060_execute_twice_or_unknown_batch(seeded, env, clock):
    batch, *_ = queued_batch(seeded, env, clock(), 2)
    assert _problem(execute_batch, seeded, batch.id, "실행 2건", now=clock(), env=env).code == "batch_not_draft"
    assert _problem(execute_batch, seeded, 99999, "실행 2건", now=clock(), env=env).status == 404
    assert len(seeded.execute(select(Job)).scalars().all()) == 1


def test_tc_wb_061_execute_refuses_when_state_changed_since_precheck(seeded, env, clock):
    sugs = approved_many(seeded, env, clock(), 3)
    batch, pre = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=env)
    later = clock() + timedelta(hours=25)  # 사전 점검 뒤 승인이 만료됨
    e = _problem(execute_batch, seeded, batch.id, pre["confirm_text"], now=later, env=env)
    assert (e.status, e.code) == (409, "precheck_stale") and e.hint
    assert batch.status == "draft" and all(i.scheduled_date is None for i in batch.items)


def test_tc_wb_062_cancel_semantics(seeded, env, clock):
    draft_sugs = approved_many(seeded, env, clock(), 2)
    draft, _ = create_draft(seeded, [s.id for s in draft_sugs], None, now=clock(), env=env)
    assert cancel_batch(seeded, draft.id, now=clock(), env=env).status == "cancelled"
    assert {i.status for i in draft.items} == {"cancelled"} and {s.status for s in draft_sugs} == {"approved"}

    batch, sugs, _ = queued_batch(seeded, env, clock(), 3, skip=2)
    running = batch.items[0]
    running.status = "running"        # 진행 중 항목은 중지해도 완료까지 둔다
    seeded.commit()
    cancel_batch(seeded, batch.id, now=clock(), env=env)
    assert batch.status == "cancelled" and [i.status for i in batch.items] == ["running", "cancelled", "cancelled"]
    assert [seeded.get(Suggestion, s.id).status for s in sugs] == ["queued", "approved", "approved"]  # 취소된 항목의 제안은 승인 상태로 되돌아간다
    assert "[cancelled]" in batch.items[1].skip_reason
    assert _problem(cancel_batch, seeded, batch.id, now=clock(), env=env).code == "batch_not_cancellable"
    assert _problem(cancel_batch, seeded, 4242, now=clock(), env=env).status == 404
    assert apply_one(seeded, batch.items[1].id, now=clock(), env=env, gateway=None).status == "not_pending"  # 취소된 항목은 실행되지 않는다
