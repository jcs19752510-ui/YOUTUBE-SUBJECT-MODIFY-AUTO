"""9단계 보안 점검 공용 픽스처(공격자 관점 시험). 운영 코드를 고치지 않고 임시 SQLite 로 앱을 띄운다.

재실행:  <venv>/bin/python -m pytest web/tests_security -q    (venv = web/backend/requirements-dev.txt + web/docker/requirements-ytitle.txt)
실스택(컨테이너) 시험은 YTWEB_SEC_LIVE_PORT 가 있을 때만 돈다(test_sec_04_live_stack.py 머리말 참고).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
# mutation_check.py 가 변이를 적용한 사본을 가리키게 할 때만 쓰는 우회 경로(기본은 저장소의 실제 소스)
_BACKEND = Path(os.environ.get("YTWEB_SEC_BACKEND_DIR", REPO_ROOT / "web" / "backend"))
_SRC = Path(os.environ.get("YTWEB_SEC_SRC_DIR", REPO_ROOT / "src"))
for p in (_SRC, _BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ytitle.config import load_settings  # noqa: E402

from ytweb.app import create_app  # noqa: E402
from ytweb.config import WebSettings  # noqa: E402
from ytweb.core.ratelimit import RateLimits  # noqa: E402
from ytweb.db.models import Base  # noqa: E402
from ytweb.db.session import make_engine, make_session_factory  # noqa: E402
from ytweb.domain.common import Env, set_default_env  # noqa: E402
from ytweb.domain.seed import seed_demo  # noqa: E402

ORIGIN = "http://127.0.0.1:8080"
HOST = "127.0.0.1:8080"


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
def settings(tmp_path: Path) -> WebSettings:
    return WebSettings(
        mode="demo",
        database_url=f"sqlite:///{tmp_path / 'sec.db'}",
        base_dir=REPO_ROOT,
        secrets_dir=tmp_path / "secrets",
        allowed_hosts=(HOST, "localhost:8080"),
        session_ttl_hours=12,
    )


@pytest.fixture
def engine(settings):
    eng = make_engine(settings.database_url)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine):
    return make_session_factory(engine)


@pytest.fixture
def env(settings) -> Env:
    return Env.build(load_settings(REPO_ROOT, env={}), settings)


@pytest.fixture(autouse=True)
def _reset_default_env():
    yield
    set_default_env(None)


@pytest.fixture
def seeded(factory, clock, env):
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
    return factory


def build_app(settings, clock, *, rate_limits: RateLimits | None = None, time_fn=None, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setenv("YTWEB_AUTO_CREATE", "1")
        monkeypatch.delenv("YTWEB_STATIC_DIR", raising=False)
    return create_app(settings, clock=clock, time_fn=time_fn, rate_limits=rate_limits or RateLimits(global_per_min=100_000, write_per_min=100_000, auth_per_min=100_000))


@pytest.fixture
def app(settings, engine, seeded, clock, monkeypatch):
    return build_app(settings, clock, monkeypatch=monkeypatch)


@pytest.fixture
def client(app):
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as c:
        yield c


def login(client: TestClient, pin: str | None = None, headers: dict | None = None):
    h = {"Origin": ORIGIN}
    h.update(headers or {})
    return client.post("/api/v1/auth/session", json={"pin": pin} if pin else None, headers=h)


@pytest.fixture
def csrf(client) -> str:
    r = login(client)
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def hdr(csrf: str, key: str | None = None, **extra) -> dict[str, str]:
    h = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    if key:
        h["Idempotency-Key"] = key
    h.update(extra)
    return h
