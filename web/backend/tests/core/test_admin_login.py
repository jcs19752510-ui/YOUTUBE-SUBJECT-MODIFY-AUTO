"""관리자 로그인(DEC-055, 개정 DEC-058): 로그인·실패 잠금·60분 무활동 만료·로컬 등록 명령(해시만 DB 저장)·웹 계정 생성 경로 없음·감사 기록. 값은 모두 시험용 가짜다."""
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
    """등록 명령으로 관리자 계정이 이미 등록된 상태의 서버. 로그인 쿠키는 없다."""
    with TestClient(lapp, base_url=ORIGIN) as c:
        with lapp.state.session_factory() as db:
            admin_account.register_admin(db, ID, PW, now=lapp.state.clock())
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
            admin_account.register_admin(db, ID, PW, now=clock())
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
    """TC-AL-021 YTWEB_ADMIN_LOGIN=1 이면 무활동 만료 기본 60분. 꺼져 있으면 30분(기존). 계정 값(아이디·비밀번호)을 설정으로 받지 않는다(DEC-058)."""
    base = {"YTWEB_DATABASE_URL": "sqlite://", "YTWEB_ADMIN_LOGIN": "1", "YTWEB_ADMIN_ID": "leak1234", "YTWEB_ADMIN_PASSWORD": "Leak-Passw0rd!"}
    s = load_web_settings(base)
    assert s.admin_login and s.session_idle_minutes == 60
    assert not any(hasattr(s, a) for a in ("admin_id", "admin_password", "admin_id_file", "admin_password_file"))
    assert "Leak-Passw0rd!" not in repr(s)
    assert load_web_settings({**base, "YTWEB_SESSION_IDLE_MINUTES": "15"}).session_idle_minutes == 15
    off = load_web_settings({"YTWEB_DATABASE_URL": "sqlite://"})
    assert off.admin_login is False and off.session_idle_minutes == 30


# ───────────── DEC-058: 계정은 로컬 등록 명령으로만, 평문은 어디에도 없다 ─────────────

def test_no_account_creation_route_exists(lc):
    """TC-AL-401 계정을 만드는 API 가 없다(404/405). 임의 계정으로 로그인 불가."""
    for path in ("/api/v1/auth/setup", "/api/v1/auth/register", "/api/v1/auth/signup", "/api/v1/auth/admin"):
        for m in ("post", "put"):
            r = getattr(lc, m)(path, json={"login_id": "other123", "password": "Another-Passw0rd!"}, headers=H)
            assert r.status_code in (404, 405), (path, m, r.status_code)
    assert _login(lc, "other123", "Another-Passw0rd!").status_code == 401
    assert "setup_required" not in lc.get("/api/v1/auth/me").json()


def test_openapi_has_no_account_creation_operation(lapp):
    """TC-AL-402 OpenAPI 에 계정 생성·초기화 경로가 없다."""
    paths = lapp.openapi()["paths"]
    assert not [p for p in paths if any(k in p for k in ("setup", "register", "signup", "reset"))]
    assert "/api/v1/auth/login" in paths


def test_register_stores_hash_only_and_login_works(lc, lapp):
    """TC-AL-403 등록한 계정은 해시만 DB 에 있고 로그인할 수 있다."""
    with lapp.state.session_factory() as db:
        acc = db.scalars(select(AdminAccount)).one()
    assert acc.login_id == ID and acc.password_hash.startswith("scrypt$") and PW not in acc.password_hash
    assert _login(lc).status_code == 200


def test_no_account_means_nobody_can_log_in_and_message_tells_how(lapp):
    """TC-AL-404 계정이 등록되지 않았으면 아무도 로그인할 수 없고(409), 안내가 등록 명령을 알려 준다(값 없음)."""
    with TestClient(lapp, base_url=ORIGIN) as c:
        r = _login(c)
        assert r.status_code == 409 and r.json()["code"] == "login_not_configured"
        assert "register-admin.bat" in r.json()["hint"] and PW not in r.text
        assert c.get("/api/v1/settings").status_code == 401
        assert c.get("/api/v1/auth/me").json()["login_required"] is True


def test_register_replaces_account_and_ends_sessions_and_lock(lc, lapp):
    """TC-AL-405 다시 등록하면 계정이 교체되고(1명 유지) 세션이 모두 끝나며 실패 잠금이 초기화된다."""
    assert _login(lc).status_code == 200
    for _ in range(5):
        _login(TestClient(lapp, base_url=ORIGIN), password="bad-password-1")
    now = lapp.state.clock()
    with lapp.state.session_factory() as db:
        assert admin_account.register_admin(db, "newadmin1", "Another-Passw0rd!", now=now) == "replaced"
        db.commit()
        assert [a.login_id for a in db.scalars(select(AdminAccount)).all()] == ["newadmin1"]
        assert db.scalars(select(SessionRow)).all() == []
    assert lc.get("/api/v1/settings").status_code == 401  # 이전 로그인 끝남
    assert _login(TestClient(lapp, base_url=ORIGIN), "newadmin1", "Another-Passw0rd!").status_code == 200  # 잠금 초기화


def test_register_validates_format(factory, clock):
    """TC-AL-406 형식 위반(아이디 4~20 영숫자, 비밀번호 8~64)은 거부되고 계정이 바뀌지 않는다."""
    with factory() as db:
        for lid, pw in (("abc", PW), ("ab-cd", PW), ("a" * 21, PW), (ID, "short"), (ID, "p" * 65)):
            with pytest.raises(ValueError):
                admin_account.register_admin(db, lid, pw, now=clock())
        assert not admin_account.has_admin(db)


def test_admin_cli_register_prompts_hidden_and_saves_hash(login_settings, engine, monkeypatch, capsys, factory):
    """TC-AL-407 register: TTY 에서만, 비밀번호는 getpass(숨김)로 두 번, DB 에 해시만, 출력·감사 기록에 값 없음."""
    from ytweb import admin_cli
    monkeypatch.setenv("YTWEB_DATABASE_URL", login_settings.database_url)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": ID)
    pws = iter([PW, PW])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(pws))
    assert admin_cli.main(["status"]) == 0 and capsys.readouterr().out.strip() == "NONE"
    assert admin_cli.main(["register"]) == 0
    out = capsys.readouterr()
    assert PW not in out.out + out.err and ID not in out.out.replace("관리자 아이디", "")
    assert admin_cli.main(["status"]) == 0 and capsys.readouterr().out.strip() == "REGISTERED"
    with factory() as db:
        acc = db.scalars(select(AdminAccount)).one()
        assert acc.login_id == ID and acc.password_hash.startswith("scrypt$") and PW not in acc.password_hash
        rows = db.scalars(select(AuditLog).where(AuditLog.action == "admin.register")).all()
        assert len(rows) == 1 and PW not in str(rows[0].detail) and ID not in str(rows[0].detail)


def test_admin_cli_register_rejects_non_tty_mismatch_and_bad_format(login_settings, engine, monkeypatch, capsys, factory):
    """TC-AL-408 파이프 입력(비 TTY)·비밀번호 불일치·형식 오류는 거부되고 계정이 생기지 않는다. 잘못된 인자는 종료코드 2."""
    from ytweb import admin_cli
    monkeypatch.setenv("YTWEB_DATABASE_URL", login_settings.database_url)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    assert admin_cli.main(["register"]) == 2
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": ID)
    pws = iter([PW, "Different-Passw0rd!"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(pws))
    assert admin_cli.main(["register"]) == 1
    monkeypatch.setattr("builtins.input", lambda prompt="": "ab")
    pws2 = iter([PW, PW])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(pws2))
    assert admin_cli.main(["register"]) == 1
    with factory() as db:
        assert db.scalars(select(AdminAccount)).all() == []
    assert admin_cli.main([]) == 2 and admin_cli.main(["x"]) == 2
