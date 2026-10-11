"""6단계 독립 검증 3: 일일 상한·배치 크기·일정 배정·72h 간격·영상당 3회·쿼터 3행 선예약·사전 점검(W-008/009, 안전 정책 6-3)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from ytweb.core.errors import ProblemError
from ytweb.core.settings_store import effective_daily_cap, set_web_setting
from ytweb.db.models import Batch, BatchItem, MetricsSnapshot, QuotaUsage, Suggestion, Video
from ytweb.domain.batches import apply_one, cancel_batch, create_draft, execute_batch, run_due_items
from ytweb.domain.limits_quota import applied_today, check_video_limits, quota_state, used_today
from ytweb.domain.suggestions import approve

from tests.verify_wb.vbh import Faulty, add_change, changes, day_counts, fill_quota, life_ids, make_sug, ok_sug, queued, quota_units, set_cap

UTC = timezone.utc


def _approved(db, env, now, n, skip=0):
    return [ok_sug(db, env, now, v) for v in life_ids(db, n, skip)]


# ───────────────────────── 배치 크기 ─────────────────────────

def test_tc_vb_070_batch_size_boundaries_0_1_50_51(seeded200, db, env, clock):
    """배치당 50건 상한: 0건 422, 50건 허용, 51건 422. 51번째가 적격이어도 거부."""
    sugs = _approved(db, env, clock(), 51)
    db.commit()
    with pytest.raises(ProblemError) as e0:
        create_draft(db, [], None, now=clock(), env=env)
    assert (e0.value.status, e0.value.code) == (422, "batch_empty")
    with pytest.raises(ProblemError) as e51:
        create_draft(db, [s.id for s in sugs], None, now=clock(), env=env)
    assert (e51.value.status, e51.value.code) == (422, "batch_too_large")
    assert db.execute(select(func.count()).select_from(Batch)).scalar_one() == 0
    b, pre = create_draft(db, [s.id for s in sugs[:50]], None, now=clock(), env=env)
    assert pre["item_count"] == 50 and pre["confirm_text"] == "실행 50건"
    b1, pre1 = create_draft(db, [sugs[50].id], None, now=clock(), env=env)
    assert pre1["item_count"] == 1


def test_tc_vb_071_duplicate_ids_and_same_video_twice(seeded, db, env, clock):
    a = ok_sug(db, env, clock(), life_ids(db, 1)[0])
    with pytest.raises(ProblemError) as e1:
        create_draft(db, [a.id, a.id], None, now=clock(), env=env)
    assert e1.value.code == "duplicate_suggestion"
    other = make_sug(db, env, clock(), a.video_id, "냉장고 정리 쉽게 따라 하는 순서 천천히 알려드립니다 둘")
    approve(db, other.id, "검수자", now=clock(), env=env)
    b, pre = create_draft(db, [a.id, other.id], None, now=clock(), env=env)
    assert pre["item_count"] == 1 and [x["code"] for x in pre["blocked"]] == ["duplicate_video"]


def test_tc_vb_072_blocked_items_are_listed_not_silently_dropped(seeded, db, env, clock):
    ok = ok_sug(db, env, clock(), life_ids(db, 1)[0])
    unapproved = make_sug(db, env, clock(), life_ids(db, 1, skip=1)[0])
    b, pre = create_draft(db, [ok.id, unapproved.id, 424242], None, now=clock(), env=env)
    codes = {x["suggestion_id"]: x["code"] for x in pre["blocked"]}
    assert pre["item_count"] == 1 and codes == {unapproved.id: "not_approved", 424242: "suggestion_not_found"}
    with pytest.raises(ProblemError) as e:
        create_draft(db, [unapproved.id], None, now=clock(), env=env)
    assert e.value.code == "batch_empty"


def test_tc_vb_073_suggestion_in_other_batch_cannot_be_added_again(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    with pytest.raises(ProblemError) as e:
        create_draft(db, [sugs[0].id], None, now=clock(), env=env)
    assert e.value.code == "batch_empty"


# ───────────────────────── 확인 문구 ─────────────────────────

@pytest.mark.parametrize("typed", ["", "실행 2건 ", " 실행 2건", "실행  2건", "실행 3건", "실행2건", "실행 2건\n", "execute 2", "실행 2 건", "실행 ２건"])
def test_tc_vb_074_confirm_text_must_match_exactly(seeded, db, env, clock, typed):
    sugs = _approved(db, env, clock(), 2)
    b, pre = create_draft(db, [s.id for s in sugs], None, now=clock(), env=env)
    db.commit()
    assert pre["confirm_text"] == "실행 2건"
    with pytest.raises(ProblemError) as e:
        execute_batch(db, b.id, typed, now=clock(), env=env)
    assert (e.value.status, e.value.code) == (422, "confirm_text_mismatch")
    db.rollback()
    db.expire_all()
    assert db.get(Batch, b.id).status == "draft" and all(s.status == "approved" for s in db.execute(select(Suggestion)).scalars() if s.id in {x.id for x in sugs})
    assert db.execute(select(func.count()).select_from(BatchItem).where(BatchItem.scheduled_date.is_not(None))).scalar_one() == 0
    b2, _ = execute_batch(db, b.id, "실행 2건", now=clock(), env=env)
    assert b2.status == "queued"


def test_tc_vb_075_execute_twice_and_cancelled_batch_not_executable(seeded, db, env, clock):
    sugs = _approved(db, env, clock(), 2)
    b, pre = create_draft(db, [s.id for s in sugs], None, now=clock(), env=env)
    execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
    with pytest.raises(ProblemError) as e:
        execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
    assert (e.value.status, e.value.code) == (409, "batch_not_draft")
    with pytest.raises(ProblemError) as e404:
        execute_batch(db, 9999, "실행 1건", now=clock(), env=env)
    assert e404.value.status == 404


def test_tc_vb_076_draft_batch_is_never_processed_by_tick(seeded, db, factory, env, clock):
    sugs = _approved(db, env, clock(), 2)
    b, pre = create_draft(db, [s.id for s in sugs], None, now=clock(), env=env)
    db.commit()
    res = run_due_items(factory, clock(), env)
    assert res.processed == 0 and quota_units(db) == 0 and changes(db) == []


# ───────────────────────── W-008 일정 배정·일일 상한 ─────────────────────────

def test_tc_vb_080_cap3_items8_schedules_3_3_2(seeded200, db, env, clock):
    """인수4: 상한 3·항목 8 → 3/3/2."""
    set_cap(db, clock, 3)
    b, sugs = queued(db, env, clock(), 8)
    assert list(day_counts(db, b.id).values()) == [3, 3, 2]
    days = list(day_counts(db, b.id))
    assert days[0] == "2026-10-10" and days[1] == "2026-10-11" and days[2] == "2026-10-12"
    assert b.precheck["schedule"] == [{"date": "2026-10-10", "count": 3}, {"date": "2026-10-11", "count": 3}, {"date": "2026-10-12", "count": 2}]


def test_tc_vb_081_default_cap_is_10_and_25_items_schedule_10_10_5(seeded200, db, env, clock):
    assert effective_daily_cap(db, env.policy) == 10
    b, sugs = queued(db, env, clock(), 25)
    assert list(day_counts(db, b.id).values()) == [10, 10, 5]
    assert b.precheck["daily_cap"] == 10


@pytest.mark.parametrize("raw, expected", [(1, 1), (20, 20), (7, 7), (0, 10), (21, 10), (-3, 10), (True, 10), ("5", 10), (None, 10)])
def test_tc_vb_082_effective_cap_validation_and_fallback(db, env, clock, raw, expected):
    """상한 설정값 경계: 1~20 정수만 유효. 그 밖/형식 오류는 기본 10(안전한 쪽 = 설정 오염이 상한을 올리지 못함)으로."""
    set_web_setting(db, "daily_apply_cap", raw, now=clock())
    assert effective_daily_cap(db, env.policy) == expected


def test_tc_vb_083_today_already_applied_reduces_todays_slots(seeded200, db, env, clock):
    set_cap(db, clock, 5)
    ids = life_ids(db, 20)
    for v in ids[:2]:
        add_change(db, v, clock() - timedelta(hours=1))
    db.commit()
    b, sugs = queued(db, env, clock(), 7, skip=2)
    assert list(day_counts(db, b.id).values()) == [3, 4]  # 오늘 5-2=3, 내일 4


def test_tc_vb_084_second_batch_shares_queue_slots_with_first(seeded200, db, env, clock):
    set_cap(db, clock, 3)
    b1, _ = queued(db, env, clock(), 4)
    b2, _ = queued(db, env, clock(), 4, skip=4)
    assert day_counts(db, b1.id) == {"2026-10-10": 3, "2026-10-11": 1}
    assert day_counts(db, b2.id) == {"2026-10-11": 2, "2026-10-12": 2}


def test_tc_vb_085_cap_reached_today_pushes_all_to_tomorrow(seeded, db, env, clock):
    set_cap(db, clock, 2)
    ids = life_ids(db, 6)
    for v in ids[:2]:
        add_change(db, v, clock() - timedelta(minutes=5))
    db.commit()
    b, _ = queued(db, env, clock(), 2, skip=2)
    assert day_counts(db, b.id) == {"2026-10-11": 2}
    assert any("상한" in w and "내일" in w for w in b.precheck["warnings"])


def test_tc_vb_086_tick_applies_only_daily_cap_even_after_downtime(seeded200, db, factory, env, clock):
    """인수4: 꺼져 있다 켜져도 하루 상한만큼만 처리(놓친 예약을 몰아서 실행하지 않음). W-008."""
    set_cap(db, clock, 3)
    b, sugs = queued(db, env, clock(), 8)
    clock.advance(days=5)   # 5일 동안 PC 꺼짐: 3일치 예약이 모두 밀림
    r1 = run_due_items(factory, clock(), env)
    assert (r1.success, r1.stopped_by) == (3, "cap_reached")
    assert applied_today(db, clock()) == 3
    clock.advance(days=1)
    r2 = run_due_items(factory, clock(), env)
    assert (r2.success, r2.stopped_by) == (3, "cap_reached")
    clock.advance(days=1)
    r3 = run_due_items(factory, clock(), env)
    assert (r3.success, r3.stopped_by) == (2, None)
    db.expire_all()
    assert db.get(Batch, b.id).status == "done"
    # 반영 순서는 예약 순서(seq)
    applied = [c.suggestion_id for c in changes(db)]
    assert applied == [s.id for s in sugs]


def test_tc_vb_087_tick_waits_for_future_dates_and_batch_status_queued(seeded200, db, factory, env, clock):
    set_cap(db, clock, 2)
    b, _ = queued(db, env, clock(), 5)
    r = run_due_items(factory, clock(), env)
    assert r.success == 2
    db.expire_all()
    assert db.get(Batch, b.id).status == "queued"  # 미래 예약만 남으면 running 이 아니라 queued
    assert run_due_items(factory, clock(), env).processed == 0


def test_tc_vb_088_kst_midnight_boundary_for_daily_count(seeded, db, env, clock):
    """KST 하루 경계: 14:59:59Z(=23:59:59 KST)는 같은 날, 15:00:00Z 는 다음 날."""
    vids = life_ids(db, 4)
    now = datetime(2026, 10, 10, 3, 0, tzinfo=UTC)
    add_change(db, vids[0], datetime(2026, 10, 9, 14, 59, 59, tzinfo=UTC))   # 어제(KST)
    add_change(db, vids[1], datetime(2026, 10, 9, 15, 0, 0, tzinfo=UTC))     # 오늘 시작
    add_change(db, vids[2], datetime(2026, 10, 10, 14, 59, 59, tzinfo=UTC))  # 오늘 끝
    add_change(db, vids[3], datetime(2026, 10, 10, 15, 0, 0, tzinfo=UTC))    # 내일
    assert applied_today(db, now) == 2
    assert applied_today(db, datetime(2026, 10, 10, 15, 0, 0, tzinfo=UTC)) == 1   # 날짜가 바뀌면 새로 센다


def test_tc_vb_089_only_apply_success_or_planned_count_toward_cap(seeded, db, env, clock):
    vids = life_ids(db, 6)
    t = clock() - timedelta(minutes=1)
    add_change(db, vids[0], t, result="success")
    add_change(db, vids[1], t, result="planned")
    add_change(db, vids[2], t, result="failed")
    add_change(db, vids[3], t, result="aborted")
    add_change(db, vids[4], t, result="success", change_type="rollback")
    assert applied_today(db, clock()) == 2


# ───────────────────────── 영상별 한도: 72h / 3회 / 노출수 ─────────────────────────

def _codes(report):
    return {c.code: c.passed for c in report.checks}


def test_tc_vb_090_interval_72h_boundary(seeded, db, env_free, clock):
    vid = life_ids(db, 1)[0]
    t0 = clock()
    add_change(db, vid, t0)
    pol = env_free.policy
    for delta, ok in ((timedelta(hours=72) - timedelta(seconds=1), False), (timedelta(hours=72), True), (timedelta(hours=72, seconds=1), True), (timedelta(0), False)):
        rep = check_video_limits(db, vid, t0 + delta, pol, 10)
        assert _codes(rep)["INTERVAL"] is ok, delta


def test_tc_vb_091_max_3_changes_per_video(seeded, db, env_free, clock):
    vid = life_ids(db, 1)[0]
    t0 = clock() - timedelta(days=30)
    add_change(db, vid, t0, n=2)
    rep = check_video_limits(db, vid, clock(), env_free.policy, 10)
    assert _codes(rep)["COUNT"] is True and rep.passed
    add_change(db, vid, t0 + timedelta(days=1))
    rep = check_video_limits(db, vid, clock(), env_free.policy, 10)
    assert _codes(rep)["COUNT"] is False and not rep.passed
    # failed/aborted 는 횟수에 세지 않음, planned 는 센다
    vid2 = life_ids(db, 1, skip=1)[0]
    add_change(db, vid2, t0, result="failed", n=3)
    add_change(db, vid2, t0, result="aborted", n=3)
    assert check_video_limits(db, vid2, clock(), env_free.policy, 10).passed
    add_change(db, vid2, t0, result="success", n=2)
    add_change(db, vid2, t0, result="planned")
    assert _codes(check_video_limits(db, vid2, clock(), env_free.policy, 10))["COUNT"] is False


def test_tc_vb_092_min_impressions_boundary_999_1000_none(seeded, db, env, clock):
    """재변경 최소 노출수(정책 1000, 기록 없음=거부 fail-closed). 변경 이후 시작하는 기간의 지표만 인정."""
    vid = life_ids(db, 1)[0]
    last = clock() - timedelta(days=10)
    add_change(db, vid, last)
    now = clock()
    assert _codes(check_video_limits(db, vid, now, env.policy, 10))["IMPRESSIONS"] is False  # 기록 없음
    def snap(imp, start_off=1, phase="after", taken=None):
        db.add(MetricsSnapshot(video_id=vid, taken_at=taken or now, phase=phase, source="demo", impressions=imp, period_start=(last + timedelta(days=start_off)).date(), period_end=(now - timedelta(days=1)).date(), ctr=1.0, views=1, watch_minutes=1.0))
        db.flush()
    snap(999)
    assert _codes(check_video_limits(db, vid, now, env.policy, 10))["IMPRESSIONS"] is False
    snap(1000)
    assert _codes(check_video_limits(db, vid, now, env.policy, 10))["IMPRESSIONS"] is True
    # 변경 이전부터 시작하는 기간(period_start <= 변경 날짜)의 큰 값은 무시
    vid2 = life_ids(db, 1, skip=1)[0]
    add_change(db, vid2, last)
    db.add(MetricsSnapshot(video_id=vid2, taken_at=now, phase="after", source="demo", impressions=99999, period_start=last.date(), period_end=now.date(), ctr=1.0, views=1, watch_minutes=1.0))
    db.add(MetricsSnapshot(video_id=vid2, taken_at=now, phase="before", source="demo", impressions=99999, period_start=(last + timedelta(days=1)).date(), period_end=now.date(), ctr=1.0, views=1, watch_minutes=1.0))
    db.flush()
    assert _codes(check_video_limits(db, vid2, now, env.policy, 10))["IMPRESSIONS"] is False


def test_tc_vb_093_dec042_demo_relaxes_min_impressions_only_for_limit_judgement(seeded, db, env, clock):
    """DEC-042: 데모(Env.build)는 교체 한도 판정에서만 최소 노출수를 0 으로 낮춘다. 정책 값(리포트 '데이터 부족' 기준)은 1000 그대로."""
    vid = life_ids(db, 1)[0]
    add_change(db, vid, clock() - timedelta(hours=73))
    assert env.policy.min_impressions_before_rechange == 1000 and env.rechange_min_impressions == 0
    assert env.limits_policy.min_impressions_before_rechange == 0
    rep = check_video_limits(db, vid, clock(), env.limits_policy, 10)
    assert rep.passed and _codes(rep)["INTERVAL"] is True and _codes(rep)["IMPRESSIONS"] is True
    # 완화는 노출수에만: 72시간 이내는 여전히 거부, 3회째 이후도 거부
    vid2 = life_ids(db, 1, skip=1)[0]
    add_change(db, vid2, clock() - timedelta(hours=71))
    assert _codes(check_video_limits(db, vid2, clock(), env.limits_policy, 10))["INTERVAL"] is False
    vid3 = life_ids(db, 1, skip=2)[0]
    for d in (30, 20, 10):
        add_change(db, vid3, clock() - timedelta(days=d))
    assert _codes(check_video_limits(db, vid3, clock(), env.limits_policy, 10))["COUNT"] is False
    # 완화 설정이 없는 Env(실제 모드 가정)는 정책 값 그대로 적용
    from dataclasses import replace
    strict = replace(env, rechange_min_impressions=None)
    assert strict.limits_policy.min_impressions_before_rechange == 1000
    assert _codes(check_video_limits(db, vid, clock(), strict.limits_policy, 10))["IMPRESSIONS"] is False


def test_tc_vb_094_dec042_demo_rechange_allowed_after_72h_through_apply_one(seeded, db, env, clock, gw):
    """사전 점검·반영(apply_one) 두 경로 모두 완화가 적용되어 72시간 뒤 같은 영상의 재변경이 성공한다."""
    from ytweb.db.models import Change as _C
    vid = life_ids(db, 1)[0]
    add_change(db, vid, clock() - timedelta(hours=73))
    db.commit()
    sug = ok_sug(db, env, clock(), vid)
    b, pre = create_draft(db, [sug.id], None, now=clock(), env=env)
    assert not pre.get("blocked")
    execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
    db.commit()
    item = db.execute(select(BatchItem).where(BatchItem.video_id == vid)).scalars().one()
    assert item.status == "pending"
    out = apply_one(db, item.id, now=clock(), env=env, gateway=gw)
    assert out.status == "success"
    assert db.execute(select(func.count()).select_from(_C).where(_C.video_id == vid, _C.result == "success")).scalar_one() == 2


def test_tc_vb_095_daily_cap_check_inside_limits_uses_web_cap_not_policy_3(seeded, db, env, clock):
    """evaluate_limits DAILY 에 웹 상한(기본 10)을 넣어 쓴다: 정책의 3이 아니라 10."""
    vids = life_ids(db, 12)
    for v in vids[:9]:
        add_change(db, v, clock() - timedelta(minutes=1))
    rep = check_video_limits(db, vids[11], clock(), env.policy, 10)
    assert _codes(rep)["DAILY"] is True
    add_change(db, vids[9], clock() - timedelta(minutes=1))
    assert _codes(check_video_limits(db, vids[11], clock(), env.policy, 10))["DAILY"] is False
    assert _codes(check_video_limits(db, vids[11], clock(), env.policy, 11))["DAILY"] is True


def test_tc_vb_096_apply_refuses_when_video_limit_fails_and_does_not_touch_youtube(seeded, db, env_free, clock):
    env = env_free
    b, sugs = queued(db, env, clock(), 1)
    vid = sugs[0].video_id
    add_change(db, vid, clock() - timedelta(hours=10))
    db.commit()
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("skipped", "limit_interval")
    assert g.reads == 0 and g.updates == 0 and quota_units(db) == 0


def test_tc_vb_097_daily_cap_enforced_inside_apply_one_even_if_scheduled_today(seeded, db, env, clock):
    """일정이 오늘로 배정돼 있어도 apply_one 자체가 오늘 상한을 다시 확인(스케줄러 우회·동시 틱 방어 심층)."""
    set_cap(db, clock, 2)
    b, sugs = queued(db, env, clock(), 3)
    # 일정 조작: 3건 모두 오늘로
    from tests.verify_wb.vbh import set_all_due
    set_all_due(db, b.id, clock().date())
    g = Faulty(db, clock)
    outs = [apply_one(db, it.id, now=clock(), env=env, gateway=g) for it in b.items]
    # DEF-VB-01 수정 후: 오늘 몫이 찬 뒤 도달한 항목은 건너뛰지 않고 다음 날(KST)로 이월한다
    assert [o.status for o in outs] == ["success", "success", "deferred"] and outs[2].code == "limit_daily"
    third = db.get(BatchItem, b.items[2].id)
    assert third.status == "pending" and third.scheduled_date == clock().astimezone(timezone(timedelta(hours=9))).date() + timedelta(days=1)
    assert third.change_id is None and third.skip_reason is None
    assert applied_today(db, clock()) == 2 and g.updates == 2 and quota_units(db) == 2 * 52


# ───────────────────────── 쿼터 3행 선예약 ─────────────────────────

def test_tc_vb_100_success_reserves_three_rows_52_units(seeded, db, env, clock, gw):
    b, sugs = queued(db, env, clock(), 1)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    assert out.status == "success"
    rows = db.execute(select(QuotaUsage).order_by(QuotaUsage.id)).scalars().all()
    assert [(r.method, r.units, r.status) for r in rows] == [("videos.list", 1, "ok"), ("videos.update", 50, "ok"), ("videos.list", 1, "ok")]


def test_tc_vb_101_reservation_happens_before_first_gateway_call_all_or_nothing(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    g = Faulty(db, clock)
    snapshot = {}

    def spy(n, snap):
        if snapshot:
            return snap
        db.expire_all()
        snapshot["rows"] = [(r.units, r.status) for r in db.execute(select(QuotaUsage)).scalars()]
        return snap

    g.on_read = spy
    apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert snapshot["rows"] == [(1, "reserved"), (50, "reserved"), (1, "reserved")]  # 첫 호출 시점에 3행이 이미 예약됨


@pytest.mark.parametrize("remaining, expect", [(52, "success"), (51, "skipped"), (53, "success"), (0, "skipped")])
def test_tc_vb_102_quota_boundary_52_needed(seeded, db, env, clock, remaining, expect):
    b, sugs = queued(db, env, clock(), 1)
    fill_quota(db, clock(), env.policy.daily_limit_units - remaining)
    before = quota_units(db)
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert out.status == expect
    if expect == "skipped":
        assert out.code == "quota_exhausted" and g.reads == 0 and g.updates == 0
        assert quota_units(db) == before                       # 부분 예약이 남지 않음
        assert changes(db) == []
        db.expire_all()
        assert db.get(Suggestion, sugs[0].id).approval.used_at is None  # 승인 소진 안 됨
        assert db.get(Suggestion, sugs[0].id).status == "approved"       # 승인 유효하므로 다시 대기 가능
    else:
        assert used_today(db, clock()) <= env.policy.daily_limit_units


def test_tc_vb_103_verify_read_always_has_quota_when_write_happened(seeded, db, env, clock):
    """쓰기 뒤 검증할 쿼터가 없는 상황 방지: 잔여가 정확히 52 여도 반영 → 검증까지 끝난다."""
    b, sugs = queued(db, env, clock(), 1)
    fill_quota(db, clock(), env.policy.daily_limit_units - 52)
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert out.status == "success" and g.reads == 2 and used_today(db, clock()) == env.policy.daily_limit_units
    c = changes(db)[0]
    assert c.verify_result["ok"] is True


def test_tc_vb_104_read_failure_keeps_1_unit_releases_rest(seeded, db, env, clock):
    from ytweb.youtube.base import GatewayError
    b, sugs = queued(db, env, clock(), 1)
    g = Faulty(db, clock)

    def boom(n, snap):
        raise GatewayError("rate", "일시 오류")

    g.on_read = boom
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("failed", "read_failed")
    rows = db.execute(select(QuotaUsage).order_by(QuotaUsage.id)).scalars().all()
    assert [(r.units, r.status) for r in rows] == [(1, "failed"), (0, "failed"), (0, "failed")]
    assert changes(db) == [] and g.updates == 0
    db.expire_all()
    assert db.get(Suggestion, sugs[0].id).approval.used_at is None


def test_tc_vb_105_update_definite_failure_keeps_51_units_marks_change_failed(seeded, db, env, clock):
    from ytweb.youtube.base import GatewayError
    b, sugs = queued(db, env, clock(), 1)
    g = Faulty(db, clock)

    def boom(n, body):
        raise GatewayError("forbidden", "권한 없음", definite=True)

    g.on_update = boom
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("failed", "update_failed")
    rows = db.execute(select(QuotaUsage).order_by(QuotaUsage.id)).scalars().all()
    assert [(r.units, r.status) for r in rows] == [(1, "ok"), (50, "failed"), (0, "failed")]
    c = changes(db)[0]
    assert c.result == "failed" and c.error_code == "update_failed" and c.applied_at is None
    assert db.get(Video, sugs[0].video_id).title != sugs[0].title
    # 실패한 변경은 한도(횟수/간격/일일)에 산입되지 않는다
    assert applied_today(db, clock()) == 0


def test_tc_vb_106_quota_resets_at_pacific_midnight(seeded, db, env, clock):
    """쿼터의 하루는 태평양 시간: 2026-10-10 06:59:59Z(PDT 23:59:59)는 전날, 07:00:00Z 는 새 날."""
    t = datetime(2026, 10, 10, 6, 59, 59, tzinfo=UTC)
    fill_quota(db, t, 5990)
    assert quota_state(db, t, env.policy).remaining == 10
    t2 = datetime(2026, 10, 10, 7, 0, 0, tzinfo=UTC)
    assert quota_state(db, t2, env.policy).remaining == env.policy.daily_limit_units
    assert quota_state(db, t2, env.policy).pt_date.isoformat() == "2026-10-10"


def test_tc_vb_107_tick_stops_pending_when_quota_short_not_skipping(seeded200, db, factory, env, clock):
    b, sugs = queued(db, env, clock(), 3)
    fill_quota(db, clock(), env.policy.daily_limit_units - 60)   # 1건 분량(52)만 남음
    r = run_due_items(factory, clock(), env)
    assert r.success == 1 and r.stopped_by == "quota_exhausted"
    db.expire_all()
    left = [i.status for i in db.get(Batch, b.id).items]
    assert left.count("pending") == 2 and left.count("skipped") == 0 and left.count("failed") == 0
    clock.advance(hours=5)  # 태평양 자정(07:00Z) 이후
    clock.advance(hours=1)
    r2 = run_due_items(factory, clock(), env)
    assert r2.success == 2


# ───────────────────────── 사전 점검(W-009) ─────────────────────────

def test_tc_vb_110_precheck_numbers_and_warnings(seeded200, db, env, clock):
    sugs = _approved(db, env, clock(), 4)
    b, pre = create_draft(db, [s.id for s in sugs], "메모\n줄바꿈", now=clock(), env=env)
    assert pre["item_count"] == 4 and pre["estimated_units"] == 4 * 52 and pre["daily_cap"] == 10
    assert pre["quota_remaining_units"] == env.policy.daily_limit_units
    assert pre["confirm_text"] == "실행 4건" and pre["schedule"] == [{"date": "2026-10-10", "count": 4}]
    assert any("A/B" in w for w in pre["warnings"])
    assert "\n" not in (b.note or "")


def test_tc_vb_111_precheck_warns_when_today_exceeds_remaining_quota(seeded, db, env, clock):
    sugs = _approved(db, env, clock(), 3)
    fill_quota(db, clock(), env.policy.daily_limit_units - 100)
    b, pre = create_draft(db, [s.id for s in sugs], None, now=clock(), env=env)
    assert pre["quota_remaining_units"] == 100 and any("쿼터" in w for w in pre["warnings"])


def test_tc_vb_112_warn_result_included_gets_warning(seeded, db, env, clock):
    vid = life_ids(db, 1)[0]
    s = make_sug(db, env, clock(), vid, "냉장고 정리 처음이라도 쉽게 따라 하는 순서와 주의할 점 그리고 집에서 바로 해보는 방법까지 천천히")
    assert s.validation_result == "warn"
    approve(db, s.id, "검수자", now=clock(), env=env)
    b, pre = create_draft(db, [s.id], None, now=clock(), env=env)
    assert any("경고 판정" in w for w in pre["warnings"])


def test_tc_vb_113_excluded_video_blocked_in_precheck_and_in_apply(seeded, db, env, clock):
    """D3: 제외 영상은 사전 점검(blocked)·반영(skipped)에서도 막는다."""
    s1 = ok_sug(db, env, clock(), life_ids(db, 1)[0])
    s2 = ok_sug(db, env, clock(), life_ids(db, 1, skip=1)[0])
    db.get(Video, s2.video_id).made_for_kids = True
    db.flush()
    b, pre = create_draft(db, [s1.id, s2.id], None, now=clock(), env=env)
    assert pre["item_count"] == 1 and pre["blocked"][0]["code"] == "video_excluded"
    # 실행 확정 이후 영상이 제외 대상이 되면 반영 단계에서 skipped
    b, _ = execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
    db.get(Video, s1.video_id).privacy_status = "private"
    db.commit()
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("skipped", "video_excluded") and g.reads == 0 and g.updates == 0


# ───────────────────────── 취소(W-010) ─────────────────────────

def test_tc_vb_120_cancel_stops_pending_and_restores_suggestions(seeded, db, factory, env, clock):
    set_cap(db, clock, 1)
    b, sugs = queued(db, env, clock(), 3)
    assert run_due_items(factory, clock(), env).success == 1
    db.expire_all()
    cancel_batch(db, b.id, now=clock(), env=env)
    db.commit()
    db.expire_all()
    bb = db.get(Batch, b.id)
    assert bb.status == "cancelled"
    assert sorted(i.status for i in bb.items) == ["cancelled", "cancelled", "success"]
    assert [db.get(Suggestion, s.id).status for s in sugs] == ["applied", "approved", "approved"]
    clock.advance(days=3)
    assert run_due_items(factory, clock(), env).processed == 0
    with pytest.raises(ProblemError) as e:
        cancel_batch(db, b.id, now=clock(), env=env)
    assert e.value.code == "batch_not_cancellable"


def test_tc_vb_121_cancelled_items_can_be_requeued_in_new_batch(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 2)
    cancel_batch(db, b.id, now=clock(), env=env)
    db.commit()
    b2, pre = create_draft(db, [s.id for s in sugs], None, now=clock(), env=env)
    assert pre["item_count"] == 2


def test_tc_vb_122_cancel_after_ttl_returns_to_approved_per_d1_then_expires_on_next_touch(seeded, db, env, clock):
    """D1: 취소 시 승인 유효성도 '실행 확정 시각' 기준이라 approved 로 돌아오지만, 다음 조회/배치 담기 때 만료 처리되어 재사용 불가."""
    b, sugs = queued(db, env, clock(), 1)
    clock.advance(hours=30)
    cancel_batch(db, b.id, now=clock(), env=env)
    db.commit()
    db.expire_all()
    assert db.get(Suggestion, sugs[0].id).status == "approved"
    with pytest.raises(ProblemError):
        create_draft(db, [sugs[0].id], None, now=clock(), env=env)
    assert db.get(Suggestion, sugs[0].id).status == "expired"


def test_tc_vb_123_running_item_is_left_alone_by_cancel(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 2)
    from sqlalchemy import update
    db.execute(update(BatchItem).where(BatchItem.id == b.items[0].id).values(status="running"))
    db.commit()
    cancel_batch(db, b.id, now=clock(), env=env)
    db.expire_all()
    st = {i.seq: i.status for i in db.get(Batch, b.id).items}
    assert st == {1: "running", 2: "cancelled"}


def test_tc_vb_124_cancelled_batch_item_not_applied_if_claimed_late(seeded, db, env, clock):
    b, sugs = queued(db, env, clock(), 1)
    item_id = b.items[0].id
    cancel_batch(db, b.id, now=clock(), env=env)
    db.commit()
    g = Faulty(db, clock)
    out = apply_one(db, item_id, now=clock(), env=env, gateway=g)
    assert out.status == "not_pending" and g.updates == 0 and changes(db) == []


def test_tc_vb_098_over_cap_item_carries_over_and_runs_next_day(seeded, db, factory, env, clock):
    set_cap(db, clock, 1)
    b, sugs = queued(db, env, clock(), 2)
    from tests.verify_wb.vbh import set_all_due
    set_all_due(db, b.id, clock().date())
    g = Faulty(db, clock)
    assert apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g).status == "success"
    out = apply_one(db, b.items[1].id, now=clock(), env=env, gateway=g)
    assert out.status == "deferred"
    db.expire_all()
    assert db.get(BatchItem, b.items[1].id).status == "pending" and db.get(Batch, b.id).status == "queued"
    r = run_due_items(factory, clock(), env)               # 같은 날 다시 틱: 아무 것도 안 하고 상한 도달만 보고
    assert (r.processed, r.stopped_by) == (0, None) or r.stopped_by == "cap_reached"
    assert applied_today(db, clock()) == 1
    clock.advance(days=1)
    r2 = run_due_items(factory, clock(), env)
    assert r2.success == 1
    db.expire_all()
    assert db.get(Batch, b.id).status == "done" and db.get(BatchItem, b.items[1].id).status == "success"
