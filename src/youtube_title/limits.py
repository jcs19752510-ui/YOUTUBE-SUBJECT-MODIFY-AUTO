"""교체 제한 검사(FR-014, SEC-004, SEC-020). 값이 불확실하면 항상 거부 쪽(fail-closed)으로 판정한다.

구조: DB에서 사실(`LimitFacts`)을 모으는 함수와, 사실만으로 판정하는 순수 함수(`evaluate_limits`)로 나눠
경계값을 DB 없이 정확히 시험할 수 있게 했다. 이 모듈은 DB를 읽기만 하며 아무것도 쓰지 않는다.

판정 기준(설정값은 DESIGN 5-3 `cadence`):
- INTERVAL  : 같은 영상의 직전 변경으로부터 `min_interval_hours` 이상 지났는가(정확히 같으면 통과)
- COUNT     : 같은 영상의 변경 횟수가 `max_changes_per_video` 미만인가
- IMPRESSIONS: 한 번이라도 바꾼 영상은 '변경 이후 기간'의 노출수가 `min_impressions_before_rechange` 이상인가.
               노출수를 모르면(기록 없음·API 미제공) 거부한다.
- DAILY     : 오늘(태평양 시간 날짜, 쿼터와 같은 '하루') 적용 건수가 `max_live_changes_per_day` 미만인가

'변경'으로 세는 행: `title_changes.result`가 `success`(성공) 또는 `planned`(결과 미확정 시도)인 행.
미확정 시도는 실제로 제목이 바뀌었는지 알 수 없으므로 보수적으로 변경으로 본다. `failed`·`aborted`는 세지 않는다.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from youtube_title.config import Settings
from youtube_title.errors import DatabaseError
from youtube_title.timeutil import parse_iso, pt_date, pt_zone, utc_iso

KST = timezone(timedelta(hours=9))
COUNTED_RESULTS = ("success", "planned")

INTERVAL = "INTERVAL"
COUNT = "COUNT"
IMPRESSIONS = "IMPRESSIONS"
DAILY = "DAILY"


@dataclass(frozen=True)
class LimitFacts:
    """DB에서 모은 사실. 판정 함수는 이 값과 설정, 현재 시각만 본다."""

    last_change_at: datetime | None     # 같은 영상의 직전 변경 시각(UTC)
    change_count: int                   # 같은 영상의 변경 횟수
    impressions_since_change: int | None  # 직전 변경 이후 기간의 노출수(모르면 None)
    changes_today: int                  # 오늘(PT 날짜) 전체 영상의 적용 건수
    next_day_start: datetime            # 다음 PT 자정(UTC)


@dataclass(frozen=True)
class LimitCheck:
    code: str
    label: str
    passed: bool
    message: str
    retry_at: datetime | None = None    # 다시 시도할 수 있는 가장 이른 시각(알 수 있을 때만)


@dataclass(frozen=True)
class LimitReport:
    checks: tuple[LimitCheck, ...]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> tuple[LimitCheck, ...]:
        return tuple(c for c in self.checks if not c.passed)


def format_kst(moment: datetime) -> str:
    """사용자 화면용 한국 시간 `YYYY-MM-DD HH:MM`(UX 설계 3장)."""
    return moment.astimezone(KST).strftime("%Y-%m-%d %H:%M") + " (한국 시간)"


def _db_error(exc: Exception) -> DatabaseError:
    return DatabaseError("교체 제한 검사에 필요한 이력을 읽지 못했습니다.", "data 폴더의 DB 파일이 손상되지 않았는지 확인하세요.", cause=type(exc).__name__)


def _parse_ts(value: object) -> datetime:
    try:
        return parse_iso(str(value))
    except ValueError as exc:
        raise DatabaseError("변경 이력의 시각 형식이 올바르지 않아 교체 제한을 확인할 수 없습니다.", "data 폴더의 DB 파일을 점검하세요(안전을 위해 거부합니다).", cause="시각 형식 이상") from exc


def _pt_day_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """moment가 속한 태평양 시간 하루의 [시작, 끝) 경계를 UTC로 돌려준다(서머타임 전환일도 정확히)."""
    zone = pt_zone()
    day: date = pt_date(moment)
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    return start, end


def gather_facts(conn: sqlite3.Connection, video_id: str, now: datetime) -> LimitFacts:
    """DB를 읽어 사실을 모은다. 모든 SQL은 파라미터 바인딩이다(SEC-018)."""
    placeholders = ",".join("?" for _ in COUNTED_RESULTS)
    day_start, day_end = _pt_day_bounds(now)
    try:
        count = conn.execute(
            f"SELECT COUNT(*) FROM title_changes WHERE video_id = ? AND result IN ({placeholders})",
            (video_id, *COUNTED_RESULTS),
        ).fetchone()[0]
        last = conn.execute(
            f"SELECT COALESCE(applied_at, created_at) AS ts FROM title_changes WHERE video_id = ? AND result IN ({placeholders}) "
            "ORDER BY COALESCE(applied_at, created_at) DESC, id DESC LIMIT 1",
            (video_id, *COUNTED_RESULTS),
        ).fetchone()
        today = conn.execute(
            f"SELECT COUNT(*) FROM title_changes WHERE change_type = 'apply' AND result IN ({placeholders}) "
            "AND COALESCE(applied_at, created_at) >= ? AND COALESCE(applied_at, created_at) < ?",
            (*COUNTED_RESULTS, utc_iso(day_start), utc_iso(day_end)),
        ).fetchone()[0]
        last_at = _parse_ts(last[0]) if last else None
        impressions = None
        if last_at is not None:
            # 변경 시각이 속한 날짜(UTC)보다 '뒤에서 시작하는' 기간의 지표만 인정한다. 태평양 날짜는 UTC 날짜보다 늦지 않으므로
            # 이 기준은 변경 이전 시간이 섞인 기간을 확실히 제외한다(보수적). 기간 시작일이 없는 지표도 제외된다.
            row = conn.execute(
                "SELECT MAX(impressions) FROM metrics_snapshots WHERE video_id = ? AND phase IN ('after','periodic') "
                "AND impressions IS NOT NULL AND period_start IS NOT NULL AND period_start > ? AND taken_at >= ?",
                (video_id, last_at.date().isoformat(), utc_iso(last_at)),
            ).fetchone()
            impressions = None if row[0] is None else int(row[0])
    except sqlite3.Error as exc:
        raise _db_error(exc) from exc
    return LimitFacts(last_at, int(count), impressions, int(today), day_end)


def evaluate_limits(facts: LimitFacts, settings: Settings, now: datetime) -> LimitReport:
    """사실만으로 4가지 제한을 판정한다(순수 함수). 하나라도 실패하면 `LimitReport.passed`는 False다."""
    checks: list[LimitCheck] = []

    # 1) 최소 간격
    if facts.last_change_at is None:
        checks.append(LimitCheck(INTERVAL, "최소 간격", True, "이전 변경 기록이 없습니다."))
    else:
        ready = facts.last_change_at + timedelta(hours=settings.min_interval_hours)
        if now >= ready:
            checks.append(LimitCheck(INTERVAL, "최소 간격", True, f"직전 변경({format_kst(facts.last_change_at)}) 후 {settings.min_interval_hours}시간이 지났습니다."))
        else:
            checks.append(LimitCheck(INTERVAL, "최소 간격", False, f"직전 변경({format_kst(facts.last_change_at)}) 후 {settings.min_interval_hours}시간이 지나지 않았습니다. {format_kst(ready)} 이후에 가능합니다.", ready))

    # 2) 영상별 변경 횟수
    cap = settings.max_changes_per_video
    if facts.change_count < cap:
        checks.append(LimitCheck(COUNT, "변경 횟수", True, f"이 영상의 변경 {facts.change_count}회 / 상한 {cap}회"))
    else:
        checks.append(LimitCheck(COUNT, "변경 횟수", False, f"이 영상은 이미 {facts.change_count}회 변경되어 상한({cap}회)에 도달했습니다. 시간이 지나도 풀리지 않습니다. 더 바꾸려면 설정 파일(config/settings.yaml)의 영상당 변경 횟수 상한(cadence.max_changes_per_video)을 늘려야 합니다."))

    # 3) 최소 노출수(재변경에만 적용)
    need = settings.min_impressions_before_rechange
    if facts.change_count == 0 or need <= 0:
        checks.append(LimitCheck(IMPRESSIONS, "최소 노출수", True, "처음 변경이므로 노출수 조건이 없습니다." if facts.change_count == 0 else "최소 노출수 조건이 꺼져 있습니다(0)."))
    elif facts.impressions_since_change is None:
        checks.append(LimitCheck(IMPRESSIONS, "최소 노출수", False, f"직전 변경 이후 기간의 노출수 기록이 없어 확인할 수 없습니다(안전을 위해 거부). `fetch --metrics --phase after`로 지표를 가져오거나 Studio 내보내기 CSV를 가져오세요. 필요 노출수: {need}회 이상."))
    elif facts.impressions_since_change >= need:
        checks.append(LimitCheck(IMPRESSIONS, "최소 노출수", True, f"변경 이후 노출수 {facts.impressions_since_change}회 / 필요 {need}회"))
    else:
        checks.append(LimitCheck(IMPRESSIONS, "최소 노출수", False, f"변경 이후 노출수가 {facts.impressions_since_change}회로 필요한 {need}회에 못 미칩니다. 노출이 더 쌓인 뒤 지표를 다시 가져오세요."))

    # 4) 하루 적용 건수
    daily = settings.max_live_changes_per_day
    if facts.changes_today < daily:
        checks.append(LimitCheck(DAILY, "하루 적용 건수", True, f"오늘(태평양 시간 기준) 적용 {facts.changes_today}건 / 상한 {daily}건"))
    else:
        checks.append(LimitCheck(DAILY, "하루 적용 건수", False, f"오늘(태평양 시간 기준) 이미 {facts.changes_today}건을 적용해 하루 상한({daily}건)에 도달했습니다. {format_kst(facts.next_day_start)} 이후에 가능합니다.", facts.next_day_start))

    return LimitReport(tuple(checks))


def check_limits(conn: sqlite3.Connection, settings: Settings, video_id: str, now: datetime) -> LimitReport:
    """영상 하나의 교체 제한을 DB 이력으로 검사한다. 읽기 전용."""
    return evaluate_limits(gather_facts(conn, video_id, now), settings, now)
