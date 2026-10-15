"""관리자 로그인(DEC-055) + 웹 최초 설정(DEC-056): 로그인·실패 잠금·60분 무활동 만료·최초 계정 만들기·감사 기록. 값은 모두 시험용 가짜다."""
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
    return replace(web_settings, admin_login=True, session_idle_minutes=60)


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
    """계정이 이미 있는 상태(웹 최초 설정을 마친 뒤)의 클라이언트. 로그인 쿠키는 없다."""
    with TestClient(lapp, base_url=ORIGIN) as c:
        with lapp.state.session_factory() as db:
            admin_account.create_admin(db, ID, PW, now=lapp.state.clock())
            db.commit()
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
        with app.state.session_factory() as db:
            admin_account.create_admin(db, ID, PW, now=clock())
            db.commit()
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


# ───────────── 웹 최초 설정(DEC-056) ─────────────

@pytest.fixture
def sc(lapp):
    """계정이 아직 없는 상태(서버를 처음 띄운 직후)의 클라이언트."""
    with TestClient(lapp, base_url=ORIGIN) as c:
        yield c


def _setup(c, login_id=ID, password=PW, headers=H):
    return c.post("/api/v1/auth/setup", json={"login_id": login_id, "password": password}, headers=headers)


def test_me_says_setup_required_when_no_account(sc):
    """TC-AL-201 계정이 없으면 setup_required=true, login_required=false(화면이 '계정 만들기'를 보여 준다)."""
    body = sc.get("/api/v1/auth/me").json()
    assert body["setup_required"] is True and body["login_required"] is False and body["authenticated"] is False


def test_setup_creates_account_logs_in_and_closes_forever(sc, lapp):
    """TC-AL-202 최초 설정: 계정 생성 + 바로 로그인(쿠키) + 이후 setup 은 409 setup_closed, me 는 login_required."""
    r = _setup(sc)
    assert r.status_code == 200 and r.json()["admin_login_id"] == ID and r.json()["idle_timeout_seconds"] == 3600
    assert sc.get("/api/v1/settings").status_code == 200
    again = _setup(TestClient(lapp, base_url=ORIGIN), "other123", "Another-Passw0rd!")
    assert again.status_code == 409 and again.json()["code"] == "setup_closed"
    other = TestClient(lapp, base_url=ORIGIN)
    me = other.get("/api/v1/auth/me").json()
    assert me["login_required"] is True and me["setup_required"] is False
    with lapp.state.session_factory() as db:
        acc = db.scalars(select(AdminAccount)).one()
    assert acc.login_id == ID and acc.password_hash.startswith("scrypt$") and PW not in acc.password_hash


def test_setup_validates_format_and_does_not_echo(sc):
    """TC-AL-203 아이디·비밀번호 규칙 위반은 422 setup_invalid, 입력한 비밀번호는 응답에 없음, 계정은 만들어지지 않음."""
    for lid, pw in (("abc", PW), ("ab-cd", PW), ("a" * 21, PW), (ID, "short"), (ID, "p" * 65)):
        r = _setup(sc, lid, pw)
        assert r.status_code == 422 and r.json()["code"] == "setup_invalid" and pw not in r.text, (lid, pw)
    assert sc.get("/api/v1/auth/me").json()["setup_required"] is True


def test_setup_needs_allowed_origin_before_body(sc):
    """TC-AL-204 출처가 없거나 다르면 403(본문이 틀려도 출처가 먼저), same-site 도 거부."""
    assert _setup(sc, headers={}).status_code == 403
    assert _setup(sc, headers={"Origin": "http://evil.example"}).status_code == 403
    assert sc.post("/api/v1/auth/setup", json={}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert _setup(sc, headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-site"}).status_code == 403
    assert sc.get("/api/v1/auth/me").json()["setup_required"] is True


def test_setup_rate_limited(login_settings, engine, clock, fake_time, monkeypatch):
    """TC-AL-205 최초 설정 요청에도 분당 속도 제한이 걸린다."""
    app = _make(login_settings, clock, fake_time, monkeypatch, auth=3)
    with TestClient(app, base_url=ORIGIN) as c:
        codes = [_setup(c, "ab", PW).status_code for _ in range(4)]
    assert codes == [422, 422, 422, 429]


def test_setup_disabled_when_login_mode_off(app, client):
    """TC-AL-206 로그인 모드가 꺼져 있으면 setup 은 409 login_disabled."""
    r = _setup(client)
    assert r.status_code == 409 and r.json()["code"] == "login_disabled"


def test_setup_audit_records_without_secrets(sc, lapp):
    """TC-AL-207 admin.setup / admin.setup_denied 가 감사 기록에 남고 아이디·비밀번호 값은 없다."""
    _setup(sc, "ab", PW)
    _setup(sc)
    with lapp.state.session_factory() as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.action.like("admin.setup%")).order_by(AuditLog.id)).all()
    assert [r.action for r in rows] == ["admin.setup_denied", "admin.setup"]
    dump = " ".join(f"{r.detail} {r.target_id}" for r in rows)
    assert PW not in dump and ID not in dump


def test_login_before_setup_says_not_configured(sc):
    """TC-AL-208 계정이 없을 때 로그인 요청은 409 login_not_configured(화면은 setup 으로 안내)."""
    r = _login(sc)
    assert r.status_code == 409 and r.json()["code"] == "login_not_configured"


def test_reset_clears_account_sessions_and_lock(lc, lapp, factory_url=None):
    """TC-AL-209 reset: 계정·세션·실패 잠금을 지우면 다시 setup_required, 잠금 상태도 초기화."""
    for _ in range(5):
        _login(lc, password="bad-password-1")
    assert _login(lc).status_code == 429
    with lapp.state.session_factory() as db:
        assert admin_account.reset_admin(db) == 1
        db.commit()
    assert lc.get("/api/v1/auth/me").json()["setup_required"] is True
    assert _setup(lc).status_code == 200  # 새 계정은 잠금 없이 바로 가능
    other = TestClient(lapp, base_url=ORIGIN)
    assert _login(other).status_code == 200


def test_admin_cli_reset_runs_and_audits(login_settings, engine, monkeypatch, capsys, factory, clock):
    """TC-AL-210 `python -m ytweb.admin_cli reset` 이 계정을 지우고 감사 기록(admin.reset)을 남기며, 잘못된 인자는 종료코드 2."""
    from ytweb import admin_cli
    with factory() as db:
        admin_account.create_admin(db, ID, PW, now=clock())
        db.commit()
    monkeypatch.setenv("YTWEB_DATABASE_URL", login_settings.database_url)
    assert admin_cli.main(["reset"]) == 0
    assert "초기화했습니다" in capsys.readouterr().out and PW not in capsys.readouterr().out
    with factory() as db:
        assert db.scalars(select(AdminAccount)).all() == []
        assert [r.action for r in db.scalars(select(AuditLog).where(AuditLog.action == "admin.reset")).all()] == ["admin.reset"]
    assert admin_cli.main([]) == 2 and admin_cli.main(["x"]) == 2
