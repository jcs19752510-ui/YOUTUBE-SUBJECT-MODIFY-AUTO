import sqlite3
from datetime import datetime, timezone

import pytest

from ytitle import db
from ytitle.errors import DatabaseError

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
TABLES = {"schema_meta", "videos", "title_candidates", "title_changes", "metrics_snapshots", "run_logs", "quota_usage"}


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.migrate(c)
    yield c
    c.close()


def test_migrate_creates_seven_tables_and_is_idempotent(conn):
    """TC-021: 7개 테이블이 만들어지고 migrate를 다시 불러도 안전하다. [설계 3-1, ADR-002]"""
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    assert TABLES <= names
    assert db.migrate(conn) == db.LATEST_VERSION == 1
    assert conn.execute("SELECT COUNT(*) FROM schema_meta").fetchone()[0] == 1


def test_foreign_keys_enforced(conn):
    """TC-022: 외래키가 켜져 있어 없는 후보를 가리키는 변경 기록은 거부된다. [SEC-006]"""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO title_changes (video_id, candidate_id, change_type, previous_title, new_title, result, created_at) VALUES ('v',999,'apply','a','b','planned','x')")


@pytest.mark.parametrize("sql", [
    "INSERT INTO title_candidates (video_id,candidate_title,source,strict_mode,status,created_at,updated_at) VALUES ('v','t','human',0,'unknown','x','x')",
    "INSERT INTO title_candidates (video_id,candidate_title,source,strict_mode,topic,status,created_at,updated_at) VALUES ('v','t','human',0,'sports','candidate','x','x')",
    "INSERT INTO title_candidates (video_id,candidate_title,source,strict_mode,status,created_at,updated_at) VALUES ('v','t','',0,'candidate','x','x')",
    "INSERT INTO title_changes (video_id,change_type,previous_title,new_title,result,created_at) VALUES ('v','apply','a','b','done','x')",
    "INSERT INTO quota_usage (pt_date,method,units,called_at,status) VALUES ('d','m',-5,'t','ok')",
    "INSERT INTO run_logs (run_id,started_at,command,mode) VALUES ('r','t','c','weird')",
    "INSERT INTO metrics_snapshots (video_id,taken_at,phase,source) VALUES ('v','t','during','api')",
])
def test_check_constraints_reject_invalid_enums(conn, sql):
    """TC-023: 상태·종류 값이 허용 목록에 없으면 DB가 거부한다(상태 머신 보호). [ADR-002, SEC-006]"""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)


def test_parameter_binding_stores_injection_text_literally(conn):
    """TC-024: 따옴표·SQL 구문이 든 제목도 값으로만 저장되고 테이블은 그대로다. [SEC-018]"""
    evil = "x'); DROP TABLE videos;--"
    conn.execute("INSERT INTO videos (video_id,title,snippet_json,fetched_at) VALUES (?,?,?,?)", ("abc123DEF45", evil, "{}", "t"))
    assert conn.execute("SELECT title FROM videos").fetchone()[0] == evil
    assert conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 1


def test_backup_creates_readable_copy_without_overwrite(conn, tmp_path):
    """TC-025: 백업 사본이 만들어져 같은 내용을 읽을 수 있고, 같은 초에 두 번 만들어도 덮어쓰지 않는다. [NFR-010]"""
    conn.execute("INSERT INTO videos (video_id,title,snippet_json,fetched_at) VALUES ('a','제목','{}','t')")
    conn.commit()
    p1 = db.backup(conn, tmp_path / "bk", NOW)
    p2 = db.backup(conn, tmp_path / "bk", NOW)
    assert p1 != p2 and p1.exists() and p2.exists()
    c2 = sqlite3.connect(p1)
    assert c2.execute("SELECT title FROM videos").fetchone()[0] == "제목"
    c2.close()


def test_newer_db_version_rejected():
    """TC-026: 프로그램보다 새 버전의 DB는 거부하고 업데이트를 안내한다. [ADR-002]"""
    c = db.connect(":memory:")
    db.migrate(c)
    c.execute("UPDATE schema_meta SET version = 99")
    with pytest.raises(DatabaseError) as ei:
        db.migrate(c)
    assert "업데이트" in ei.value.next_step


def test_run_log_start_and_finish(conn):
    """TC-027: 실행 기록이 시작·종료 시각, 종료 코드와 함께 저장된다. [FR-020]"""
    db.start_run(conn, "r1", "purge", "dry_run", NOW)
    db.finish_run(conn, "r1", 0, "ok", NOW)
    row = conn.execute("SELECT * FROM run_logs WHERE run_id='r1'").fetchone()
    assert (row["command"], row["mode"], row["exit_code"], row["summary"]) == ("purge", "dry_run", 0, "ok")
    assert row["started_at"] == "2026-10-10T12:00:00Z"


def test_connect_failure_gives_korean_error(tmp_path):
    """TC-028: 열 수 없는 경로는 한국어 안내가 있는 DatabaseError가 된다. [NFR-007]"""
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(DatabaseError):
        db.connect(blocker / "sub" / "x.sqlite3")
