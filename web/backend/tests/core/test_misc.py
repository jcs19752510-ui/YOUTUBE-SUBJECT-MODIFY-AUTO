"""시간 유틸 · 의존성 · 라우터 자동 포함 · 헬스 · 정적 파일 서빙."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import CORE_ROUTERS, ORIGIN
from ytweb.app import create_app, discover_routers
from ytweb.core.clock import kst_today, pt_date, utcnow
from ytweb.core.deps import get_clock, get_policy, get_session, get_web_settings
from ytweb.db.models import SettingKV


def test_kst_today_boundary():
    """TC-WA-133 UTC 14:59 는 같은 날, 15:00 은 KST 로 다음 날."""
    assert kst_today(datetime(2026, 10, 10, 14, 59, tzinfo=timezone.utc)) == date(2026, 10, 10)
    assert kst_today(datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)) == date(2026, 10, 11)


def test_pt_date_handles_dst_and_boundary():
    """TC-WA-134 태평양 시간 기준일(서머타임 UTC-7, 표준시 UTC-8)."""
    assert pt_date(datetime(2026, 10, 10, 6, 59, tzinfo=timezone.utc)) == date(2026, 10, 9)
    assert pt_date(datetime(2026, 10, 10, 7, 0, tzinfo=timezone.utc)) == date(2026, 10, 10)
    assert pt_date(datetime(2026, 12, 10, 7, 59, tzinfo=timezone.utc)) == date(2026, 12, 9)
    assert pt_date(datetime(2026, 12, 10, 8, 0, tzinfo=timezone.utc)) == date(2026, 12, 10)


def test_clock_rejects_naive_and_utcnow_is_aware():
    """TC-WA-135 naive datetime 은 거부, utcnow 는 tz-aware UTC."""
    with pytest.raises(ValueError):
        kst_today(datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        pt_date(datetime(2026, 1, 1))
    assert utcnow().utcoffset() == timedelta(0)


def test_discover_routers_finds_core_modules():
    """TC-WA-136 라우터 자동 탐색이 health/auth/settings/audit 를 찾는다(router 속성이 없는 모듈은 제외)."""
    found = discover_routers()
    for name in CORE_ROUTERS:
        assert name in found


def test_discovery_default_includes_core_routes(web_settings, engine, monkeypatch):
    """TC-WA-137 router_modules 를 생략하면 자동 탐색으로 핵심 경로가 등록된다."""
    with TestClient(create_app(web_settings), base_url=ORIGIN) as c:
        assert c.get("/healthz").status_code == 200
        assert c.get("/readyz").status_code == 200
        assert c.get("/api/v1/auth/me").status_code == 200
        assert c.get("/api/v1/settings").status_code == 401
        assert c.get("/api/v1/audit").status_code == 401


def test_deps_expose_app_state(app, client):
    """TC-WA-138 get_web_settings/get_policy/get_clock 이 앱 상태의 값을 돌려준다."""
    r = APIRouter()

    @r.get("/api/v1/_t/deps")
    def _d(ws=Depends(get_web_settings), policy=Depends(get_policy), clock=Depends(get_clock)):
        return {"mode": ws.mode, "ttl": policy.approval_ttl_hours, "now": clock().isoformat(), "cap_cfg": policy.enable_live}

    app.include_router(r)
    with TestClient(app, base_url=ORIGIN) as c:
        j = c.get("/api/v1/_t/deps").json()
    assert j["mode"] == "demo" and j["ttl"] == 24 and j["now"].startswith("2026-10-10T03:00") and j["cap_cfg"] is False


def test_get_session_commits_on_success_and_rolls_back_on_error(app, client, db):
    """TC-WA-139 get_session: 정상 종료는 commit, 예외는 rollback."""
    from datetime import datetime, timezone
    r = APIRouter()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    @r.post("/api/v1/_t/ok")
    def _ok(s=Depends(get_session)):
        s.add(SettingKV(key="t_ok", value=1, updated_at=now))
        return {}

    @r.post("/api/v1/_t/err")
    def _err(s=Depends(get_session)):
        s.add(SettingKV(key="t_err", value=1, updated_at=now))
        s.flush()
        from ytweb.core.errors import ProblemError
        raise ProblemError(400, "bad", "나쁨")

    app.include_router(r)
    with TestClient(app, base_url=ORIGIN) as c:
        assert c.post("/api/v1/_t/ok").status_code == 200
        assert c.post("/api/v1/_t/err").status_code == 400
    keys = set(db.execute(select(SettingKV.key)).scalars())
    assert keys == {"t_ok"}


def test_readyz_ok_and_api_alias(client):
    """TC-WA-140 /readyz 와 /api/readyz 는 DB 연결 시 ok + mode."""
    for p in ("/readyz", "/api/readyz"):
        assert client.get(p).json() == {"status": "ok", "db": "ok", "mode": "demo"}


def test_readyz_db_down_returns_503_without_details(client, app):
    """TC-WA-141 DB 연결 실패 시 503 degraded 이고 오류 상세는 노출하지 않는다."""
    class Broken:
        def connect(self):
            from sqlalchemy.exc import OperationalError
            raise OperationalError("SELECT 1", {}, Exception("password authentication failed for user x"))

    app.state.engine = Broken()
    r = client.get("/readyz")
    assert r.status_code == 503 and r.json() == {"status": "degraded", "db": "down", "mode": "demo"}


@pytest.fixture
def static_app(web_settings, engine, tmp_path, monkeypatch):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOPSECRET", encoding="utf-8")
    monkeypatch.setenv("YTWEB_STATIC_DIR", str(root))
    with TestClient(create_app(web_settings, router_modules=CORE_ROUTERS), base_url=ORIGIN) as c:
        yield c


def test_static_serves_index_and_assets(static_app):
    """TC-WA-142 YTWEB_STATIC_DIR 가 있으면 / 는 index.html, 정적 자산은 그대로 서빙."""
    assert "INDEX" in static_app.get("/").text
    r = static_app.get("/assets/app.js")
    assert r.status_code == 200 and "console.log" in r.text


def test_static_spa_fallback_for_client_routes(static_app):
    """TC-WA-143 클라이언트 라우트(/videos/abc)는 index.html 로 대체된다."""
    assert "INDEX" in static_app.get("/videos/abc").text


def test_static_does_not_swallow_api_or_health(static_app):
    """TC-WA-144 /api 아래 없는 경로는 index 가 아니라 404 problem+json, healthz 는 JSON."""
    r = static_app.get("/api/v1/nothing")
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert static_app.get("/healthz").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt", "/..%2fsecret.txt"])
def test_static_path_traversal_blocked(static_app, path):
    """TC-WA-145 경로 이동(../) 으로 정적 폴더 밖 파일을 읽을 수 없다."""
    r = static_app.get(path)
    assert "TOPSECRET" not in r.text


def test_static_ignored_when_dir_missing(web_settings, engine, tmp_path, monkeypatch):
    """TC-WA-146 폴더가 없으면 정적 서빙을 켜지 않는다(404)."""
    monkeypatch.setenv("YTWEB_STATIC_DIR", str(tmp_path / "nope"))
    with TestClient(create_app(web_settings, router_modules=CORE_ROUTERS), base_url=ORIGIN) as c:
        assert c.get("/").status_code == 404
