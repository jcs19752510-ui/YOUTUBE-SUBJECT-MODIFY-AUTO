"""관리자 로그인(DEC-055, 개정 DEC-057): 로그인·실패 잠금·60분 무활동 만료·.env 값으로 계정 준비·웹 계정 생성 경로 없음·감사 기록. 값은 모두 시험용 가짜다."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import ORIGIN, FakeClock, hdr
from ytweb.app import create_app
from ytweb.config import WebSettings, load_web_settings
from ytweb.core import admin_account
from ytweb.core.ratelimit import RateLimits
from ytweb.db.models import AdminAccount, AuditLog, SessionRow

ID, PW = "test-admin".replace("-", ""), "Test-Passw0rd!"  # testadmin
ROUTERS = ["ytweb.routers.health", "ytweb.routers.auth", "ytweb.routers.settings", "ytweb.routers.audit"]
H = {"Origin": ORIGIN}


@pytest.fixture
def login_settings(web_settings: WebSettings) -> WebSettings:
    return replace(web_settings, admin_login=True, session_idle_minutes=60, admin_id=ID, admin_password=PW)


def _make(settings, clock, fake_time, monkeypatch, **limits):
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "1")
    monkeypatch.delenv("YTWEB_STATIC_DIR", raising=False)
    rl = RateLimits(global_per_min=10_000, write_per_min=10_000, auth_per_min=limits.get("auth", 10_000))
    return create_app(settings, clock=clock, router_modules=ROUTERS, time_fn=fake_time, rate_limits=rl)


@pytest.fixture
def lapp(login_settings, engine, clock, fake_time, monkeypatch):
    return _make(login_settings, clock, fake_time, monkeypatch)


@pytest.fixture
def lc(lapp):
    """서버를 시작한 상태: 시작할 때 .env 값(관리자 아이디·비밀번호)이 계정으로 준비된다. 로그인 쿠키는 없다."""
    with TestClient(lapp, base_url=ORIGIN) as c:
        yield c


def _login(c, login_id=ID, password=PW):
    return c.post("/api/v1/auth/login", json={"login_id": login_id, "password": password}, headers=H)


def test_me_before_login_says_login_required(lc):
    """TC-AL-001 로그인 모드에서 미인증이면 login_required=true, PIN 은 요구하지 않는다."""
    body = lc.get("/api/v1/auth/me").json()
    assert body["authenticated"] is False and body["login_required"] is True
    assert body["pin_required"] is False and body["csrf_token"] is None and body["admin_login_id"] is None
    assert body["idle_timeout_seconds"] == 3600


def test_anonymous_session_is_blocked_in_login_mode(lc):
    """TC-AL-002 익명 세션 발급은 막힌다(403 login_required)."""
    r = lc.post("/api/v1/auth/session", json={}, headers=H)
    assert r.status_code == 403 and r.json()["code"] == "login_required"


def test_protected_api_requires_login(lc):
    """TC-AL-003 로그인 전 보호 API 는 401 session_required."""
    assert lc.get("/api/v1/settings").status_code == 401
    assert lc.get("/api/v1/audit").status_code == 401


def test_login_success_sets_hardened_cookie_and_opens_api(lc):
    """TC-AL-004 로그인 성공: 쿠키(HttpOnly·SameSite=Strict·Path=/api), csrf, 보호 API 접근."""
    r = _login(lc)
    assert r.status_code == 200
    j = r.json()
    assert j["admin_login_id"] == ID and j["idle_timeout_seconds"] == 3600 and j["csrf_token"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie
    assert "secure" not in cookie.replace("samesite", "")  # http://127.0.0.1 용
    assert lc.get("/api/v1/settings").status_code == 200
    me = lc.get("/api/v1/auth/me").json()
    assert me["authenticated"] is True and me["login_required"] is False and me["admin_login_id"] == ID


def test_wrong_password_and_wrong_id_look_identical(lc):
    """TC-AL-005 아이디 오류와 비밀번호 오류의 응답이 같다(계정 열거 방지)."""
    a = _login(lc, password="Wrong-Passw0rd!")
    b = _login(lc, login_id="nobody1", password=PW)
    assert a.status_code == b.status_code == 401
    assert a.json()["code"] == b.json()["code"] == "login_invalid"
    assert a.json()["title"] == b.json()["title"] == admin_account.INVALID_MESSAGE
    assert lc.get("/api/v1/settings").status_code == 401


def test_lockout_after_five_failures_then_expires_and_doubles(lc, clock):
    """TC-AL-006 5회 실패 → 5분 잠금(올바른 비밀번호도 거부), 5분 뒤 다시 가능, 다시 5회 실패하면 10분."""
    for _ in range(4):
        assert _login(lc, password="bad-password-1").status_code == 401
    r = _login(lc, password="bad-password-1")
    assert r.status_code == 429 and r.json()["code"] == "login_locked" and int(r.headers["retry-after"]) == 300
    assert _login(lc).status_code == 429  # 잠금 중에는 맞는 비밀번호도 거부
    clock.advance(minutes=5, seconds=1)
    for _ in range(4):
        assert _login(lc, password="bad-password-1").status_code == 401
    r = _login(lc, password="bad-password-1")
    assert r.status_code == 429 and int(r.headers["retry-after"]) == 600
    clock.advance(minutes=10, seconds=1)
    assert _login(lc).status_code == 200


def test_success_resets_failure_counter(lc):
    """TC-AL-007 성공하면 실패 횟수가 초기화된다(4회 실패 → 성공 → 4회 실패해도 잠기지 않음)."""
    for _ in range(4):
        _login(lc, password="bad-password-1")
    assert _login(lc).status_code == 200
    for _ in range(4):
        assert _login(lc, password="bad-password-1").status_code == 401


def test_idle_timeout_60_minutes_expires_session(lc, clock):
    """TC-AL-008 마지막 사용 59분 뒤에는 유효, 60분 이상 아무 요청이 없으면 401 session_required."""
    _login(lc)
    clock.advance(minutes=59)
    assert lc.get("/api/v1/settings").status_code == 200  # 사용했으므로 시계가 다시 시작
    clock.advance(minutes=59)
    assert lc.get("/api/v1/auth/me").json()["authenticated"] is True  # '계속 사용'(me 호출)
    clock.advance(minutes=60)
    r = lc.get("/api/v1/settings")
    assert r.status_code == 401 and r.json()["code"] == "session_required"
    assert lc.get("/api/v1/auth/me").json()["login_required"] is True


def test_new_login_ends_previous_sessions(lc, lapp, clock):
    """TC-AL-009 새 로그인은 이전 세션을 모두 끝낸다(세션 고정 방지)."""
    _login(lc)
    old_cookie = lc.cookies.get("ytw_session", path="/api")
    other = TestClient(lapp, base_url=ORIGIN)
    assert _login(other).status_code == 200
    stale = TestClient(lapp, base_url=ORIGIN)
    stale.cookies.set("ytw_session", old_cookie, path="/api")
    assert stale.get("/api/v1/settings").status_code == 401
    assert other.get("/api/v1/settings").status_code == 200


def test_logout_ends_session(lc):
    """TC-AL-010 로그아웃 뒤 같은 쿠키로 보호 API 를 부르면 401."""
    csrf = _login(lc).json()["csrf_token"]
    assert lc.delete("/api/v1/auth/session", headers=hdr(csrf)).status_code == 204
    assert lc.get("/api/v1/settings").status_code == 401


def test_login_needs_allowed_origin(lc):
    """TC-AL-011 출처 헤더가 없거나 허용 밖이면 403(비밀번호 확인 전)."""
    r = lc.post("/api/v1/auth/login", json={"login_id": ID, "password": PW})
    assert r.status_code == 403
    r = lc.post("/api/v1/auth/login", json={"login_id": ID, "password": PW}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert lc.get("/api/v1/settings").status_code == 401


def test_login_body_validation_does_not_echo_password(lc):
    """TC-AL-012 잘못된 본문은 422 이고 입력한 비밀번호를 응답에 되돌리지 않는다."""
    secret = "ZZ-secret-value-ZZ"
    r = lc.post("/api/v1/auth/login", json={"login_id": ID, "password": secret, "x": 1}, headers=H)
    assert r.status_code == 422 and secret not in r.text
    assert lc.post("/api/v1/auth/login", json={"login_id": "", "password": "a"}, headers=H).status_code == 422
    assert lc.post("/api/v1/auth/login", json={"login_id": ID, "password": "p" * 129}, headers=H).status_code == 422


def test_audit_records_login_events_without_secrets(lc, lapp):
    """TC-AL-013 login.denied / login.success 가 감사 기록에 남고 비밀번호·아이디 값은 없다."""
    _login(lc, password="Wrong-Passw0rd!")
    _login(lc)
    with lapp.state.session_factory() as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.action.like("login.%")).order_by(AuditLog.id)).all()
    assert [r.action for r in rows] == ["login.denied", "login.success"]
    dump = " ".join(f"{r.detail} {r.target_id}" for r in rows)
    assert PW not in dump and "Wrong-Passw0rd!" not in dump and ID not in dump


def test_password_is_stored_only_as_hash(lc, lapp):
    """TC-AL-014 DB 에는 scrypt 해시만 있고 원문이 없다."""
    with lapp.state.session_factory() as db:
        acc = db.scalars(select(AdminAccount)).one()
    assert acc.login_id == ID and acc.password_hash.startswith("scrypt$") and PW not in acc.password_hash


def test_login_rate_limit_applies(login_settings, engine, clock, fake_time, monkeypatch):
    """TC-AL-015 로그인 요청에도 분당 속도 제한(auth_per_min)이 걸린다."""
    app = _make(login_settings, clock, fake_time, monkeypatch, auth=3)
    with TestClient(app, base_url=ORIGIN) as c:
        codes = [_login(c, password="bad-password-1").status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_login_disabled_when_mode_off(app, client):
    """TC-AL-017 로그인 모드가 꺼져 있으면(기본) 기존 동작 그대로: /login 409, 익명 세션 가능, login_required=false."""
    assert client.post("/api/v1/auth/login", json={"login_id": ID, "password": PW}, headers=H).status_code == 409
    me = client.get("/api/v1/auth/me").json()
    assert me["login_required"] is False and me["pin_required"] is False
    assert client.post("/api/v1/auth/session", json={}, headers=H).status_code == 200


def test_format_validation():
    """TC-AL-020 아이디 영숫자 4~20자, 비밀번호 8~64자."""
    f = admin_account.validate_credentials_format
    assert f("abcd", "12345678") is None and f("a" * 20, "p" * 64) is None
    assert f("abc", "12345678") and f("a" * 21, "12345678") and f("ab-cd", "12345678")
    assert f("abcd", "1234567") and f("abcd", "p" * 65)


def test_config_login_defaults():
    """TC-AL-021 YTWEB_ADMIN_LOGIN=1 이면 무활동 만료 기본 60분. 꺼져 있으면 30분(기존). 비밀 파일 설정은 더 이상 없다(DEC-056)."""
    base = {"YTWEB_DATABASE_URL": "sqlite://", "YTWEB_ADMIN_LOGIN": "1"}
    s = load_web_settings(base)
    assert s.admin_login and s.session_idle_minutes == 60
    assert load_web_settings({**base, "YTWEB_SESSION_IDLE_MINUTES": "15"}).session_idle_minutes == 15
    off = load_web_settings({"YTWEB_DATABASE_URL": "sqlite://"})
    assert off.admin_login is False and off.session_idle_minutes == 30
    assert not hasattr(s, "admin_id_file") and not hasattr(s, "admin_password_file")


# ───────────── DEC-057: 웹에서 계정을 만들 수 없다 · .env 값으로만 준비 ─────────────

def test_no_account_creation_route_exists(lc):
    """TC-AL-301 계정을 만드는 API(/auth/setup 등)가 없다(404/405). 다른 사람이 계정을 만들 방법이 없다."""
    for path in ("/api/v1/auth/setup", "/api/v1/auth/register", "/api/v1/auth/signup", "/api/v1/auth/admin"):
        for m in ("post", "put"):
            r = getattr(lc, m)(path, json={"login_id": "other123", "password": "Another-Passw0rd!"}, headers=H)
            assert r.status_code in (404, 405), (path, m, r.status_code)
    assert _login(lc, "other123", "Another-Passw0rd!").status_code == 401
    assert "setup_required" not in lc.get("/api/v1/auth/me").json()


def test_openapi_has_no_account_creation_operation(lapp):
    """TC-AL-302 OpenAPI 에 계정 생성·초기화 경로가 없다."""
    paths = lapp.openapi()["paths"]
    assert not [p for p in paths if any(k in p for k in ("setup", "register", "signup", "reset"))]
    assert "/api/v1/auth/login" in paths


def test_account_comes_only_from_env_values(lc, lapp):
    """TC-AL-303 DB 의 관리자는 .env 값 1개뿐이고 비밀번호는 해시로만 있다."""
    with lapp.state.session_factory() as db:
        acc = db.scalars(select(AdminAccount)).one()
    assert acc.login_id == ID and acc.password_hash.startswith("scrypt$") and PW not in acc.password_hash


def test_missing_env_means_nobody_can_log_in(web_settings, engine, clock, fake_time, monkeypatch):
    """TC-AL-304 .env 값이 없으면 아무도 로그인할 수 없다(닫힘): 409 login_not_configured + 설정 방법 안내, 보호 API 401."""
    s = replace(web_settings, admin_login=True, session_idle_minutes=60)
    with TestClient(_make(s, clock, fake_time, monkeypatch), base_url=ORIGIN) as c:
        r = _login(c)
        assert r.status_code == 409 and r.json()["code"] == "login_not_configured"
        assert ".env" in r.json()["hint"] and "YTWEB_ADMIN_PASSWORD" in r.json()["hint"]
        assert PW not in r.text
        assert c.get("/api/v1/settings").status_code == 401
        assert c.get("/api/v1/auth/me").json()["login_required"] is True


def test_sync_created_unchanged_updated_missing_invalid(login_settings, factory, clock):
    """TC-AL-305 .env → 계정 반영: 생성·변경 없음·비밀번호 변경(세션 종료·잠금 초기화)·값 없음·형식 오류."""
    now = clock()
    with factory() as db:
        assert admin_account.sync_admin_from_env(db, login_settings, now=now) == "created"
        db.commit()
        assert admin_account.sync_admin_from_env(db, login_settings, now=now) == "unchanged"
        db.add(SessionRow(id="x" * 64, csrf_token="c", created_at=now, expires_at=now, last_seen=now))
        db.commit()
        changed = replace(login_settings, admin_password="Another-Passw0rd!")
        assert admin_account.sync_admin_from_env(db, changed, now=now) == "updated"
        db.commit()
        assert db.scalars(select(SessionRow)).all() == []
        assert admin_account.authenticate(db, ID, "Another-Passw0rd!", now=now).login_id == ID
        assert admin_account.sync_admin_from_env(db, replace(login_settings, admin_password="short"), now=now) == "invalid"
        assert admin_account.sync_admin_from_env(db, replace(login_settings, admin_id="ab"), now=now) == "invalid"
        assert admin_account.sync_admin_from_env(db, replace(login_settings, admin_id=None), now=now) == "missing"
        assert admin_account.sync_admin_from_env(db, replace(login_settings, admin_password=None), now=now) == "missing"


def test_changed_id_replaces_account(login_settings, factory, clock):
    """TC-AL-306 아이디를 바꿔도 관리자는 1명(이전 계정은 사라진다)."""
    now = clock()
    with factory() as db:
        admin_account.sync_admin_from_env(db, login_settings, now=now)
        db.commit()
        assert admin_account.sync_admin_from_env(db, replace(login_settings, admin_id="newadmin1"), now=now) == "updated"
        db.commit()
        assert [a.login_id for a in db.scalars(select(AdminAccount)).all()] == ["newadmin1"]


def test_special_chars_password_and_secret_not_in_repr(login_settings, factory, clock):
    """TC-AL-307 특수문자(예: **) 비밀번호가 그대로 쓰이고, 설정 객체의 repr 에 비밀번호가 나오지 않는다."""
    s = replace(login_settings, admin_password="Star**Passw0rd")
    assert "Star**Passw0rd" not in repr(s)
    now = clock()
    with factory() as db:
        assert admin_account.sync_admin_from_env(db, s, now=now) == "created"
        assert admin_account.authenticate(db, ID, "Star**Passw0rd", now=now).login_id == ID


def test_config_reads_admin_env_but_never_files():
    """TC-AL-308 YTWEB_ADMIN_ID/PASSWORD 만 읽고 파일 설정은 더 이상 없다."""
    s = load_web_settings({"YTWEB_DATABASE_URL": "sqlite://", "YTWEB_ADMIN_LOGIN": "1", "YTWEB_ADMIN_ID": " testadmin ", "YTWEB_ADMIN_PASSWORD": "Test-Passw0rd!"})
    assert s.admin_id == "testadmin" and s.admin_password == "Test-Passw0rd!"
    assert not hasattr(s, "admin_id_file") and not hasattr(s, "admin_password_file")
    assert load_web_settings({"YTWEB_DATABASE_URL": "sqlite://"}).admin_id is None
