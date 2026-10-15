"""Alembic 환경. 마이그레이션은 모델이 아니라 versions/ 의 고정 SQL 을 따른다(autogenerate 미사용)."""
from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config


def _url() -> str | None:
    return config.attributes.get("url") or os.environ.get("YTWEB_MIGRATE_DATABASE_URL")


def run_migrations_offline() -> None:
    url = _url() or "postgresql+psycopg://"
    context.configure(url=url, dialect_name="postgresql", literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    if not url:
        raise RuntimeError("마이그레이션 DB URL 이 없습니다(YTWEB_MIGRATE_DATABASE_URL 또는 ytweb.migrate 사용).")
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
