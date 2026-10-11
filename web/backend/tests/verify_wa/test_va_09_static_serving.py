"""독립 점검 9: 빌드된 프런트(dist) 서빙의 경로 순회·SPA 폴백 (S-W04, S-W10 계열 경로 순회 방지)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from ytweb.app import create_app
from ytweb.core.ratelimit import RateLimits

from tests.conftest import CORE_ROUTERS, ORIGIN
from tests.verify_wa.helpers import asgi_call, header


@pytest.fixture
def static_app(tmp_path, web_settings, engine, clock, fake_time, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>INDEX</html>")
    (dist / "assets" / "app.js").write_text("console.log('ok')")
    (tmp_path / "outside_secret.txt").write_text("TOP-SECRET-OUTSIDE")
    (dist / "leak").symlink_to(tmp_path / "outside_secret.txt")
    monkeypatch.setenv("YTWEB_STATIC_DIR", str(dist))
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "1")
    return create_app(web_settings, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time,
                      rate_limits=RateLimits(global_per_min=100_000, write_per_min=100_000, auth_per_min=100_000))


H = [("host", "127.0.0.1:8080")]


@pytest.mark.parametrize("path", [
    "/../outside_secret.txt", "/%2e%2e/outside_secret.txt", "/..%2foutside_secret.txt", "/assets/../../outside_secret.txt",
    "/%2e%2e%2foutside_secret.txt", "/leak", "/assets/..%2f..%2foutside_secret.txt", "/....//outside_secret.txt",
    "//outside_secret.txt", "/assets/%2e%2e/%2e%2e/outside_secret.txt", "/%00../outside_secret.txt",
])
def test_static_path_traversal_and_symlink_escape_never_leak(static_app, path):
    """TC-VA-138 [S-W10, S-W04] 정적 서빙: 상위 경로(../·인코딩 변형·널 문자)와 dist 밖을 가리키는 심볼릭 링크로 dist 밖 파일을 읽을 수 없다."""
    with TestClient(static_app, base_url=ORIGIN) as c:
        r = c.get(path)
    assert "TOP-SECRET-OUTSIDE" not in r.text, (path, r.status_code)


def test_static_serves_assets_spa_fallback_and_api_404_stays_json(static_app):
    """TC-VA-139 [S-W04] 실제 파일은 그대로, 모르는 화면 경로는 index.html(SPA), /api 아래 없는 경로는 index.html 이 아니라 problem+json 404, 정적 응답에도 CSP(default-src 'self')가 붙는다."""
    with TestClient(static_app, base_url=ORIGIN) as c:
        assert c.get("/assets/app.js").text == "console.log('ok')"
        r = c.get("/videos/123")
        assert r.status_code == 200 and "INDEX" in r.text
        assert "default-src 'self'" in r.headers["content-security-policy"] and "frame-ancestors 'none'" in r.headers["content-security-policy"]
        r = c.get("/api/v1/nothing")
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json") and "INDEX" not in r.text
        r = c.get("/api")
        assert r.status_code == 404 and "INDEX" not in r.text


def test_static_host_check_still_applies(static_app):
    """TC-VA-140 [S-W02] 정적 파일도 허용되지 않은 Host 면 403(DNS 리바인딩으로 화면 코드를 읽지 못함)."""
    assert asgi_call(static_app, "GET", "/assets/app.js", [("host", "evil.com")])["status"] == 403
    out = asgi_call(static_app, "GET", "/assets/app.js", H)
    assert out["status"] == 200 and header(out, "x-content-type-options") == "nosniff"


def test_static_does_not_accept_state_changing_methods(static_app):
    """TC-VA-141 [S-W03] 정적 폴백 경로에 POST/PUT/DELETE 를 보내면 405 이며 아무 일도 일어나지 않는다."""
    for m in ("POST", "PUT", "DELETE", "PATCH"):
        out = asgi_call(static_app, m, "/some/page", H + [("origin", ORIGIN)], [b"{}"])
        assert out["status"] == 405, m
