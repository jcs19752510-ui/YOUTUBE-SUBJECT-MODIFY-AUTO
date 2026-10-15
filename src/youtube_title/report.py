"""변경 전후 성과 비교 리포트 계산(FR-018, POL-002, SCR-008).

- 계산은 순수 함수(`build_report`)이고, DB 조회(`load_video_data` 등)는 읽기 전용 SELECT만 쓴다(SEC-018: 바인딩만).
- **데이터가 부족하면 결론을 내지 않고 '데이터 부족'으로 표시한다**: 기준선(변경 전)·변경 후 자료 없음, 기간이 변경 시점과 겹침,
  노출수가 최소 기준 미달, 집계 기간이 너무 짧음, 기간 정보 없음, 변경 후 롤백됨.
- 수치를 나란히 놓을 뿐 제목 변경이 원인이라고 단정하지 않는다(면책 문구는 항상 출력).
- 네트워크 호출 없음.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from youtube_title.timeutil import parse_iso

MIN_PERIOD_DAYS = 7  # 집계 기간 최소 일수(가정, 임의 기본값)
LIMIT_NOTE = "순차 비교는 다른 요인(시기·노출 차이)의 영향을 받아 원인을 단정할 수 없습니다."
CAUSAL_NOTE = (
    "이 표는 변경 전과 후의 숫자를 나란히 놓은 것일 뿐, 제목 변경이 원인이라고 말하지 않습니다. "
    "계절·시기, 노출 위치 변화, 썸네일, 외부 유입, 공식 A/B 테스트 같은 다른 요인이 섞여 있을 수 있습니다."
)
INSUFFICIENT_LABEL = "데이터 부족"


@dataclass(frozen=True)
class Rules:
    min_impressions: int  # 변경 전·후 각각의 노출수 최소 기준(설정 cadence.min_impressions_before_rechange 재사용)
    min_period_days: int = MIN_PERIOD_DAYS
    evaluation_window_days: int = 14  # 변경 후 지표 수집 예정일 계산용(설정 sequential_mode.evaluation_window_days)

    @classmethod
    def from_settings(cls, settings) -> "Rules":
        return cls(settings.min_impressions_before_rechange, MIN_PERIOD_DAYS, settings.evaluation_window_days)


@dataclass(frozen=True)
class Snapshot:
    id: int
    taken_at: str
    phase: str
    source: str
    period_start: str | None
    period_end: str | None
    impressions: int | None
    ctr: float | None
    views: int | None
    watch_minutes: float | None


@dataclass(frozen=True)
class Change:
    id: int
    change_type: str  # apply | rollback
    previous_title: str
    new_title: str
    at: str  # 적용 시각(없으면 기록 시각), UTC ISO
    result: str
    approver: str | None = None


@dataclass(frozen=True)
class VideoData:
    video_id: str
    title: str | None
    changes: tuple[Change, ...]
    snapshots: tuple[Snapshot, ...]


@dataclass(frozen=True)
class MetricDelta:
    key: str
    label: str
    before: float | None
    after: float | None
    delta: float | None
    pct: float | None  # 변화율(%), 변경 전 값이 없거나 0이면 None


@dataclass(frozen=True)
class VideoReport:
    video_id: str
    title: str | None
    status: str  # no_change | insufficient | ok
    changes: tuple[Change, ...]
    target: Change | None
    before: Snapshot | None
    after: Snapshot | None
    baseline_missing: bool
    reasons: tuple[str, ...]
    notes: tuple[str, ...]
    metrics: tuple[MetricDelta, ...]
    expected_after_date: str | None


def load_video_data(conn: sqlite3.Connection, video_id: str) -> VideoData:
    """읽기 전용 조회. 성공한 변경(적용·롤백)과 모든 지표 스냅샷을 가져온다."""
    row = conn.execute("SELECT title FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    changes = tuple(
        Change(r["id"], r["change_type"], r["previous_title"], r["new_title"], r["at"], r["result"], r["approver"])
        for r in conn.execute(
            "SELECT id, change_type, previous_title, new_title, COALESCE(applied_at, created_at) AS at, result, approver "
            "FROM title_changes WHERE video_id = ? AND result = 'success' ORDER BY COALESCE(applied_at, created_at), id",
            (video_id,),
        )
    )
    snaps = tuple(
        Snapshot(r["id"], r["taken_at"], r["phase"], r["source"], r["period_start"], r["period_end"], r["impressions"], r["ctr"], r["views"], r["watch_minutes"])
        for r in conn.execute(
            "SELECT id, taken_at, phase, source, period_start, period_end, impressions, ctr, views, watch_minutes FROM metrics_snapshots WHERE video_id = ? ORDER BY taken_at, id",
            (video_id,),
        )
    )
    return VideoData(video_id, row["title"] if row else None, changes, snaps)


def list_changed_video_ids(conn: sqlite3.Connection) -> list[str]:
    """성공한 적용 기록이 있는 영상 ID(최근 변경 순)."""
    rows = conn.execute(
        "SELECT video_id FROM title_changes WHERE result = 'success' AND change_type = 'apply' GROUP BY video_id ORDER BY MAX(COALESCE(applied_at, created_at)) DESC, video_id"
    )
    return [r["video_id"] for r in rows]


def _ts(value: str | None) -> datetime | None:
    try:
        return parse_iso(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def _day(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def _period_days(s: Snapshot) -> int | None:
    start, end = _day(s.period_start), _day(s.period_end)
    if start is None or end is None or end < start:
        return None
    return (end - start).days + 1


def _before_ok(s: Snapshot, applied: datetime) -> bool:
    end = _day(s.period_end)
    if end is not None:
        return end < applied.date()  # 변경 당일분은 변경 후 자료가 섞일 수 있어 제외(엄격 비교)
    taken = _ts(s.taken_at)
    return taken is not None and taken <= applied


def _after_ok(s: Snapshot, applied: datetime) -> bool:
    start = _day(s.period_start)
    if start is not None:
        return start > applied.date()
    taken = _ts(s.taken_at)
    return taken is not None and taken >= applied


def _pick(cands: list[Snapshot], ok, applied: datetime, empty_reason: str, mismatch_reason: str, notes: list[str], reasons: list[str]) -> Snapshot | None:
    if not cands:
        reasons.append(empty_reason)
        return None
    valid = [s for s in cands if ok(s, applied)]
    if not valid:
        reasons.append(mismatch_reason)
        return None
    if len(valid) > 1:
        notes.append(f"같은 단계의 자료가 {len(valid)}건 있어 가장 최근 것을 썼습니다.")
    return max(valid, key=lambda s: (s.taken_at, s.id))


def _check_side(label: str, s: Snapshot, rules: Rules, reasons: list[str]) -> None:
    if s.impressions is None:
        reasons.append(f"{label} 노출수가 없습니다(API로 받지 못했다면 Studio CSV를 가져오세요).")
    elif s.impressions < rules.min_impressions:
        reasons.append(f"{label} 노출수 {s.impressions:,}회가 최소 기준 {rules.min_impressions:,}회보다 적습니다.")
    days = _period_days(s)
    if days is None:
        reasons.append(f"{label} 집계 기간 정보가 없어 기간을 확인할 수 없습니다.")
    elif days < rules.min_period_days:
        reasons.append(f"{label} 집계 기간 {days}일이 최소 기준 {rules.min_period_days}일보다 짧습니다.")


def _metric(key: str, label: str, b: float | None, a: float | None) -> MetricDelta:
    if b is None or a is None:
        return MetricDelta(key, label, b, a, None, None)
    return MetricDelta(key, label, b, a, a - b, ((a - b) / b * 100) if b else None)


def _compute_metrics(before: Snapshot, after: Snapshot) -> tuple[MetricDelta, ...]:
    bd, ad = _period_days(before), _period_days(after)  # 호출 전에 둘 다 None이 아님을 확인했다

    def rate(v, days):
        return None if v is None else v / days

    return (
        _metric("impressions", "노출수(하루 평균)", rate(before.impressions, bd), rate(after.impressions, ad)),
        _metric("ctr", "노출 클릭률(%)", before.ctr, after.ctr),
        _metric("views", "조회수(하루 평균)", rate(before.views, bd), rate(after.views, ad)),
        _metric("watch_minutes", "시청 시간(분, 하루 평균)", rate(before.watch_minutes, bd), rate(after.watch_minutes, ad)),
    )


def build_report(video_id: str, title: str | None, changes, snapshots, rules: Rules) -> VideoReport:
    """순수 함수: 입력을 바꾸지 않고 리포트 데이터를 계산한다. 데이터가 부족하면 status='insufficient'이고 수치 비교를 하지 않는다."""
    ordered = tuple(sorted((c for c in changes if c.result == "success"), key=lambda c: (c.at, c.id)))
    applies = [c for c in ordered if c.change_type == "apply"]
    if not applies:
        return VideoReport(video_id, title, "no_change", ordered, None, None, None, True, (), ("이 영상은 성공한 제목 변경 기록이 없어 비교할 수 없습니다.",), (), None)
    target = applies[-1]
    notes: list[str] = []
    reasons: list[str] = []
    if len(applies) > 1:
        notes.append(f"제목을 {len(applies)}번 바꿨습니다. 가장 최근 변경(번호 {target.id}) 기준으로 비교합니다.")
    if any(c.change_type == "rollback" and (c.at, c.id) > (target.at, target.id) for c in ordered):
        reasons.append("변경 뒤에 롤백(원래 제목 복원)이 있어 변경 후 자료가 두 제목에 걸쳐 섞였습니다.")
    applied = _ts(target.at)
    if applied is None:
        reasons.append("변경 시각을 해석할 수 없어 전후를 나눌 수 없습니다.")
        return VideoReport(video_id, title, "insufficient", ordered, target, None, None, True, tuple(reasons), tuple(notes), (), None)

    expected = (applied.date() + timedelta(days=rules.evaluation_window_days)).isoformat()
    cands_b = [s for s in snapshots if s.phase == "before"]
    cands_a = [s for s in snapshots if s.phase == "after"]
    before = _pick(cands_b, _before_ok, applied, "변경 전 지표(기준선)가 없습니다.", "변경 전 지표가 있지만 집계 기간이 변경 시점 이후와 겹치거나 변경 뒤에 수집되어 기준선으로 쓸 수 없습니다.", notes, reasons)
    after = _pick(cands_a, _after_ok, applied, "변경 후 지표가 아직 없습니다.", "변경 후 지표가 있지만 집계 기간이 변경 이전과 겹쳐 비교에 쓸 수 없습니다.", notes, reasons)
    if before is not None:
        _check_side("변경 전", before, rules, reasons)
    if after is not None:
        _check_side("변경 후", after, rules, reasons)
    baseline_missing = before is None
    if reasons:
        return VideoReport(video_id, title, "insufficient", ordered, target, before, after, baseline_missing, tuple(reasons), tuple(notes), (), expected if after is None else None)
    assert before is not None and after is not None
    return VideoReport(video_id, title, "ok", ordered, target, before, after, False, (), tuple(notes), _compute_metrics(before, after), None)
