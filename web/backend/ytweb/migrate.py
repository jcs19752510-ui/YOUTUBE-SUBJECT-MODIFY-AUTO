"""`python -m ytweb.migrate`: 소유자 계정으로 `alembic upgrade head` 를 실행한다(앱 계정은 DDL 권한이 없다)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

BACKEND_DIR = Path(__file__).resolve().parents[1]


def owner_database_url(env: dict[str, str] | None = None) -> str:
    e = dict(os.environ if env is None else env)
    url = e.get("YTWEB_MIGRATE_DATABASE_URL")
    if url:
        return url
    pw_file = e.get("YTWEB_DB_OWNER_PASSWORD_FILE")
    if not pw_file:
        raise ValueError("YTWEB_MIGRATE_DATABASE_URL 또는 YTWEB_DB_OWNER_PASSWORD_FILE 이 필요합니다.")
    pw = Path(pw_file).read_text(encoding="utf-8").strip()
    user = e.get("YTWEB_DB_OWNER_USER", "ytweb_owner")
    host = e.get("YTWEB_DB_HOST", "db")
    name = e.get("YTWEB_DB_NAME", "ytweb")
    return URL.create("postgresql+psycopg", username=user, password=pw, host=host, port=5432, database=name).render_as_string(hide_password=False)


def alembic_config(url: str | None = None) -> Config:
    ini = os.environ.get("YTWEB_ALEMBIC_INI")
    cfg = Config(ini or str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    if url:
        cfg.attributes["url"] = url  # configparser 의 % 보간을 피하려고 옵션 대신 attributes 로 전달
    return cfg


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def main() -> int:
    try:
        url = owner_database_url()
    except (ValueError, OSError) as exc:
        print(f"마이그레이션 설정 오류: {exc}", file=sys.stderr)
        return 2
    upgrade(url)
    print("마이그레이션 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
