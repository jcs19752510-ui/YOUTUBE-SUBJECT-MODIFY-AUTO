"""Alembic 초기 마이그레이션 · 마이그레이션 실행기 · 개발 편의 auto-create."""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from alembic import command

from ytweb import migrate
from ytweb.db.models import Base

VERSION_FILE = Path(migrate.BACKEND_DIR) / "alembic" / "versions" / "0001_initial.py"


def _offline_sql() -> str:
    buf = io.StringIO()
    cfg = migrate.alembic_config()
    cfg.output_buffer = buf
    command.upgrade(cfg, "head", sql=True)
    return buf.getvalue()


def test_offline_render_contains_every_table_and_index():
    """TC-WA-115 `alembic upgrade head --sql` 이 성공하고 모든 모델 테이블·인덱스 DDL 을 포함한다."""
    sql = _offline_sql()
    for table in Base.metadata.sorted_tables:
        assert f"CREATE TABLE {table.name} " in sql, table.name
        for ix in table.indexes:
            assert ix.name in sql, ix.name
    assert "INSERT INTO alembic_version" in sql


def test_offline_render_has_partial_unique_indexes_and_checks():
    """TC-WA-116 이중 반영 차단용 부분 고유 인덱스 2개와 CHECK 제약이 렌더링된다."""
    sql = _offline_sql()
    assert "CREATE UNIQUE INDEX uq_changes_planned_per_video ON changes (video_id) WHERE result = 'planned'" in sql
    assert "CREATE UNIQUE INDEX uq_batch_items_active_suggestion ON batch_items (suggestion_id) WHERE status IN ('pending','running')" in sql
    assert "CONSTRAINT ck_jobs_status CHECK" in sql
    assert "JSONB" in sql and "TIMESTAMP WITH TIME ZONE" in sql


def test_offline_render_revokes_audit_mutation_for_app_role():
    """TC-WA-117 마이그레이션 끝에서 ytweb_app 의 audit_log UPDATE/DELETE/TRUNCATE 권한을 회수한다(역할이 있을 때만)."""
    sql = _offline_sql()
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM ytweb_app" in sql
    assert "pg_roles WHERE rolname = 'ytweb_app'" in sql


def test_migration_is_frozen_sql_not_model_import():
    """TC-WA-118 0001 은 모델을 임포트하지 않고 고정 SQL 문자열만 쓴다(모델이 바뀌어도 과거 마이그레이션이 변하지 않게)."""
    src = VERSION_FILE.read_text(encoding="utf-8")
    assert "ytweb" not in src.replace("ytweb_app", "").replace("ytweb_owner", "")
    assert "metadata" not in src and "create_all" not in src
    assert src.count('"""CREATE TABLE') == len(Base.metadata.tables)


def test_single_head_revision():
    """TC-WA-119 마이그레이션 헤드는 하나(0001)다."""
    from alembic.script import ScriptDirectory
    assert ScriptDirectory.from_config(migrate.alembic_config()).get_heads() == ["0001"]


def test_owner_url_from_explicit_env():
    """TC-WA-120 YTWEB_MIGRATE_DATABASE_URL 이 있으면 그대로 쓴다."""
    assert migrate.owner_database_url({"YTWEB_MIGRATE_DATABASE_URL": "postgresql+psycopg://o:p@h/db"}) == "postgresql+psycopg://o:p@h/db"


def test_owner_url_from_password_file(tmp_path):
    """TC-WA-121 소유자 비밀번호 파일에서 URL 을 만들고 특수문자를 인코딩한다(앱 계정이 아닌 ytweb_owner)."""
    pw = tmp_path / "owner_pw"
    pw.write_text("p@ss/w:rd%\n", encoding="utf-8")
    url = migrate.owner_database_url({"YTWEB_DB_OWNER_PASSWORD_FILE": str(pw), "YTWEB_DB_HOST": "db", "YTWEB_DB_NAME": "ytweb"})
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    assert (parsed.username, parsed.password, parsed.host, parsed.port, parsed.database) == ("ytweb_owner", "p@ss/w:rd%", "db", 5432, "ytweb")


def test_owner_url_missing_config_raises():
    """TC-WA-122 설정이 없으면 ValueError."""
    with pytest.raises(ValueError):
        migrate.owner_database_url({})


def test_main_reports_config_error(monkeypatch, capsys):
    """TC-WA-123 설정 없이 실행하면 종료 코드 2 와 한국어 안내(비밀 없음)."""
    monkeypatch.delenv("YTWEB_MIGRATE_DATABASE_URL", raising=False)
    monkeypatch.delenv("YTWEB_DB_OWNER_PASSWORD_FILE", raising=False)
    assert migrate.main() == 2
    assert "마이그레이션 설정 오류" in capsys.readouterr().err


def test_main_runs_upgrade(monkeypatch):
    """TC-WA-124 설정이 있으면 upgrade(url) 을 호출하고 0 을 돌려준다."""
    calls = []
    monkeypatch.setenv("YTWEB_MIGRATE_DATABASE_URL", "postgresql+psycopg://o:p@h/db")
    monkeypatch.setattr(migrate, "upgrade", lambda url, revision="head": calls.append(url))
    with redirect_stdout(io.StringIO()):
        assert migrate.main() == 0
    assert calls == ["postgresql+psycopg://o:p@h/db"]


def test_auto_create_makes_tables_for_sqlite(web_settings, monkeypatch):
    """TC-WA-125 sqlite + YTWEB_AUTO_CREATE=1 이면 create_all 로 테이블이 생기고, 값이 없으면 생기지 않는다."""
    from sqlalchemy import inspect
    from ytweb.app import create_app
    monkeypatch.delenv("YTWEB_AUTO_CREATE", raising=False)
    app = create_app(web_settings, router_modules=[])
    assert inspect(app.state.engine).get_table_names() == []
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "1")
    app = create_app(web_settings, router_modules=[])
    assert set(inspect(app.state.engine).get_table_names()) == set(Base.metadata.tables)
