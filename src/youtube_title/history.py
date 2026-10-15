"""변경 이력(`title_changes`) 기록·조회와 롤백 계획·DB 처리(FR-010, FR-011, SEC-006, NFR-008).

이 모듈은 DB만 다룬다. YouTube를 호출하지 않으며, 호출은 WU-5 `live_guard`가 한다.
`title_changes` 행의 흐름: `planned`(호출 직전 기록) → `success` / `failed` / `aborted` (끝난 행은 다시 바꾸지 않는다, 감사 기록).
후보 상태 전이는 DESIGN 3-2 상태 머신에 있는 것만 허용한다. 승인 정보(승인자·승인 시각·상태 `approved`)가 없으면 이력 행을 만들지 않는다.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from youtube_title.config import Settings
from youtube_title.errors import DatabaseError, InputError, SafetyGateError
from youtube_title.limits import check_limits
from youtube_title.timeutil import utc_iso
from youtube_title.updater import Plan, build_update_body, canonical_json, compute_plan_hash, is_stale, load_video_row, parse_snippet, snippet_hash, validate_new_title

# DESIGN 3-2. blocked·rolled_back은 종료 상태(나가는 전이 없음).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "candidate": frozenset({"filtered", "blocked"}),
    "filtered": frozenset({"approved"}),
    "approved": frozenset({"applied"}),
    "applied": frozenset({"evaluated", "rolled_back"}),
    "evaluated": frozenset({"rolled_back"}),
    "blocked": frozenset(),
    "rolled_back": frozenset(),
}
FINISH_RESULTS = ("success", "failed", "aborted")
_PENDING = ("success", "planned")   # '변경이 일어났거나 일어났을 수 있는' 행(limits.COUNTED_RESULTS와 같다)


def _db_error(exc: Exception, what: str = "변경 이력을 처리하지 못했습니다.") -> DatabaseError:
    return DatabaseError(what, "data 폴더의 쓰기 권한과 디스크 공간, DB 파일 상태를 확인하세요.", cause=type(exc).__name__)


def _need_text(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SafetyGateError(f"{what} 정보가 없어 기록하지 않았습니다.", "사람의 승인 정보 없이는 변경 이력을 만들 수 없습니다(SEC-001).")
    return value.strip()


def _need_aware(value: object, what: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise SafetyGateError(f"{what} 정보가 없어 기록하지 않았습니다.", "시간대가 있는 시각이 필요합니다.")
    return value


# ───────────── 후보 상태 전이 ─────────────

def _transition(conn: sqlite3.Connection, candidate_id: int, target: str, now: datetime) -> None:
    """커밋하지 않는 전이(호출한 쪽의 트랜잭션 안에서 쓴다). 허용되지 않은 전이는 예외."""
    row = conn.execute("SELECT status FROM title_candidates WHERE id = ?", (candidate_id,)).fetchone()
    if row is None:
        raise InputError(f"후보 번호 {candidate_id}번이 없습니다.", "후보번호를 확인하세요.")
    current = row[0]
    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise SafetyGateError(f"후보 {candidate_id}번의 상태를 '{current}'에서 '{target}'로 바꿀 수 없습니다.", "허용된 순서(검증 → 승인 → 적용 → 평가/롤백)만 가능합니다.")
    cur = conn.execute("UPDATE title_candidates SET status = ?, updated_at = ? WHERE id = ? AND status = ?", (target, utc_iso(now), candidate_id, current))
    if cur.rowcount != 1:  # 다른 실행이 먼저 바꾼 경우
        raise SafetyGateError(f"후보 {candidate_id}번의 상태가 방금 바뀌어 중단했습니다.", "상태를 다시 확인한 뒤 시도하세요.")


def transition_candidate(conn: sqlite3.Connection, candidate_id: int, target: str, now: datetime) -> None:
    try:
        with conn:
            _transition(conn, candidate_id, target, now)
    except sqlite3.Error as exc:
        raise _db_error(exc) from exc


# ───────────── 조회 ─────────────

def get_change(conn: sqlite3.Connection, change_id: int) -> sqlite3.Row:
    try:
        row = conn.execute("SELECT * FROM title_changes WHERE id = ?", (change_id,)).fetchone()
    except sqlite3.Error as exc:
        raise _db_error(exc) from exc
    if row is None:
        raise InputError(f"변경 번호 {change_id}번이 없습니다.", "변경 번호는 `apply` 결과나 이력에서 확인하세요.")
    return row


def list_changes(conn: sqlite3.Connection, video_id: str | None = None, limit: int = 50) -> list[sqlite3.Row]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise InputError("조회 건수는 1 이상이어야 합니다.", "limit 값을 확인하세요.")
    try:
        if video_id is None:
            return conn.execute("SELECT * FROM title_changes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return conn.execute("SELECT * FROM title_changes WHERE video_id = ? ORDER BY id DESC LIMIT ?", (video_id, limit)).fetchall()
    except sqlite3.Error as exc:
        raise _db_error(exc) from exc


def _later_change(conn: sqlite3.Connection, video_id: str, change_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM title_changes WHERE video_id = ? AND id > ? AND result IN (?, ?) ORDER BY id LIMIT 1",
        (video_id, change_id, *_PENDING),
    ).fetchone()
    return None if row is None else int(row[0])


# ───────────── 적용 기록 ─────────────

def begin_change(conn: sqlite3.Connection, settings: Settings, plan: Plan, *, approver: str, approved_at: datetime, run_id: str | None, now: datetime, reason: str | None = None) -> int:
    """호출 직전(DESIGN 5-2 11단계)에 `planned` 행을 만들고 변경 번호를 돌려준다. 백업 snippet 전체를 함께 저장한다(SEC-005).

    다음이 모두 맞지 않으면 아무것도 쓰지 않고 `SafetyGateError`: 승인자·승인 시각 있음, 후보 상태가 `approved`, 후보와 계획이 일치,
    계획 해시가 내용과 일치, 교체 제한 통과(방어를 한 겹 더 둔 것이며 WU-5의 5단계 검사를 대체하지 않는다).
    """
    approver = _need_text(approver, "승인자")
    approved_at = _need_aware(approved_at, "승인 시각")
    try:
        cand = conn.execute("SELECT video_id, candidate_title, status FROM title_candidates WHERE id = ?", (plan.candidate_id,)).fetchone()
    except sqlite3.Error as exc:
        raise _db_error(exc) from exc
    if cand is None or cand["status"] != "approved":
        raise SafetyGateError(f"후보 {plan.candidate_id}번이 승인 상태가 아니어서 변경 이력을 만들지 않았습니다.", "`approve`로 사람의 승인을 먼저 받으세요.")
    if cand["video_id"] != plan.video_id or cand["candidate_title"] != plan.new_title:
        raise SafetyGateError("승인된 후보와 계획의 내용이 달라 중단했습니다.", "plan부터 다시 하세요.")
    if compute_plan_hash(plan.video_id, plan.candidate_id, plan.previous_title, plan.new_title, plan.snippet) != plan.plan_hash:
        raise SafetyGateError("계획 해시가 계획 내용과 맞지 않아 중단했습니다.", "plan부터 다시 하세요.")
    report = check_limits(conn, settings, plan.video_id, now)
    if not report.passed:
        raise SafetyGateError("교체 제한을 통과하지 못해 변경 이력을 만들지 않았습니다: " + " / ".join(c.message for c in report.failures), "제한이 풀리는 시각에 다시 시도하세요.")
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO title_changes (video_id, candidate_id, change_type, previous_title, new_title, backup_snippet_json, reason, approver, approved_at, plan_hash, result, run_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (plan.video_id, plan.candidate_id, "apply", plan.previous_title, plan.new_title, canonical_json(plan.snippet), reason, approver, utc_iso(approved_at), plan.plan_hash, "planned", run_id, utc_iso(now)),
            )
            return int(cur.lastrowid)
    except sqlite3.Error as exc:
        raise _db_error(exc) from exc


def record_aborted(conn: sqlite3.Connection, *, change_type: str, video_id: str, candidate_id: int | None, previous_title: str, new_title: str, plan_hash: str | None, error_code: str, reason: str, run_id: str | None, now: datetime, approver: str | None = None) -> int:
    """안전 게이트 1~10단계에서 막힌 시도를 `aborted` 행으로 남긴다(감사). 상태 전이는 일으키지 않는다."""
    if change_type not in ("apply", "rollback"):
        raise InputError(f"알 수 없는 변경 종류: {change_type!r}", "프로그램 오류입니다. 로그를 확인하세요.")
    error_code = _need_text(error_code, "중단 사유 코드")
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO title_changes (video_id, candidate_id, change_type, previous_title, new_title, reason, approver, plan_hash, result, error_code, run_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (video_id, candidate_id, change_type, previous_title, new_title, reason, approver, plan_hash, "aborted", error_code, run_id, utc_iso(now)),
            )
            return int(cur.lastrowid)
    except sqlite3.Error as exc:
        raise _db_error(exc) from exc


def finish_change(conn: sqlite3.Connection, change_id: int, result: str, now: datetime, *, error_code: str | None = None, verify_result: dict | None = None) -> None:
    """`planned` 행을 끝낸다. 이력 행 갱신과 후보 상태 전이는 한 트랜잭션이라 둘 다 되거나 둘 다 안 된다.

    success: 적용이면 후보 approved→applied, 롤백이면 후보 applied/evaluated→rolled_back. failed·aborted는 후보 상태를 바꾸지 않는다.
    이미 끝난 행(planned가 아님)은 바꿀 수 없다.
    """
    if result not in FINISH_RESULTS:
        raise InputError(f"알 수 없는 결과 값입니다: {result!r}", "success, failed, aborted 중 하나여야 합니다.")
    if result != "success":
        error_code = _need_text(error_code, "실패 사유 코드")
    row = get_change(conn, change_id)
    if row["result"] != "planned":
        raise SafetyGateError(f"변경 {change_id}번은 이미 끝난 기록이라 바꿀 수 없습니다(결과: {row['result']}).", "감사 기록은 수정하지 않습니다. 새 시도는 새 기록으로 남깁니다.")
    stamp = utc_iso(now)
    verified = canonical_json(verify_result) if verify_result is not None else None
    try:
        with conn:
            cur = conn.execute(
                "UPDATE title_changes SET result = ?, error_code = ?, applied_at = ?, verified_at = ?, verify_result_json = ? WHERE id = ? AND result = 'planned'",
                (result, error_code, stamp if result == "success" else None, stamp if verified is not None else None, verified, change_id),
            )
            if cur.rowcount != 1:
                raise SafetyGateError(f"변경 {change_id}번의 상태가 방금 바뀌어 중단했습니다.", "이력을 다시 확인하세요.")
            if result == "success" and row["candidate_id"] is not None:
                if row["change_type"] == "apply":
                    _transition(conn, row["candidate_id"], "applied", now)
                else:
                    _transition(conn, row["candidate_id"], "rolled_back", now)
    except sqlite3.Error as exc:
        raise _db_error(exc) from exc


# ───────────── 롤백 계획 ─────────────

@dataclass(frozen=True)
class RollbackPlan:
    change_id: int
    candidate_id: int | None
    video_id: str
    current_title: str          # 지금(마지막 fetch 기준) 제목
    restore_title: str          # 적용 직전의 원래 제목(백업 snippet)
    snippet: dict               # 지금(마지막 fetch 기준) snippet 전체. 롤백 본문의 재료
    snippet_sha256: str
    backup_snippet: dict
    plan_hash: str
    body: dict
    changed_since_backup: tuple[str, ...]   # 백업과 지금이 달라진 제목 외 항목(사람이 Studio에서 고친 것 등)
    current_matches_applied: bool           # 지금 제목이 우리가 적용한 제목과 같은가
    fetched_at: str
    stale: bool


def _rollback_candidate_ok(conn: sqlite3.Connection, candidate_id: int | None) -> None:
    if candidate_id is None:
        return
    row = conn.execute("SELECT status FROM title_candidates WHERE id = ?", (candidate_id,)).fetchone()
    if row is None or row[0] not in ("applied", "evaluated"):
        raise SafetyGateError(f"후보 {candidate_id}번의 상태가 롤백할 수 있는 상태(applied/evaluated)가 아닙니다.", "이미 롤백되었거나 적용되지 않은 후보입니다.")


def plan_rollback(conn: sqlite3.Connection, settings: Settings, clock, change_id: int) -> RollbackPlan:
    """성공한 적용 변경 하나를 되돌리는 계획을 만든다(읽기 전용). 원래 제목은 백업 snippet에서 가져온다.

    안전 규칙: ① 적용(apply)이고 성공한 변경만 ② 백업이 읽히고 이력과 일치 ③ 그 영상의 가장 최근 변경일 때만(이후 변경이 있으면 거부,
    오래된 제목으로 최신 제목을 덮는 사고와 이중 롤백 방지) ④ 롤백 본문은 지금 저장된 snippet 전체 + 제목만 원래 제목으로 교체.
    교체 제한(72시간·횟수·노출수·하루 건수)은 사고 복구를 막지 않도록 롤백에는 적용하지 않는다.
    """
    row = get_change(conn, change_id)
    if row["change_type"] != "apply":
        raise SafetyGateError(f"변경 {change_id}번은 롤백 기록이라 다시 롤백할 수 없습니다.", "되돌릴 적용 변경 번호를 지정하세요.")
    if row["result"] != "success":
        raise SafetyGateError(f"변경 {change_id}번은 성공한 적용이 아니어서(결과: {row['result']}) 롤백 대상이 아닙니다.", "성공한 적용 변경 번호를 지정하세요.")
    video_id = row["video_id"]
    try:
        backup = json.loads(row["backup_snippet_json"]) if row["backup_snippet_json"] else None
    except ValueError:
        backup = None
    if not isinstance(backup, dict) or not isinstance(backup.get("title"), str) or backup["title"] != row["previous_title"]:
        raise SafetyGateError(f"변경 {change_id}번의 백업 snippet이 없거나 이력과 맞지 않아 롤백 계획을 만들 수 없습니다.", "DB 백업 사본(data/backups)에서 복구하거나 Studio에서 직접 되돌리세요.")
    later = _later_change(conn, video_id, change_id)
    if later is not None:
        raise SafetyGateError(f"변경 {change_id}번 이후에 같은 영상의 다른 변경(#{later})이 있어 롤백할 수 없습니다.", f"가장 최근 변경(#{later})부터 확인하세요. 이미 롤백했다면 더 할 일이 없습니다.")
    _rollback_candidate_ok(conn, row["candidate_id"])

    vrow = load_video_row(conn, video_id)
    snippet = parse_snippet(vrow["snippet_json"], video_id)
    restore_title = validate_new_title(backup["title"], settings, check_length=False)
    if snippet["title"] == restore_title:
        raise InputError("현재 제목이 이미 원래 제목과 같아 되돌릴 내용이 없습니다.", f"최신 상태가 맞는지 `fetch --video {video_id}`로 확인하세요.")
    changed = tuple(sorted(k for k in set(backup) | set(snippet) if k != "title" and backup.get(k) != snippet.get(k)))
    now = clock.now()
    return RollbackPlan(
        change_id=change_id,
        candidate_id=row["candidate_id"],
        video_id=video_id,
        current_title=snippet["title"],
        restore_title=restore_title,
        snippet=snippet,
        snippet_sha256=snippet_hash(snippet),
        backup_snippet=backup,
        plan_hash=compute_plan_hash(video_id, row["candidate_id"], snippet["title"], restore_title, snippet, kind="rollback", change_id=change_id),
        body=build_update_body(video_id, snippet, restore_title),
        changed_since_backup=changed,
        current_matches_applied=snippet["title"] == row["new_title"],
        fetched_at=str(vrow["fetched_at"]),
        stale=is_stale(vrow["fetched_at"], now),
    )


def begin_rollback(conn: sqlite3.Connection, plan: RollbackPlan, *, approver: str, typed_video_id: str, run_id: str | None, now: datetime) -> int:
    """롤백 호출 직전에 `planned` 롤백 행을 만든다. 사람이 영상 ID를 직접 입력해 확인했을 때만(DESIGN 4-1 EVT-007)."""
    approver = _need_text(approver, "확인자")
    if typed_video_id != plan.video_id:
        raise SafetyGateError("입력한 영상 ID가 대상과 달라 롤백 기록을 만들지 않았습니다.", "대상 영상 ID를 그대로 입력하세요.")
    if compute_plan_hash(plan.video_id, plan.candidate_id, plan.current_title, plan.restore_title, plan.snippet, kind="rollback", change_id=plan.change_id) != plan.plan_hash:
        raise SafetyGateError("롤백 계획 해시가 내용과 맞지 않아 중단했습니다.", "rollback 계획부터 다시 하세요.")
    later = _later_change(conn, plan.video_id, plan.change_id)
    if later is not None:
        raise SafetyGateError(f"계획 이후에 같은 영상의 다른 변경(#{later})이 생겨 중단했습니다.", "rollback 계획부터 다시 하세요.")
    _rollback_candidate_ok(conn, plan.candidate_id)
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO title_changes (video_id, candidate_id, change_type, previous_title, new_title, backup_snippet_json, reason, approver, approved_at, plan_hash, result, run_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (plan.video_id, plan.candidate_id, "rollback", plan.current_title, plan.restore_title, canonical_json(plan.snippet), f"롤백 대상 변경 #{plan.change_id}", approver, utc_iso(now), plan.plan_hash, "planned", run_id, utc_iso(now)),
            )
            return int(cur.lastrowid)
    except sqlite3.Error as exc:
        raise _db_error(exc) from exc
