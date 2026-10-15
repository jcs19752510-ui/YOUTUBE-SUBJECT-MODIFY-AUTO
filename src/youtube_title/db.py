"""SQLite 저장소와 마이그레이션(ADR-002). 모든 SQL은 파라미터 바인딩만 사용한다(SEC-018)."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from youtube_title.errors import DatabaseError
from youtube_title.timeutil import utc_iso

SCHEMA_V1 = """
CREATE TABLE schema_meta (version INTEGER NOT NULL);
CREATE TABLE videos (
  video_id TEXT PRIMARY KEY, title TEXT NOT NULL, category_id TEXT, privacy_status TEXT,
  made_for_kids INTEGER CHECK (made_for_kids IN (0,1) OR made_for_kids IS NULL),
  live_broadcast_content TEXT, duration_sec INTEGER, description_excerpt TEXT,
  snippet_json TEXT NOT NULL, fetched_at TEXT NOT NULL
);
CREATE TABLE title_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL, candidate_title TEXT NOT NULL,
  evidence TEXT, source TEXT NOT NULL CHECK (length(source) > 0),
  topic TEXT CHECK (topic IN ('life','health','finance') OR topic IS NULL),
  strict_mode INTEGER NOT NULL CHECK (strict_mode IN (0,1)),
  validation_result TEXT CHECK (validation_result IN ('pass','warn','block') OR validation_result IS NULL),
  validation_reasons_json TEXT, dictionary_hash TEXT, file_name TEXT, file_sha256 TEXT,
  status TEXT NOT NULL CHECK (status IN ('candidate','filtered','approved','applied','evaluated','rolled_back','blocked')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE title_changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL,
  candidate_id INTEGER REFERENCES title_candidates(id),
  change_type TEXT NOT NULL CHECK (change_type IN ('apply','rollback')),
  previous_title TEXT NOT NULL, new_title TEXT NOT NULL, backup_snippet_json TEXT,
  reason TEXT, approver TEXT, approved_at TEXT, plan_hash TEXT,
  result TEXT NOT NULL CHECK (result IN ('planned','success','failed','aborted')),
  error_code TEXT, applied_at TEXT, verified_at TEXT, verify_result_json TEXT, run_id TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE metrics_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL, taken_at TEXT NOT NULL,
  phase TEXT NOT NULL CHECK (phase IN ('before','after','periodic')),
  source TEXT NOT NULL CHECK (source IN ('api','csv')),
  period_start TEXT, period_end TEXT, impressions INTEGER, ctr REAL, views INTEGER, watch_minutes REAL, raw_json TEXT
);
CREATE TABLE run_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
  command TEXT NOT NULL, mode TEXT NOT NULL CHECK (mode IN ('dry_run','live')), exit_code INTEGER, summary TEXT
);
CREATE TABLE quota_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, pt_date TEXT NOT NULL, method TEXT NOT NULL, units INTEGER NOT NULL CHECK (units >= 0),
  called_at TEXT NOT NULL, run_id TEXT, status TEXT NOT NULL CHECK (status IN ('reserved','ok','failed'))
);
CREATE INDEX idx_title_changes_video ON title_changes (video_id, applied_at);
CREATE INDEX idx_quota_usage_date ON quota_usage (pt_date);
CREATE INDEX idx_metrics_video ON metrics_snapshots (video_id, phase, taken_at);
INSERT INTO schema_meta (version) VALUES (1);
"""

MIGRATIONS = [(1, SCHEMA_V1)]  # 번호는 올리기만 한다. 기존 번호의 내용은 수정하지 않는다.
LATEST_VERSION = MIGRATIONS[-1][0]


def connect(path: Path | str) -> sqlite3.Connection:
    p = Path(path)
    try:
        if str(path) != ":memory:":
            p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
    except (OSError, sqlite3.Error) as exc:
        raise DatabaseError("데이터베이스 파일을 열 수 없습니다.", "data 폴더에 쓰기 권한이 있는지 확인하세요.", cause=type(exc).__name__) from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'").fetchone()
    if not row:
        return 0
    v = conn.execute("SELECT MAX(version) AS v FROM schema_meta").fetchone()["v"]
    return int(v or 0)


def migrate(conn: sqlite3.Connection) -> int:
    version = current_version(conn)
    if version > LATEST_VERSION:
        raise DatabaseError(f"데이터베이스가 이 프로그램보다 새 버전입니다(DB {version} > 프로그램 {LATEST_VERSION}).", "프로그램을 최신 버전으로 업데이트하세요.")
    for number, sql in MIGRATIONS:
        if number <= version:
            continue
        # sqlite3는 DDL을 자동으로 트랜잭션에 묶지 않으므로 BEGIN/COMMIT을 직접 써서 전부 적용되거나 전혀 적용되지 않게 한다.
        try:
            conn.execute("BEGIN")
            for stmt in _split(sql):
                conn.execute(stmt)
            if number > 1:
                conn.execute("UPDATE schema_meta SET version = ?", (number,))
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise DatabaseError(f"데이터베이스 업그레이드에 실패했습니다(버전 {number}).", "data 폴더의 DB 파일을 백업한 뒤 다시 시도하세요.", cause=type(exc).__name__) from exc
    return current_version(conn)


def _split(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";\n") if s.strip()]


def backup(conn: sqlite3.Connection, dest_dir: Path | str, now: datetime) -> Path:
    """sqlite 백업 API로 안전한 사본을 만든다(NFR-010)."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"youtube_title_{now.strftime('%Y%m%d_%H%M%S')}.sqlite3"
    n = 1
    while target.exists():
        target = dest / f"youtube_title_{now.strftime('%Y%m%d_%H%M%S')}_{n}.sqlite3"
        n += 1
    out = sqlite3.connect(str(target))
    try:
        conn.backup(out)
    finally:
        out.close()
    return target


def start_run(conn: sqlite3.Connection, run_id: str, command: str, mode: str, now: datetime) -> None:
    with conn:
        conn.execute("INSERT INTO run_logs (run_id, started_at, command, mode) VALUES (?,?,?,?)", (run_id, utc_iso(now), command, mode))


def finish_run(conn: sqlite3.Connection, run_id: str, exit_code: int, summary: str, now: datetime) -> None:
    try:
        with conn:
            conn.execute("UPDATE run_logs SET ended_at=?, exit_code=?, summary=? WHERE run_id=?", (utc_iso(now), exit_code, summary, run_id))
    except sqlite3.Error as exc:
        raise DatabaseError("실행 기록을 저장하지 못했습니다.", "data 폴더의 쓰기 권한과 디스크 공간을 확인하세요.", cause=type(exc).__name__) from exc
