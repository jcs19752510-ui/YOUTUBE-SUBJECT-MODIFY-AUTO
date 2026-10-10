"""Host 허용 목록 · 요청 크기 · 속도 제한 · 보안 헤더 · /docs 노출 · 오류 형식."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import CORE_ROUTERS, ORIGIN, login
from ytweb.app import create_app
from ytweb.core.ratelimit import RateLimits


def _make(web_settings, fake_time, clock, **kw):
    return create_app(web_settings, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time, **kw)


def test_host_not_allowed_rejected(client):
    """TC-WA-@@@ 허용 목록 밖 Host(DNS 리바인딩)는 403 host_not_allowed."""
    r = client.get("/api/v1/auth/me", headers={"Host": "evil.example:8080"})
    assert r.status_code == 403
    assert r.json()["code"] == "host_not_allowed"
    assert r.headers["content-type"].startswith("application/problem+json")


def test_host_localhost_and_case_insensitive_allowed(client):
    """TC-WA-@@@ localhost:8080 과 대소문자 다른 Host 는 허용."""
    assert client.get("/api/v1/auth/me", headers={"Host": "localhost:8080"}).status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Host": "LocalHost:8080"}).status_code == 200


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.1:9999", "", "127.0.0.1:8080.evil.com"])
def test_host_port_mismatch_or_missing_rejected(client, host):
    """TC-WA-@@@ 포트가 없거나 다르거나 빈 Host 는 거부."""
    r = client.get("/api/v1/auth/me", headers={"Host": host})
    assert r.status_code == 403


def test_health_exempt_from_host_check(client):
    """TC-WA-@@@ 컨테이너 헬스체크는 Host 검증을 받지 않는다(민감 정보 없음)."""
    r = client.get("/healthz", headers={"Host": "api:8000"})
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert client.get("/api/healthz", headers={"Host": "api:8000"}).status_code == 200


def test_oversized_content_length_rejected(client):
    """TC-WA-@@@ Content-Length 가 1MB 를 넘으면 413 payload_too_large."""
    r = client.post("/api/v1/auth/session", content=b"x" * (1024 * 1024 + 1), headers={"Origin": ORIGIN, "content-type": "application/json"})
    assert r.status_code == 413
    assert r.json()["code"] == "payload_too_large"


def test_oversized_chunked_body_rejected(client):
    """TC-WA-@@@ Content-Length 없는 chunked 본문도 1MB 를 넘으면 413."""
    def gen():
        for _ in range(20):
            yield b"x" * 100_000

    r = client.post("/api/v1/auth/session", content=gen(), headers={"Origin": ORIGIN, "content-type": "application/json"})
    assert r.status_code == 413
    assert r.json()["code"] == "payload_too_large"


def test_body_under_limit_not_rejected(client):
    """TC-WA-@@@ 한도 이하 본문은 크기 제한에 걸리지 않는다."""
    r = client.post("/api/v1/auth/session", json={"pin": "1" * 60}, headers={"Origin": ORIGIN})
    assert r.status_code == 200


def test_global_rate_limit_and_recovery(web_settings, engine, clock, fake_time):
    """TC-WA-@@@ 전역 속도 제한 초과 시 429 + Retry-After, 시간이 지나면 회복."""
    app = _make(web_settings, fake_time, clock, rate_limits=RateLimits(global_per_min=3, write_per_min=100, auth_per_min=100))
    with TestClient(app, base_url=ORIGIN) as c:
        for _ in range(3):
            assert c.get("/api/v1/auth/me").status_code == 200
        r = c.get("/api/v1/auth/me")
        assert r.status_code == 429 and r.json()["code"] == "rate_limited"
        assert int(r.headers["retry-after"]) >= 1
        assert c.get("/healthz").status_code == 200  # 헬스는 제한 제외
        fake_time.t += 61
        assert c.get("/api/v1/auth/me").status_code == 200


def test_auth_rate_limit_bucket(web_settings, engine, clock, fake_time):
    """TC-WA-@@@ 세션 발급은 별도의 더 낮은 한도를 가진다."""
    app = _make(web_settings, fake_time, clock, rate_limits=RateLimits(global_per_min=100, write_per_min=100, auth_per_min=2))
    with TestClient(app, base_url=ORIGIN) as c:
        h = {"Origin": ORIGIN}
        assert c.post("/api/v1/auth/session", headers=h).status_code == 200
        assert c.post("/api/v1/auth/session", headers=h).status_code == 200
        assert c.post("/api/v1/auth/session", headers=h).status_code == 429
        assert c.get("/api/v1/auth/me").status_code == 200


def test_write_rate_limit_bucket(web_settings, engine, clock, fake_time):
    """TC-WA-@@@ 상태 변경 메서드는 쓰기 한도를 따로 센다(읽기는 영향 없음)."""
    app = _make(web_settings, fake_time, clock, rate_limits=RateLimits(global_per_min=100, write_per_min=2, auth_per_min=100))
    with TestClient(app, base_url=ORIGIN) as c:
        csrf = login(c)  # 쓰기 1회
        h = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
        assert c.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers=h).status_code == 200  # 2회
        assert c.patch("/api/v1/settings", json={"daily_apply_cap": 6}, headers=h).status_code == 429
        assert c.get("/api/v1/settings").status_code == 200


def test_rejected_requests_do_not_consume_budget(web_settings, engine, clock, fake_time):
    """TC-WA-@@@ 잘못된 Host 요청은 속도 제한 예산을 쓰지 않는다."""
    app = _make(web_settings, fake_time, clock, rate_limits=RateLimits(global_per_min=2, write_per_min=100, auth_per_min=100))
    with TestClient(app, base_url=ORIGIN) as c:
        for _ in range(5):
            assert c.get("/api/v1/auth/me", headers={"Host": "evil:1"}).status_code == 403
        assert c.get("/api/v1/auth/me").status_code == 200


def test_security_headers_on_api_response(client):
    """TC-WA-@@@ API 응답에 보안 헤더와 요청 ID 가 붙는다."""
    r = client.get("/api/v1/auth/me")
    h = r.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "no-referrer"
    assert h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["cache-control"] == "no-store"
    assert "camera=()" in h["permissions-policy"]
    assert len(h["x-request-id"]) == 32


def test_security_headers_on_error_responses(client):
    """TC-WA-@@@ 거부(403)·404 응답에도 보안 헤더가 붙는다."""
    for r in (client.get("/api/v1/auth/me", headers={"Host": "evil:1"}), client.get("/api/v1/nope")):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_docs_disabled_by_default(client):
    """TC-WA-@@@ enable_docs 가 꺼져 있으면 /docs, /redoc, /openapi.json 이 없다."""
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(p).status_code == 404


def test_docs_enabled_when_configured(web_settings, engine, clock, fake_time):
    """TC-WA-@@@ enable_docs 이면 /docs 가 열린다."""
    from dataclasses import replace
    app = _make(replace(web_settings, enable_docs=True), fake_time, clock)
    with TestClient(app, base_url=ORIGIN) as c:
        assert c.get("/docs").status_code == 200
        assert c.get("/openapi.json").status_code == 200


def test_websocket_rejected(client):
    """TC-WA-@@@ 웹소켓 연결은 지원하지 않고 닫는다."""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws"):
            pass
