"""교체 한도와 쿼터(041-050)."""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from ytweb.db.models import Change, MetricsSnapshot, QuotaUsage
from ytweb.domain.common import StepFailure
from ytweb.domain.limits_quota import (
    applied_today, check_video_limits, gather_facts, mark_call, quota_state, release_unused, reserve_calls, summarize_limits, units_per_apply,
)

from tests.domain.helpers import eligible_video_ids

UTC = timezone.utc


def _change(db, vid, at, *, result="success", ctype="apply"):
    c = Change(video_id=vid, change_type=ctype, previous_title="이전", new_title="새", result=result, mode="demo", applied_at=at if result == "success" else None, created_at=at)
    db.add(c)
    db.flush()
    return c


def test_tc_wb_041_interval_72h_boundary(seeded, env_free, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    t0 = clock()
    _change(seeded, vid, t0)
    just_before = check_video_limits(seeded, vid, t0 + timedelta(hours=72) - timedelta(seconds=1), env_free.policy, 10)
    assert [c.code for c in just_before.failures] == ["INTERVAL"]
    assert just_before.failures[0].retry_at == t0 + timedelta(hours=72)
    assert check_video_limits(seeded, vid, t0 + timedelta(hours=72), env_free.policy, 10).passed  # 정확히 72시간이면 통과


def test_tc_wb_042_max_three_changes_per_video(seeded, env_free, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    t0 = clock() - timedelta(days=30)
    for i in range(3):
        _change(seeded, vid, t0 + timedelta(days=i * 4))
    report = check_video_limits(seeded, vid, clock(), env_free.policy, 10)
    assert [c.code for c in report.failures] == ["COUNT"] and gather_facts(seeded, vid, clock()).change_count == 3
    assert summarize_limits(report) == {"allowed": False, "reasons": [report.failures[0].message], "next_allowed_at": None}  # 시간이 지나도 풀리지 않음
    _change(seeded, vid, clock() - timedelta(days=1), result="failed")  # 실패한 시도는 세지 않는다
    assert gather_facts(seeded, vid, clock()).change_count == 3


def test_tc_wb_043_min_impressions_fail_closed_then_ok_with_after_metrics(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    t0 = clock() - timedelta(days=10)
    _change(seeded, vid, t0)
    assert [c.code for c in check_video_limits(seeded, vid, clock(), env.policy, 10).failures] == ["IMPRESSIONS"]
    seeded.add(MetricsSnapshot(video_id=vid, taken_at=clock(), phase="after", source="demo", period_start=(t0 + timedelta(days=1)).date(), period_end=clock().date(), impressions=5000))
    seeded.flush()
    assert check_video_limits(seeded, vid, clock(), env.policy, 10).passed
    assert summarize_limits(check_video_limits(seeded, eligible_video_ids(seeded, 2)[1], clock(), env.policy, 10)) == {"allowed": True, "reasons": [], "next_allowed_at": None}


def test_tc_wb_044_daily_cap_counts_kst_day_boundary(seeded, env_free, clock):
    v = eligible_video_ids(seeded, 4)
    now = datetime(2026, 10, 10, 3, 0, tzinfo=UTC)               # KST 2026-10-10 12:00
    _change(seeded, v[0], datetime(2026, 10, 9, 14, 59, 59, tzinfo=UTC))  # KST 10-09 23:59:59 → 어제
    _change(seeded, v[1], datetime(2026, 10, 9, 15, 0, 0, tzinfo=UTC))    # KST 10-10 00:00:00 → 오늘
    _change(seeded, v[2], now - timedelta(hours=1), ctype="rollback")      # 롤백은 상한에 세지 않음
    _change(seeded, v[3], now - timedelta(hours=1), result="planned")      # 진행 중도 센다
    assert applied_today(seeded, now) == 2
    report = check_video_limits(seeded, eligible_video_ids(seeded, 5)[4], now, env_free.policy, 2)
    assert [c.code for c in report.failures] == ["DAILY"]
    assert report.failures[0].retry_at == datetime(2026, 10, 10, 15, 0, tzinfo=UTC)  # 다음 KST 자정
    assert check_video_limits(seeded, eligible_video_ids(seeded, 5)[4], now, env_free.policy, 3).passed


def test_tc_wb_045_quota_reserve_mark_and_remaining(seeded, env, clock):
    policy = env.policy
    st0 = quota_state(seeded, clock(), policy)
    assert (st0.used, st0.limit, st0.remaining, st0.warning) == (0, 6000, 6000, False)
    ids = reserve_calls(seeded, clock(), policy, [("videos.list", 1), ("videos.update", 50), ("videos.list", 1)])
    assert quota_state(seeded, clock(), policy).used == units_per_apply(policy) == 52
    mark_call(seeded, ids[0], "ok")
    mark_call(seeded, ids[1], "failed")
    rows = {r.id: r for r in seeded.execute(select(QuotaUsage)).scalars()}
    assert [rows[i].status for i in ids] == ["ok", "failed", "reserved"] and all(r.pt_date == date(2026, 10, 9) for r in rows.values())  # 태평양 시간 기준일
    with pytest.raises(ValueError):
        mark_call(seeded, ids[2], "reserved")


def test_tc_wb_046_quota_exhaustion_reserves_nothing_and_warns_at_80_percent(seeded, env, clock):
    tight = dataclasses.replace(env.policy, daily_limit_units=100)
    reserve_calls(seeded, clock(), tight, [("videos.update", 50)])
    st = quota_state(seeded, clock(), tight)
    assert st.warning is False
    reserve_calls(seeded, clock(), tight, [("videos.list", 30)])
    assert quota_state(seeded, clock(), tight).warning is True  # 80 / 100 = 경고 비율
    with pytest.raises(StepFailure) as e:
        reserve_calls(seeded, clock(), tight, [("videos.list", 1), ("videos.update", 50)])
    assert e.value.code == "quota_exhausted"
    assert len(seeded.execute(select(QuotaUsage)).scalars().all()) == 2  # 일부만 예약되지 않는다(전부 아니면 전무)
    reserve_calls(seeded, clock(), tight, [("videos.list", 20)])  # 정확히 상한까지는 허용
    assert quota_state(seeded, clock(), tight).remaining == 0


def test_tc_wb_047_release_only_unused_reservations(seeded, env, clock):
    ids = reserve_calls(seeded, clock(), env.policy, [("videos.list", 1), ("videos.update", 50), ("videos.list", 1)])
    mark_call(seeded, ids[0], "ok")
    mark_call(seeded, ids[1], "failed")
    release_unused(seeded, ids)
    rows = {r.id: r for r in seeded.execute(select(QuotaUsage)).scalars()}
    assert (rows[ids[0]].units, rows[ids[1]].units, rows[ids[2]].units) == (1, 50, 0)  # 호출한 것은 차감 유지, 안 쓴 것만 환원
    assert quota_state(seeded, clock(), env.policy).used == 51
    release_unused(seeded, [])


def test_tc_wb_048_quota_day_is_pacific_time(seeded, env):
    late = datetime(2026, 10, 10, 6, 59, tzinfo=UTC)    # PT 10-09 23:59
    early = datetime(2026, 10, 10, 7, 0, tzinfo=UTC)    # PT 10-10 00:00 (PDT)
    reserve_calls(seeded, late, env.policy, [("videos.update", 50)])
    assert quota_state(seeded, late, env.policy).used == 50
    assert quota_state(seeded, early, env.policy).used == 0 and quota_state(seeded, early, env.policy).pt_date == date(2026, 10, 10)
