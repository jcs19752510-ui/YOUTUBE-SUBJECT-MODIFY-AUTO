"""교체 한도와 API 쿼터(WEB_DESIGN §4-3). 판정은 ytitle.limits.evaluate_limits 를 그대로 쓰고, 여기서는 DB 사실 수집과 쿼터 기록만 한다.

- 영상별 간격(72시간)·횟수(3회)·최소 노출수는 기존 정책(settings.yaml) 값이다.
- 하루 반영 상한은 웹 설정(daily_apply_cap, KST 하루)이라 evaluate_limits 의 DAILY 검사에는 이 값을 넣어 쓴다.
- 쿼터의 하루는 태평양 시간 날짜(quota_usage.pt_date)다. 실패한 호출도 차감을 유지하고, 호출하지 않은 예약만 풀어 준다.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session
from ytitle.config import Settings
from ytitle.limits import LimitFacts, LimitReport, evaluate_limits

from ytweb.core.clock import kst_today, pt_date
from ytweb.db.models import Change, MetricsSnapshot, QuotaUsage
from ytweb.domain.common import StepFailure, kst_day_bounds

COUNTED_RESULTS = ("success", "planned")  # 변경이 일어났거나 일어났을 수 있는 행
_QUOTA_LOCK_KEY = 7_340_002


def _change_time():
    return func.coalesce(Change.applied_at, Change.created_at)


def applied_today(session: Session, now: datetime) -> int:
    """오늘(KST) 반영한 건수. 진행 중(planned)도 센다 — 같은 상한을 두 번 쓰지 않게."""
    start, end = kst_day_bounds(kst_today(now))
    stmt = select(func.count()).select_from(Change).where(
        Change.change_type == "apply", Change.result.in_(COUNTED_RESULTS), _change_time() >= start, _change_time() < end
    )
    return int(session.execute(stmt).scalar_one())


def gather_facts(session: Session, video_id: str, now: datetime) -> LimitFacts:
    base = (Change.video_id == video_id, Change.result.in_(COUNTED_RESULTS))
    count = int(session.execute(select(func.count()).select_from(Change).where(*base)).scalar_one())
    last_at = session.execute(select(func.max(_change_time())).where(*base)).scalar_one()
    impressions = None
    if last_at is not None:
        # 변경 시각 날짜보다 뒤에서 시작하는 기간의 지표만 인정한다(변경 이전 시간이 섞인 기간 제외, ytitle.limits 와 같은 보수 규칙).
        stmt = select(func.max(MetricsSnapshot.impressions)).where(
            MetricsSnapshot.video_id == video_id,
            MetricsSnapshot.phase.in_(("after", "periodic")),
            MetricsSnapshot.impressions.is_not(None),
            MetricsSnapshot.period_start.is_not(None),
            MetricsSnapshot.period_start > last_at.date(),
            MetricsSnapshot.taken_at >= last_at,
        )
        value = session.execute(stmt).scalar_one()
        impressions = None if value is None else int(value)
    _, next_day = kst_day_bounds(kst_today(now))
    return LimitFacts(last_at, count, impressions, applied_today(session, now), next_day)


def check_video_limits(session: Session, video_id: str, now: datetime, policy: Settings, cap: int) -> LimitReport:
    effective = dataclasses.replace(policy, max_live_changes_per_day=cap)
    return evaluate_limits(gather_facts(session, video_id, now), effective, now)


def summarize_limits(report: LimitReport) -> dict:
    retry = [c.retry_at for c in report.failures if c.retry_at is not None]
    return {
        "allowed": report.passed,
        "reasons": [c.message for c in report.failures],
        "next_allowed_at": max(retry) if retry and len(retry) == len(report.failures) else None,
    }


# ───────────── 쿼터 ─────────────

@dataclass(frozen=True)
class QuotaState:
    used: int
    limit: int
    remaining: int
    pt_date: date
    warning: bool


def used_today(session: Session, now: datetime) -> int:
    value = session.execute(select(func.coalesce(func.sum(QuotaUsage.units), 0)).where(QuotaUsage.pt_date == pt_date(now))).scalar_one()
    return int(value)


def quota_state(session: Session, now: datetime, policy: Settings) -> QuotaState:
    used = used_today(session, now)
    return QuotaState(used, policy.daily_limit_units, max(0, policy.daily_limit_units - used), pt_date(now), used >= policy.daily_limit_units * policy.warn_ratio)


def units_per_apply(policy: Settings) -> int:
    """반영 1건의 쿼터: 직전 재조회 1회 + 갱신 1회 + 검증 재조회 1회."""
    return policy.update_cost + 2 * policy.read_cost


def reserve_calls(session: Session, now: datetime, policy: Settings, calls: list[tuple[str, int]], job_id: str | None = None) -> list[int]:
    """호출 전에 필요한 쿼터를 전부 예약한다(전부 되거나 하나도 안 됨). 부족하면 아무것도 남기지 않고 StepFailure(quota_exhausted)."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _QUOTA_LOCK_KEY})  # 워커 둘이 같은 잔여를 동시에 쓰지 않게
    need = sum(units for _, units in calls)
    used = used_today(session, now)
    if used + need > policy.daily_limit_units:
        raise StepFailure("quota_exhausted", f"오늘 API 쿼터가 부족해 호출하지 않았습니다(사용 {used} + 필요 {need} > 상한 {policy.daily_limit_units} 단위).")
    day = pt_date(now)
    rows = [QuotaUsage(pt_date=day, method=m, units=u, called_at=now, job_id=job_id, status="reserved") for m, u in calls]
    session.add_all(rows)
    session.flush()
    return [r.id for r in rows]


def mark_call(session: Session, reservation_id: int, status: str) -> None:
    if status not in ("ok", "failed"):
        raise ValueError(f"알 수 없는 쿼터 상태: {status!r}")
    session.execute(update(QuotaUsage).where(QuotaUsage.id == reservation_id, QuotaUsage.status == "reserved").values(status=status))
    session.flush()


def release_unused(session: Session, reservation_ids: list[int]) -> None:
    """호출하지 않은 예약만 0으로 풀어 준다. 호출했다가 실패한 것(failed)은 차감을 유지한다."""
    if reservation_ids:
        session.execute(update(QuotaUsage).where(QuotaUsage.id.in_(reservation_ids), QuotaUsage.status == "reserved").values(units=0, status="failed"))
        session.flush()


def next_kst_midnight(now: datetime) -> datetime:
    return kst_day_bounds(kst_today(now))[1]


def days_ahead(today: date, n: int) -> date:
    return today + timedelta(days=n)
