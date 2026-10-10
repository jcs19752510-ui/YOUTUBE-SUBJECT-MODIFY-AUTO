"""도메인 테스트 픽스처. 루트 tests/conftest.py(W-BE-A)의 clock·web_settings·engine·factory·db 를 그대로 쓴다."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ytitle.config import load_settings

from ytweb.app import create_app
from ytweb.core.ratelimit import RateLimits
from ytweb.domain.common import Env, set_default_env
from ytweb.domain.seed import seed_demo
from ytweb.youtube.mock import MockYouTubeGateway

from tests.conftest import CORE_ROUTERS, ORIGIN, REPO_ROOT, login  # noqa: F401

DOMAIN_ROUTERS = [f"ytweb.routers.{n}" for n in ("dashboard", "videos", "suggestions", "batches", "changes", "reports", "jobs", "google")]
SEED_COUNT = 60


@pytest.fixture
def policy():
    return load_settings(REPO_ROOT, env={})


@pytest.fixture
def env(policy, web_settings) -> Env:
    return Env.build(policy, web_settings)


@pytest.fixture
def env_free(env) -> Env:
    """재변경 최소 노출수 조건을 끈 정책(간격·횟수 검사를 노출수와 분리해서 시험할 때)."""
    return dataclasses.replace(env, policy=dataclasses.replace(env.policy, min_impressions_before_rechange=0))


@pytest.fixture
def seeded(db, clock, env):
    seed_demo(db, clock(), env.policy, count=SEED_COUNT)
    db.commit()
    return db


@pytest.fixture
def gw(db, clock):
    return MockYouTubeGateway(db, clock)


@pytest.fixture(autouse=True)
def _reset_default_env():
    yield
    set_default_env(None)


@pytest.fixture
def dapp(web_settings, engine, clock, fake_time, monkeypatch):
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "1")
    monkeypatch.delenv("YTWEB_STATIC_DIR", raising=False)
    return create_app(web_settings, clock=clock, router_modules=CORE_ROUTERS + DOMAIN_ROUTERS, time_fn=fake_time,
                      rate_limits=RateLimits(global_per_min=100_000, write_per_min=100_000, auth_per_min=100_000))


@pytest.fixture
def api(dapp):
    with TestClient(dapp, base_url=ORIGIN) as c:
        yield c


@pytest.fixture
def csrf(api):
    return login(api)


def hdr(csrf: str, key: str | None = None) -> dict[str, str]:
    h = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    if key:
        h["Idempotency-Key"] = key
    return h
