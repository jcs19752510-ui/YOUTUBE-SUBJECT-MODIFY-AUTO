"""공용 픽스처(W-BE-A). SQLite 파일 DB + 가짜 시계로 빠르게 돈다."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ytweb.app import create_app
from ytweb.config import WebSettings
from ytweb.core.ratelimit import RateLimits
from ytweb.db.models import Base
from ytweb.db.session import make_engine, make_session_factory

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_ROUTERS = ["ytweb.routers.health", "ytweb.routers.auth", "ytweb.routers.settings", "ytweb.routers.audit"]
ORIGIN = "http://127.0.0.1:8080"


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 10, 3, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


class FakeTime:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def web_settings(tmp_path: Path) -> WebSettings:
    return WebSettings(
        mode="demo",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        base_dir=REPO_ROOT,
        secrets_dir=tmp_path / "secrets",
        allowed_hosts=("127.0.0.1:8080", "localhost:8080"),
        session_ttl_hours=12,
    )


@pytest.fixture
def engine(web_settings: WebSettings):
    eng = make_engine(web_settings.database_url)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine):
    return make_session_factory(engine)


@pytest.fixture
def db(factory):
    with factory() as s:
        yield s
        s.rollback()


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def app(web_settings, engine, clock, fake_time, monkeypatch):
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "1")
    monkeypatch.delenv("YTWEB_STATIC_DIR", raising=False)
    return create_app(web_settings, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time,
                      rate_limits=RateLimits(global_per_min=10_000, write_per_min=10_000, auth_per_min=10_000))


@pytest.fixture
def client(app):
    with TestClient(app, base_url=ORIGIN) as c:
        yield c


def login(client: TestClient, pin: str | None = None) -> str:
    r = client.post("/api/v1/auth/session", json={"pin": pin} if pin else None, headers={"Origin": ORIGIN})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def hdr(csrf: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf}


@pytest.fixture
def csrf(client) -> str:
    return login(client)


@pytest.fixture(scope="session")
def pg_url() -> str:
    url = os.environ.get("YTWEB_TEST_PG_URL")
    if not url:
        pytest.skip("YTWEB_TEST_PG_URL 이 없어 PostgreSQL 전용 테스트를 건너뜀")
    return url
