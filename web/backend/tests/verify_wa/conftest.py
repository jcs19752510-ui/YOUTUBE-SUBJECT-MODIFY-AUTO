"""verify_wa 전용 픽스처. 부모 tests/conftest.py 의 app/client/clock/engine 등을 그대로 쓴다."""
from __future__ import annotations

import io
import logging

import pytest
from ytweb.core.logsetup import JsonFormatter


@pytest.fixture
def log_capture():
    """`ytweb` 로거 트리에 JSON 포매터 핸들러를 붙여 로그 원문을 문자열로 모은다(앱이 쓰는 실제 포매터)."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("ytweb")
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield buf
    logger.removeHandler(handler)
    logger.setLevel(old_level)


@pytest.fixture
def probe_app(web_settings, engine, clock, fake_time, monkeypatch):
    """core 라우터 + 프로브 라우터를 올린 앱(속도 제한은 사실상 해제)."""
    from ytweb.app import create_app
    from ytweb.core.ratelimit import RateLimits

    from tests.conftest import CORE_ROUTERS
    from tests.verify_wa import probe_routes
    probe_routes.CALLS.clear()
    probe_routes.FAIL_NEXT["flag"] = False
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "1")
    monkeypatch.delenv("YTWEB_STATIC_DIR", raising=False)
    return create_app(web_settings, clock=clock, router_modules=CORE_ROUTERS + ["tests.verify_wa.probe_routes"], time_fn=fake_time,
                      rate_limits=RateLimits(global_per_min=100_000, write_per_min=100_000, auth_per_min=100_000))


@pytest.fixture
def pclient(probe_app):
    from fastapi.testclient import TestClient

    from tests.conftest import ORIGIN
    with TestClient(probe_app, base_url=ORIGIN) as c:
        yield c
