import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from youtube_title import cli, commands, db, timeutil
from youtube_title.config import load_settings
from youtube_title.errors import ConfigError, DatabaseError
from youtube_title.logging_setup import setup_logging


def test_keyboard_interrupt_exit_130(project, streams, tmp_path, monkeypatch):
    """TC-073: 사용자가 Ctrl+C로 중단하면 한국어 안내와 함께 종료 코드 130이 된다. [FR-020, NFR-008]"""
    import importlib

    extra = tmp_path / "kb"
    extra.mkdir()
    (extra / "kb.py").write_text(textwrap.dedent('''
        def _run(args, ctx):
            raise KeyboardInterrupt
        def register(sub, parent):
            sub.add_parser("kb", parents=[parent], help="x").set_defaults(func=_run)
    '''), encoding="utf-8")
    monkeypatch.setattr(commands, "__path__", list(commands.__path__) + [str(extra)])
    importlib.invalidate_caches()
    code = cli.main(["--base-dir", str(project), "kb"], out=streams.out, err=streams.err, env={})
    sys.modules.pop("youtube_title.commands.kb", None)
    assert code == 130 and "중단" in streams.err.getvalue()
    import sqlite3

    row = sqlite3.connect(project / "data" / "youtube_title.sqlite3").execute("SELECT exit_code, summary FROM run_logs").fetchone()
    assert row == (130, "interrupted")


def test_python_dash_m_entrypoint_works():
    """TC-074: `python -m youtube_title --version`이 실제로 실행되어 버전을 출력한다. [FR-017]"""
    src = str(Path(__file__).resolve().parent.parent / "src")
    r = subprocess.run([sys.executable, "-m", "youtube_title", "--version"], capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONPATH=src))
    assert r.returncode == 0 and r.stdout.startswith("유튜브 제목 ")


def test_empty_yaml_and_wrong_section_type(project):
    """TC-075: 비어 있는 설정 파일은 기본값으로, 항목이 목록/숫자 형태로 잘못되면 ConfigError. [NFR-007]"""
    (project / "config" / "settings.yaml").write_text("", encoding="utf-8")
    assert load_settings(project, env={}).daily_limit_units == 6000
    (project / "config" / "settings.yaml").write_text("quota: 5\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(project, env={})


def test_migration_failure_becomes_database_error(monkeypatch):
    """TC-076: 마이그레이션 SQL이 실패하면 한국어 DatabaseError가 되고 DB는 부분 적용되지 않는다. [ADR-002]"""
    monkeypatch.setattr(db, "MIGRATIONS", [(1, "CREATE TABLE ok (x INTEGER);\nCREATE TABLE broken (")])
    c = db.connect(":memory:")
    with pytest.raises(DatabaseError):
        db.migrate(c)
    assert c.execute("SELECT name FROM sqlite_master WHERE name='ok'").fetchone() is None
    c.close()


def test_missing_tzdata_gives_actionable_error(monkeypatch):
    """TC-077: tzdata가 없어 태평양 시간대를 못 찾으면 설치 방법을 안내하는 ConfigError. [ADR-006, Windows]"""
    import zoneinfo

    def boom(key):
        raise zoneinfo.ZoneInfoNotFoundError(key)

    monkeypatch.setattr(zoneinfo, "ZoneInfo", boom)
    with pytest.raises(ConfigError) as ei:
        timeutil.pt_zone()
    assert "pip install tzdata" in ei.value.next_step


def test_console_logging_handler_masks_secrets(tmp_path, capsys):
    """TC-078: 콘솔 로그(경고 이상)도 같은 마스킹을 거친다. [SEC-008]"""
    logger = setup_logging(tmp_path, "r9", console=True)
    assert len(logger.handlers) == 2
    logger.warning("키 GOCSPX-abcDEF123_ghi 노출")
    err = capsys.readouterr().err
    assert "GOCSPX-abc" not in err and "r9" in err
    logger.info("정보는 콘솔에 안 나온다")
    assert "정보는" not in capsys.readouterr().err
    assert logging.getLogger("youtube_title").propagate is False


def test_finish_run_failure_is_database_error():
    """TC-079: 닫힌 연결에 실행 기록을 저장하려 하면 한국어 DatabaseError가 된다(조용히 삼키지 않음). [FR-020, NFR-007]"""
    from datetime import datetime, timezone

    c = db.connect(":memory:")
    db.migrate(c)
    c.close()
    with pytest.raises(DatabaseError):
        db.finish_run(c, "r", 0, "ok", datetime(2026, 1, 1, tzinfo=timezone.utc))
