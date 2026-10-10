"""워커 틱·재시작 복구·작업 핸들러(081-092)."""
from __future__ import annotations

import dataclasses
from datetime import timedelta

from sqlalchemy import func, select

from ytweb.core import jobs
from ytweb.core.settings_store import set_web_setting
from ytweb.db.models import Batch, BatchItem, Change, Job, Suggestion, Video
from ytweb.domain import handlers
from ytweb.domain.batches import cancel_batch, create_draft, execute_batch, recover_running_items, run_due_items
from ytweb.domain.common import set_default_env
from ytweb.worker import Worker, load_domain_handlers

from tests.domain.helpers import FaultyGateway, approved, approved_many, eligible_video_ids, queued_batch


def _statuses(db, batch_id):
    db.expire_all()
    return [i.status for i in db.get(Batch, batch_id).items]


def _cap(db, clock, n):
    set_web_setting(db, "daily_apply_cap", n, now=clock())
    db.commit()


def test_tc_wb_081_tick_never_exceeds_todays_cap(seeded, factory, env, clock):
    _cap(seeded, clock, 3)
    batch, *_ = queued_batch(seeded, env, clock(), 8)
    res = run_due_items(factory, clock(), env)
    assert (res.processed, res.success) == (3, 3)
    assert _statuses(seeded, batch.id) == ["success"] * 3 + ["pending"] * 5
    again = run_due_items(factory, clock(), env)
    assert again.processed == 0  # 오늘 몫은 끝, 내일 예약분은 건드리지 않는다
    seeded.expire_all()
    assert seeded.get(Batch, batch.id).status == "running"


def test_tc_wb_082_missed_days_are_not_burst_executed(seeded, factory, env, clock):
    _cap(seeded, clock, 3)
    batch, *_ = queued_batch(seeded, env, clock(), 8)      # 3/3/2 로 예약, PC 는 이후 이틀간 꺼져 있었다
    clock.advance(days=2)
    res = run_due_items(factory, clock(), env)
    assert res.processed == 3 and res.stopped_by == "cap_reached"   # 8건이 모두 도래했어도 하루 상한만
    assert _statuses(seeded, batch.id) == ["success"] * 3 + ["pending"] * 5
    assert run_due_items(factory, clock(), env).processed == 0
    clock.advance(days=1)
    assert run_due_items(factory, clock(), env).processed == 3
    clock.advance(days=1)
    assert run_due_items(factory, clock(), env).processed == 2
    assert _statuses(seeded, batch.id) == ["success"] * 8 and seeded.get(Batch, batch.id).status == "done"
    assert seeded.execute(select(func.count()).select_from(Change)).scalar_one() == 8


def test_tc_wb_083_tick_stops_on_quota_and_resumes_next_pacific_day(seeded, factory, env, clock):
    tight = dataclasses.replace(env, policy=dataclasses.replace(env.policy, daily_limit_units=104))
    batch, *_ = queued_batch(seeded, env, clock(), 5)
    res = run_due_items(factory, clock(), tight)
    assert (res.processed, res.stopped_by) == (2, "quota_exhausted")
    assert _statuses(seeded, batch.id) == ["success"] * 2 + ["pending"] * 3  # 건너뛰지 않고 대기
    clock.advance(hours=5)                                                  # 태평양 시간 자정 이후(쿼터 초기화), 한국 날짜는 그대로
    res2 = run_due_items(factory, clock(), tight)
    assert res2.processed == 2 and res2.stopped_by == "quota_exhausted"
    assert _statuses(seeded, batch.id).count("success") == 4


def test_tc_wb_084_tick_ignores_draft_and_cancelled_batches(seeded, factory, env, clock):
    sugs = approved_many(seeded, env, clock(), 2)
    draft, _ = create_draft(seeded, [sugs[0].id], None, now=clock(), env=env)
    queued, _, _ = queued_batch(seeded, env, clock(), 2, skip=2)
    cancel_batch(seeded, queued.id, now=clock(), env=env)
    seeded.commit()
    assert run_due_items(factory, clock(), env).processed == 0
    assert _statuses(seeded, draft.id) == ["pending"] and _statuses(seeded, queued.id) == ["cancelled"] * 2


def test_tc_wb_085_failures_do_not_stop_the_tick(seeded, factory, env, clock):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 3)
    victim = seeded.get(Video, sugs[1].video_id)
    victim.snippet = {**victim.snippet, "tags": ["바뀜"]}      # 두 번째 항목만 plan_mismatch
    seeded.commit()
    res = run_due_items(factory, clock(), env)
    assert (res.processed, res.success, res.skipped, res.failed) == (3, 2, 1, 0)
    assert _statuses(seeded, batch.id) == ["success", "skipped", "success"]


def test_tc_wb_086_recover_running_items_by_reread(seeded, factory, env, clock):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 4)
    items = list(batch.items)
    gw = FaultyGateway(seeded, clock)

    def planned(item, sug):
        video = seeded.get(Video, sug.video_id)
        ch = Change(video_id=video.video_id, suggestion_id=sug.id, batch_id=batch.id, change_type="apply", previous_title=video.title, new_title=sug.title,
                    backup_snippet=dict(video.snippet), result="planned", mode="demo", created_at=clock())
        seeded.add(ch)
        seeded.flush()
        item.status, item.change_id, item.updated_at = "running", ch.id, clock()
        sug.approval.used_at = clock()
        return ch, video

    ch_a, v_a = planned(items[0], sugs[0])           # a: 갱신까지 끝났는데 기록 전에 끊김
    body = {"id": v_a.video_id, "snippet": {**v_a.snippet, "title": sugs[0].title}}
    gw.update_snippet(v_a.video_id, body)
    ch_b, _ = planned(items[1], sugs[1])             # b: 갱신 전에 끊김
    items[2].status, items[2].updated_at = "running", clock()   # c: planned 기록 전에 끊김
    ch_d, v_d = planned(items[3], sugs[3])           # d: 제목이 이전도 새것도 아님
    v_d.title = "제3의 제목"
    v_d.snippet = {**v_d.snippet, "title": "제3의 제목"}
    seeded.commit()
    assert recover_running_items(factory, clock(), env) == 0                       # 방금 시작한 항목은 건드리지 않는다
    assert recover_running_items(factory, clock() + timedelta(minutes=11), env) == 4
    seeded.expire_all()
    assert [i.status for i in batch.items] == ["success", "failed", "pending", "failed"]
    assert seeded.get(Change, ch_a.id).result == "success" and seeded.get(Suggestion, sugs[0].id).status == "applied"
    assert (seeded.get(Change, ch_b.id).result, seeded.get(Change, ch_b.id).error_code) == ("aborted", "interrupted")
    assert seeded.get(Change, ch_d.id).result == "planned" and "[result_unknown]" in batch.items[3].skip_reason
    assert seeded.get(Suggestion, sugs[1].id).status == "expired"  # 승인이 소진되어 다시 승인 필요
    assert seeded.get(Suggestion, sugs[2].id).status == "queued"   # 처음부터 다시 처리 가능


def test_tc_wb_087_job_handler_batch_execute(seeded, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    batch, _, job = queued_batch(seeded, env, clock(), 3)
    assert jobs.process_next(factory, worker_id="t", clock=clock) is True
    seeded.expire_all()
    done = seeded.get(Job, job.id)
    assert done.status == "succeeded" and done.progress == 3 and done.result["success"] == 3 and "자동 처리" in done.result["note"]
    assert seeded.get(Batch, batch.id).status == "done"


def test_tc_wb_088_job_handler_videos_sync(factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    with factory() as s:
        jobs.enqueue(s, type="videos.sync", payload={}, total=200, now=clock())
        s.commit()
    assert jobs.process_next(factory, worker_id="t", clock=clock)
    with factory() as s:
        job = s.execute(select(Job)).scalar_one()
        assert job.status == "succeeded" and job.result["created"] == 200 and s.execute(select(func.count()).select_from(Video)).scalar_one() == 200


def test_tc_wb_089_job_handler_generate_isolates_failures(seeded, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    ok = eligible_video_ids(seeded, 2)
    excluded = next(v.video_id for v in seeded.execute(select(Video)).scalars() if v.exclusion_reasons)
    with factory() as s:
        jobs.enqueue(s, type="suggestions.generate", payload={"video_ids": [ok[0], excluded, ok[1]], "count": 2}, total=3, now=clock())
        s.commit()
    jobs.process_next(factory, worker_id="t", clock=clock)
    with factory() as s:
        job = s.execute(select(Job)).scalar_one()
        assert job.status == "succeeded" and job.progress == 3
        assert job.result == {"videos": 3, "suggestions": 4, "skipped": [{"video_id": excluded, "code": "video_excluded"}]}


def test_tc_wb_090_tick_batch_filter_and_worker_integration(seeded, factory, env, clock):
    set_default_env(env)
    b1, *_ = queued_batch(seeded, env, clock(), 2)
    b2, *_ = queued_batch(seeded, env, clock(), 2, skip=2)
    assert run_due_items(factory, clock(), env, batch_id=b2.id).processed == 2
    assert _statuses(seeded, b1.id) == ["pending"] * 2
    fn = load_domain_handlers()
    assert fn is run_due_items
    worker = Worker(factory, clock=clock, run_due_items=fn)
    worker.tick()   # 워커 틱이 도메인 함수를 시그니처 그대로 호출한다(job 처리 → 틱)
    assert _statuses(seeded, b1.id) == ["success"] * 2


def test_tc_wb_091_progress_callback_and_empty_tick(seeded, factory, env, clock):
    queued_batch(seeded, env, clock(), 3)
    seen = []
    res = run_due_items(factory, clock(), env, on_progress=seen.append)
    assert seen == [1, 2, 3] and res.processed == 3
    assert run_due_items(factory, clock(), env).processed == 0


def test_tc_wb_092_expired_unqueued_approvals_are_swept_by_tick(seeded, factory, env, clock):
    sug = approved(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])
    seeded.commit()
    run_due_items(factory, clock() + timedelta(hours=25), env)
    seeded.expire_all()
    assert seeded.get(Suggestion, sug.id).status == "expired"
