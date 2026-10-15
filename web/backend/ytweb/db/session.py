"""엔진·세션 팩토리. 모든 질의는 ORM/파라미터 바인딩만 사용한다(S-W13)."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_engine(url: str, *, echo: bool = False) -> Engine:
    kwargs: dict = {"echo": echo, "future": True}
    if url.startswith("postgresql"):
        kwargs.update(pool_size=5, max_overflow=5, pool_pre_ping=True)
    elif url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """FastAPI 의존성/워커용: 정상 종료 시 commit, 예외 시 rollback."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
