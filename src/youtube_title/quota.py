"""쿼터 선예약과 일일 상한 검사(FR-015, SEC-002, NFR-003, ADR-008).

API를 부르기 전에 units를 먼저 예약해 DB에 남기고, 호출이 실패해도 차감은 되돌리지 않는다(보수적).
하루의 경계는 태평양 시간 자정이다(ADR-006).
"""
from __future__ import annotations

import sqlite3

from youtube_title.config import Settings
from youtube_title.errors import DatabaseError, InputError, QuotaError
from youtube_title.timeutil import pt_date, utc_iso

RESET_HINT = (
    "쿼터는 태평양 시간 자정에 초기화됩니다(한국 시간으로 서머타임 중이면 오후 4시, 아니면 오후 5시). "
    "그때 이후에 다시 실행하거나, 설정의 quota.daily_limit_units를 확인하세요."
)
_MARK_STATUSES = ("ok", "failed")


class QuotaManager:
    def __init__(self, conn: sqlite3.Connection, settings: Settings, clock) -> None:
        self._conn = conn
        self._settings = settings
        self._clock = clock

    @property
    def limit(self) -> int:
        return self._settings.daily_limit_units

    def today(self) -> str:
        return pt_date(self._clock.now()).isoformat()

    def used_today(self) -> int:
        """예약·성공·실패를 모두 합산한다. 실패한 호출도 구글 쪽에서는 쓰였을 수 있어 차감을 유지한다."""
        try:
            row = self._conn.execute("SELECT COALESCE(SUM(units), 0) FROM quota_usage WHERE pt_date = ?", (self.today(),)).fetchone()
        except sqlite3.Error as exc:
            raise _db_error(exc) from exc
        return int(row[0])

    def remaining(self) -> int:
        return max(0, self.limit - self.used_today())

    def is_warning(self) -> bool:
        """오늘 사용량이 경고 비율(warn_ratio) 이상인지."""
        return self.used_today() >= self.limit * self._settings.warn_ratio

    def reserve(self, method: str, units: int, run_id: str | None) -> int:
        """호출 전에 units를 예약하고 예약 ID를 돌려준다. 상한을 넘기면 DB에 아무것도 남기지 않고 QuotaError."""
        if not isinstance(method, str) or not method.strip():
            raise InputError("쿼터 예약에 호출 이름이 없습니다.", "프로그램 오류입니다. 로그를 확인하고 알려 주세요.")
        if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
            raise InputError(f"쿼터 예약 단위가 올바르지 않습니다: {units!r}", "설정의 quota 비용 값(read_cost 등)이 1 이상인지 확인하세요.")
        now = self._clock.now()
        day = pt_date(now).isoformat()
        try:
            with self._conn:
                # 합계 확인과 삽입을 한 문장으로 묶어 확인과 기록 사이에 틈이 없게 한다.
                cur = self._conn.execute(
                    "INSERT INTO quota_usage (pt_date, method, units, called_at, run_id, status) "
                    "SELECT ?, ?, ?, ?, ?, 'reserved' "
                    "WHERE (SELECT COALESCE(SUM(units), 0) FROM quota_usage WHERE pt_date = ?) + ? <= ?",
                    (day, method, units, utc_iso(now), run_id, day, units, self.limit),
                )
                reserve_id = cur.lastrowid if cur.rowcount == 1 else None
        except sqlite3.Error as exc:
            raise _db_error(exc) from exc
        if reserve_id is None:
            used = self.used_today()
            raise QuotaError(
                f"오늘 쿼터 상한을 넘게 되어 호출하지 않았습니다(사용 {used} + 필요 {units} > 상한 {self.limit} units).",
                RESET_HINT,
            )
        return reserve_id

    def mark(self, reserve_id: int, status: str) -> None:
        """호출 결과를 기록한다. 'failed'여도 units는 그대로 차감된다."""
        if status not in _MARK_STATUSES:
            raise ValueError(f"알 수 없는 쿼터 상태: {status!r}")
        try:
            with self._conn:
                cur = self._conn.execute("UPDATE quota_usage SET status = ? WHERE id = ? AND status = 'reserved'", (status, reserve_id))
        except sqlite3.Error as exc:
            raise _db_error(exc) from exc
        if cur.rowcount != 1:
            raise ValueError(f"예약 기록을 찾을 수 없거나 이미 처리됨: {reserve_id!r}")


def _db_error(exc: sqlite3.Error) -> DatabaseError:
    return DatabaseError("쿼터 기록을 읽거나 쓰지 못했습니다.", "data 폴더의 쓰기 권한과 디스크 공간을 확인하세요.", cause=type(exc).__name__)
