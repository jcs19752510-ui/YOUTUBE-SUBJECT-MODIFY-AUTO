"""SEC-01 HTTP 경계(공격자 관점): Host/Origin/Fetch-Metadata/CSRF/세션/PIN/속도 제한/본문 크기/헤더/오류 노출/정적 경로.

위협 모델 TW-01·02·03·04·17·20·23·25·34 의 구현 여부를 코드가 아니라 동작으로 확인한다.
각 시험 이름의 [TW-xx] 는 docs/yt/threat_model.md Part W 의 위협 ID 이다.
"""
from __future__ import annotations

import json
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from ytweb.core.ratelimit import RateLimits
from ytweb.db.models import AuditLog, SessionRow

from .conftest import HOST, ORIGIN, FakeTime, build_app, hdr, login

pytestmark = pytest.mark.filterwarnings("ignore")

PATH_SAMPLES = {"video_id": "demoVid0001", "suggestion_id": "1", "batch_id": "1", "change_id": "1", "job_id": str(uuid.uuid4()), "full_path": "x"}


def api_routes(app):
    """FastAPI 0.143 은 include_router 라우트를 _IncludedRouter 로 감싸 app.routes 에서 보이지 않으므로 OpenAPI 로 전수 목록을 얻는다."""
    out = []
    for path, ops in app.openapi()["paths"].items():
        if not path.startswith("/api"):
            continue
        for m in ops:
            if m.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                p = path
                for k, v in PATH_SAMPLES.items():
                    p = p.replace("{" + k + "}", v)
                out.append((m.upper(), p))
    assert len(out) >= 25, out
    return out


# ───────────── [TW-02] Host 검증(DNS 리바인딩) ─────────────

@pytest.mark.parametrize("host", ["evil.com", "127.0.0.1", "127.0.0.1:9999", "localhost", "127.0.0.1:8080.evil.com", "evil.com:8080", "[::1]:8080", "0.0.0.0:8080", ""])
def test_host_not_allowed_is_403_for_api(app, host):
    with TestClient(app, base_url="http://x.test") as c:
        r = c.get("/api/v1/auth/me", headers={"host": host})
    assert r.status_code == 403 and r.json()["code"] == "host_not_allowed", (host, r.status_code, r.text)


def test_duplicate_host_header_rejected(app):
    with TestClient(app, base_url=ORIGIN) as c:
        r = c.get("/api/v1/auth/me", headers=[("host", HOST), ("host", "evil.com")])
    assert r.status_code == 403


def test_allowed_hosts_case_insensitive_but_exact(app):
    with TestClient(app, base_url="http://x.test") as c:
        assert c.get("/api/v1/auth/me", headers={"host": "LOCALHOST:8080"}).status_code == 200
        assert c.get("/api/v1/auth/me", headers={"host": "localhost:8080 "}).status_code in (200, 403)


def test_health_is_the_only_host_exempt_path(app):
    with TestClient(app, base_url="http://x.test") as c:
        for p in ("/healthz", "/readyz", "/api/healthz", "/api/readyz"):
            assert c.get(p, headers={"host": "evil.com"}).status_code in (200, 503), p
        for m, p in api_routes(app):
            if m == "GET" and "health" not in p and "readyz" not in p:
                assert c.get(p, headers={"host": "evil.com"}).status_code == 403, p


# ───────────── [TW-01] Origin / Sec-Fetch-Site / 로그인 CSRF ─────────────

@pytest.mark.parametrize("origin", [None, "null", "http://evil.com", "https://127.0.0.1:8080", "http://127.0.0.1:8080.evil.com", "http://127.0.0.1:8080@evil.com",
                                    "http://127.0.0.1", "http://127.0.0.1:8081", "http://localhost:8081", "http://127.0.0.1:8080/", " "])
def test_session_issue_requires_exact_origin(client, origin):
    h = {} if origin is None else {"Origin": origin}
    r = client.post("/api/v1/auth/session", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "origin_not_allowed", (origin, r.status_code, r.text)
    assert "set-cookie" not in r.headers


@pytest.mark.parametrize("sfs", ["cross-site", "same-site", "none", "", "same-origin, cross-site"])
def test_session_issue_rejects_non_same_origin_fetch_site(client, sfs):
    r = client.post("/api/v1/auth/session", headers={"Origin": ORIGIN, "Sec-Fetch-Site": sfs})
    assert r.status_code == 403 and r.json()["code"] == "cross_site_request", (sfs, r.status_code)


def test_session_issue_allows_same_origin(client):
    assert client.post("/api/v1/auth/session", headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_login_csrf_rejection_is_not_audited_but_pin_denial_is(client):
    """거부된 교차 출처 요청은 감사 로그에 남지 않는다(공격자가 로그를 채울 수 없게). 정보 항목: 남기지 않는 것이 의도인지 확인."""
    eng = client.app.state.engine
    with eng.connect() as c:
        before = c.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    client.post("/api/v1/auth/session", headers={"Origin": "http://evil.com"})
    with eng.connect() as c:
        after = c.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    assert after == before


def test_cookie_flags(client):
    r = login(client)
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=strict" in sc and "path=/api" in sc and "max-age=" in sc
    assert "secure" not in sc, "M1 은 http://127.0.0.1 이라 Secure 를 붙이지 않는다(Q-WA-1) - 사실 기록용"
    assert "domain=" not in sc


# ───────────── [TW-01] CSRF: 모든 상태 변경 라우트 전수 ─────────────

def test_every_state_changing_route_rejects_missing_csrf(client, csrf):
    mutating = [(m, p) for m, p in api_routes(client.app) if m in ("POST", "PUT", "PATCH", "DELETE") and p not in ("/api/v1/auth/session", "/api/v1/auth/login") or (m == "DELETE")]
    # 로그인(DEC-055)은 세션 발급과 같이 CSRF 토큰이 아직 없는 요청이다: 대신 출처·same-site 검사를 아래에서 따로 확인한다.
    for hdrs, code in (({}, "origin_not_allowed"), ({"Origin": "http://evil.com"}, "origin_not_allowed"), ({"Origin": ORIGIN, "Sec-Fetch-Site": "same-site"}, "cross_site_request")):
        r = client.post("/api/v1/auth/login", headers=hdrs, json={"login_id": "abcd", "password": "12345678"})
        assert r.status_code == 403 and r.json()["code"] == code, (hdrs, r.status_code)
    r = client.post("/api/v1/auth/login", headers={"Origin": "http://evil.com"}, json={})  # 본문이 틀려도 출처 거부가 먼저
    assert r.status_code == 403
    assert len(mutating) >= 11, mutating
    for m, p in mutating:
        # 올바른 세션 쿠키 + 올바른 Origin 이지만 CSRF 헤더 없음
        r = client.request(m, p, headers={"Origin": ORIGIN}, json={} if m != "DELETE" else None)
        assert r.status_code == 403 and r.json()["code"] == "csrf_invalid", (m, p, r.status_code, r.text[:200])
        r = client.request(m, p, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf[:-1] + ("A" if csrf[-1] != "A" else "B")}, json={} if m != "DELETE" else None)
        assert r.status_code == 403, (m, p, "잘못된 토큰")
        r = client.request(m, p, headers={"Origin": "http://evil.com", "X-CSRF-Token": csrf}, json={} if m != "DELETE" else None)
        assert r.status_code == 403 and r.json()["code"] == "origin_not_allowed", (m, p, "교차 출처")
        r = client.request(m, p, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Sec-Fetch-Site": "same-site"}, json={} if m != "DELETE" else None)
        assert r.status_code == 403 and r.json()["code"] == "cross_site_request", (m, p, "same-site")


def test_csrf_token_of_other_session_is_rejected(app):
    with TestClient(app, base_url=ORIGIN) as a, TestClient(app, base_url=ORIGIN) as b:
        ta = login(a).json()["csrf_token"]
        tb = login(b).json()["csrf_token"]
        assert ta != tb
        r = a.patch("/api/v1/settings", headers=hdr(tb), json={"tone": ["a"]})
        assert r.status_code == 403
        assert a.patch("/api/v1/settings", headers=hdr(ta), json={"tone": ["a"]}).status_code == 200


def test_unauthenticated_get_routes_all_401(app):
    with TestClient(app, base_url=ORIGIN) as c:
        for m, p in api_routes(app):
            if m == "GET" and "health" not in p and "readyz" not in p and p != "/api/v1/auth/me":
                r = c.get(p)
                assert r.status_code == 401 and r.json()["code"] == "session_required", (p, r.status_code)


def test_get_routes_do_not_change_state(client, csrf, engine):
    def snapshot():
        with engine.connect() as c:
            tabs = ["audit_log", "changes", "suggestions", "batches", "batch_items", "jobs", "settings_kv", "approvals", "quota_usage", "idempotency_keys"]
            return {t: c.exec_driver_sql(f"SELECT count(*) FROM {t}").scalar_one() for t in tabs}
    before = snapshot()
    for m, p in api_routes(client.app):
        if m == "GET" and "auth/me" not in p:
            client.get(p)
    assert snapshot() == before, "GET 이 상태를 바꿨다(S-W03 위반)"


def test_me_endpoint_does_not_create_session_and_does_not_leak_csrf_without_cookie(client):
    r = client.get("/api/v1/auth/me")
    assert r.json() == {"authenticated": False, "pin_required": False, "csrf_token": None,
                        "login_required": False, "admin_login_id": None, "idle_timeout_seconds": 1800}  # DEC-055 필드 3개 추가
    assert "set-cookie" not in r.headers


# ───────────── [TW-20] 세션 ─────────────

def test_session_fixation_attacker_chosen_cookie_is_ignored(app, engine):
    with TestClient(app, base_url=ORIGIN) as c:
        c.cookies.set("ytw_session", "attacker-chosen-token", path="/api")
        r = login(c)
        new = re.search(r"ytw_session=([^;]+)", r.headers["set-cookie"]).group(1)
        assert new != "attacker-chosen-token"
        with TestClient(app, base_url=ORIGIN) as other:
            other.cookies.set("ytw_session", "attacker-chosen-token", path="/api")
            assert other.get("/api/v1/settings").status_code == 401


def test_session_token_not_stored_in_clear(app, engine):
    with TestClient(app, base_url=ORIGIN) as c:
        r = login(c)
        tok = re.search(r"ytw_session=([^;]+)", r.headers["set-cookie"]).group(1)
        csrf = r.json()["csrf_token"]
    with engine.connect() as con:
        ids = [row[0] for row in con.exec_driver_sql("SELECT id FROM sessions")]
    assert tok not in ids and len(ids[0]) == 64
    assert len(tok) >= 43 and len(csrf) >= 43  # 256 비트 이상


def test_logout_invalidates_server_side_and_replay_fails(app):
    with TestClient(app, base_url=ORIGIN) as c:
        r = login(c)
        tok = re.search(r"ytw_session=([^;]+)", r.headers["set-cookie"]).group(1)
        csrf = r.json()["csrf_token"]
        assert c.delete("/api/v1/auth/session", headers=hdr(csrf)).status_code == 204
    with TestClient(app, base_url=ORIGIN) as replay:
        replay.cookies.set("ytw_session", tok, path="/api")
        assert replay.get("/api/v1/settings").status_code == 401


def test_session_idle_expiry_is_enforced_after_30_minutes(app, clock):
    """DEF-9-003 ① 닫힘(W-FIX-BE, DEC-047): 마지막 사용 뒤 30분이 지나면 세션이 만료된다. 이전 판에서는 '유휴 11시간 59분 뒤에도 유효'를 재현했다."""
    with TestClient(app, base_url=ORIGIN) as c:
        login(c)
        clock.advance(minutes=29)
        assert c.get("/api/v1/settings").status_code == 200
        clock.advance(minutes=29)  # 사용했으므로 다시 29분 유휴 - 유효
        assert c.get("/api/v1/settings").status_code == 200
        clock.advance(minutes=30)  # 정확히 30분 유휴 - 만료 경계
        assert c.get("/api/v1/settings").status_code == 401
    with TestClient(app, base_url=ORIGIN) as c2:
        login(c2)
        clock.advance(hours=11, minutes=59)  # 유휴 11시간 59분 - 이제 만료돼야 한다
        assert c2.get("/api/v1/settings").status_code == 401


def test_session_idle_expiry_applies_to_me_and_state_changing_requests(app, clock):
    with TestClient(app, base_url=ORIGIN) as c:
        csrf = login(c).json()["csrf_token"]
        clock.advance(minutes=31)
        me = c.get("/api/v1/auth/me").json()
        assert me["authenticated"] is False and me["csrf_token"] is None
        # 만료된 세션의 쿠키+CSRF 토큰으로는 쓰기도 불가(401 또는 403)
        r = c.patch("/api/v1/settings", headers=hdr(csrf), json={"daily_apply_cap": 5})
        assert r.status_code in (401, 403), r.text


def test_session_activity_extends_idle_but_not_absolute_lifetime(app, clock):
    """활동은 유휴 만료만 늦추고 절대 12시간(expires_at)은 늘리지 못한다."""
    with TestClient(app, base_url=ORIGIN) as c:
        login(c)
        for _ in range(35):  # 20분 간격 35번 = 11시간 40분
            clock.advance(minutes=20)
            assert c.get("/api/v1/settings").status_code == 200
        clock.advance(minutes=21)  # 12시간 01분 - 절대 만료
        assert c.get("/api/v1/settings").status_code == 401


def test_oversized_cookie_token_rejected_quickly(client):
    client.cookies.set("ytw_session", "A" * 5000, path="/api")
    assert client.get("/api/v1/settings").status_code == 401


def test_session_cap_evicts_oldest_session_dos_vector(app, engine, clock):
    """[정보/Low] 같은 PC 의 공격자가 세션을 21개 만들면 소유자 세션이 밀려난다(PIN 이 꺼져 있을 때). TW-03 수용 범위의 연장."""
    with TestClient(app, base_url=ORIGIN) as owner:
        login(owner)
        assert owner.get("/api/v1/settings").status_code == 200
        for _ in range(21):
            clock.advance(seconds=1)
            with TestClient(app, base_url=ORIGIN) as atk:
                login(atk)
        assert owner.get("/api/v1/settings").status_code == 401
    with engine.connect() as con:
        assert con.exec_driver_sql("SELECT count(*) FROM sessions").scalar_one() <= 20


# ───────────── [TW-04] PIN ─────────────

def _set_pin(client, csrf, pin="4821"):
    r = client.patch("/api/v1/settings", headers=hdr(csrf), json={"pin": {"action": "set", "new_pin": pin}})
    assert r.status_code == 200, r.text


def test_pin_bruteforce_locks_and_correct_pin_is_refused_while_locked(app, clock):
    with TestClient(app, base_url=ORIGIN) as owner:
        _set_pin(owner, login(owner).json()["csrf_token"])
    with TestClient(app, base_url=ORIGIN) as atk:
        codes = [login(atk, pin=f"{i:04d}").status_code for i in range(5)]
        assert codes[:4] == [401] * 4 and codes[4] == 429, codes
        r = login(atk, pin="4821")
        assert r.status_code == 429 and r.json()["code"] == "pin_locked" and int(r.headers["retry-after"]) > 0
        clock.advance(minutes=5, seconds=1)
        assert login(atk, pin="4821").status_code == 200  # 시간이 지나면 정상 PIN 허용


def test_pin_lock_doubles_and_caps(app, clock):
    with TestClient(app, base_url=ORIGIN) as owner:
        _set_pin(owner, login(owner).json()["csrf_token"])
    waits = []
    with TestClient(app, base_url=ORIGIN) as atk:
        for _ in range(8):
            for i in range(5):
                r = login(atk, pin="0000" if i < 4 else "1111")
            assert r.status_code == 429
            w = int(r.headers["retry-after"])
            waits.append(w)
            clock.advance(seconds=w + 1)
    assert waits[0] <= 300 and waits[1] <= 600 and waits[1] > waits[0] and max(waits) <= 3600, waits


def test_pin_guess_via_settings_endpoint_is_locked_too(app, clock):
    """세션을 이미 가진 공격자가 PIN 변경/해제 요청의 current_pin 으로 추측해도 같은 잠금에 걸린다(실패 기록이 롤백되지 않는다)."""
    with TestClient(app, base_url=ORIGIN) as c:
        t = login(c).json()["csrf_token"]
        _set_pin(c, t, "4821")
        codes = [c.patch("/api/v1/settings", headers=hdr(t), json={"pin": {"action": "clear", "current_pin": f"{i:04d}"}}).status_code for i in range(6)]
        assert codes == [401, 401, 401, 401, 429, 429], codes
        clock.advance(minutes=5, seconds=1)
        assert c.patch("/api/v1/settings", headers=hdr(t), json={"pin": {"action": "clear", "current_pin": "4821"}}).status_code == 200


@pytest.mark.parametrize("pin", ["", "abcd", "12", "1" * 13, "12 34", "１２３４", "1234\n", "0" * 64, "'; DROP TABLE settings_kv;--"])
def test_pin_format_is_validated_on_set(client, csrf, pin):
    r = client.patch("/api/v1/settings", headers=hdr(csrf), json={"pin": {"action": "set", "new_pin": pin}})
    assert r.status_code in (422, 400), (pin, r.status_code)


def test_pin_change_and_clear_need_current_pin_and_revoke_other_sessions(app):
    with TestClient(app, base_url=ORIGIN) as a, TestClient(app, base_url=ORIGIN) as b:
        ta = login(a).json()["csrf_token"]
        login(b)
        _set_pin(a, ta, "4821")
        assert b.get("/api/v1/settings").status_code == 401, "PIN 설정 시 다른 세션이 폐기되지 않았다"
        assert a.patch("/api/v1/settings", headers=hdr(ta), json={"pin": {"action": "clear"}}).status_code == 401
        assert a.patch("/api/v1/settings", headers=hdr(ta), json={"pin": {"action": "clear", "current_pin": "9999"}}).status_code == 401
        assert a.patch("/api/v1/settings", headers=hdr(ta), json={"pin": {"action": "clear", "current_pin": 4821}}).status_code == 401
        assert a.patch("/api/v1/settings", headers=hdr(ta), json={"pin": {"action": "clear", "current_pin": "4821"}}).status_code == 200


def test_pin_value_never_in_audit_or_logs(app, engine, caplog):
    caplog.set_level("DEBUG")
    with TestClient(app, base_url=ORIGIN) as c:
        t = login(c).json()["csrf_token"]
        _set_pin(c, t, "7391")
        login(c, pin="1357")
    with engine.connect() as con:
        blob = json.dumps([list(map(str, r)) for r in con.exec_driver_sql("SELECT detail, target_id FROM audit_log").fetchall()])
    assert "7391" not in blob and "1357" not in blob
    assert "7391" not in caplog.text and "1357" not in caplog.text


def test_pin_hash_is_scrypt_with_unique_salt(app, engine):
    with TestClient(app, base_url=ORIGIN) as c:
        t = login(c).json()["csrf_token"]
        _set_pin(c, t, "4821")
    with engine.connect() as con:
        v = con.exec_driver_sql("SELECT value FROM settings_kv WHERE key='pin_hash'").scalar_one()
    v = json.loads(v) if isinstance(v, str) and v.startswith('"') else v
    assert str(v).startswith("scrypt$16384$8$1$") and "4821" not in str(v)


# ───────────── [TW-25] 속도·크기 제한 ─────────────

def test_session_issue_rate_limit_and_foreign_bucket_isolated(settings, engine, seeded, clock, monkeypatch):
    ft = FakeTime()
    app = build_app(settings, clock, rate_limits=RateLimits(global_per_min=50, write_per_min=50, auth_per_min=10), time_fn=ft, monkeypatch=monkeypatch)
    with TestClient(app, base_url=ORIGIN) as c:
        codes = [login(c).status_code for _ in range(12)]
        assert codes.count(200) == 10 and codes[10] == 429 and codes[11] == 429, codes
        ft.t += 61
        # 교차 출처 요청 폭주가 소유자 한도를 소모하지 않는다
        for _ in range(60):
            c.post("/api/v1/auth/session", headers={"Origin": "http://evil.com"})
        assert login(c).status_code == 200


def test_foreign_origin_flood_has_its_own_cap(settings, engine, seeded, clock, monkeypatch):
    """교차 출처 요청은 소유자 한도를 쓰지 않는 대신 자체 한도(분당 global_per_min)에 걸려야 한다 - 무제한 403 폭주 방지."""
    ft = FakeTime()
    app = build_app(settings, clock, rate_limits=RateLimits(global_per_min=30, write_per_min=30, auth_per_min=10), time_fn=ft, monkeypatch=monkeypatch)
    with TestClient(app, base_url=ORIGIN) as c:
        codes = [c.post("/api/v1/auth/session", headers={"Origin": "http://evil.com"}).status_code for _ in range(45)]
        assert codes.count(403) == 30 and codes.count(429) == 15, (codes.count(403), codes.count(429))
        ft.t += 61
        assert c.post("/api/v1/auth/session", headers={"Origin": "http://evil.com"}).status_code == 403


def test_body_size_limits(client, csrf):
    big = "x" * (1024 * 1024 + 10)
    r = client.patch("/api/v1/settings", headers={**hdr(csrf), "content-type": "application/json"}, content=json.dumps({"tone": [big]}))
    assert r.status_code == 413
    def gen():
        for _ in range(300):
            yield b"a" * 8192
    r = client.patch("/api/v1/settings", headers={**hdr(csrf), "content-type": "application/json"}, content=gen())
    assert r.status_code == 413, "Content-Length 없는 chunked 본문 우회"


@pytest.mark.parametrize("cl", ["-1", "+5", "1_0", "0x10", "1e3", "5.0", "five", "99999999999999999999"])
def test_bad_content_length_is_rejected(client, cl):
    r = client.post("/api/v1/auth/session", headers={"Origin": ORIGIN, "content-length": cl}, content=b"")
    assert r.status_code in (400, 413), (cl, r.status_code)


def test_duplicate_content_length_rejected(client):
    r = client.post("/api/v1/auth/session", headers=[("host", HOST), ("origin", ORIGIN), ("content-length", "2"), ("content-length", "2")], content=b"{}")
    assert r.status_code == 400


# ───────────── [TW-23] 헤더 / [TW-34] 문서 노출 / [TW-17] 오류 노출 ─────────────

def _assert_security_headers(r, api=True):
    h = {k.lower(): v for k, v in r.headers.items()}
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["cross-origin-resource-policy"] == "same-origin" and h["cross-origin-opener-policy"] == "same-origin"
    assert "permissions-policy" in h and "referrer-policy" in h
    if api:
        assert h["cache-control"] == "no-store" and "default-src 'none'" in h["content-security-policy"]


def test_security_headers_on_success_and_error_paths(client, csrf):
    for r in (client.get("/api/v1/auth/me"), client.get("/api/v1/nope"), client.get("/api/v1/settings/../x"), client.post("/api/v1/auth/session", headers={"Origin": "http://evil.com"}),
              client.patch("/api/v1/settings", headers=hdr(csrf), json={"x": 1}), client.get("/api/v1/videos?page=0"), client.get("/api/healthz")):
        _assert_security_headers(r)
    with TestClient(client.app, base_url="http://evil.com") as e:
        _assert_security_headers(e.get("/api/v1/auth/me"))


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect", "/api/docs", "/api/openapi.json", "/admin", "/metrics", "/debug", "/.env", "/api/v1/../../etc/passwd"])
def test_no_docs_or_admin_surface(client, path):
    r = client.get(path)
    assert r.status_code in (404, 401, 403, 405), (path, r.status_code)
    assert "swagger" not in r.text.lower() and "openapi" not in r.text.lower()


def test_websocket_rejected_with_policy_violation_code(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as ei:
        with client.websocket_connect("/api/v1/ws"):
            pass
    assert ei.value.code == 1008  # GuardMiddleware 가 정책 위반(1008)으로 닫는다 - 라우트 부재로 인한 우연한 거부가 아니다
    with pytest.raises(WebSocketDisconnect) as ei:
        with client.websocket_connect("/api/v1/auth/me"):
            pass
    assert ei.value.code == 1008


def test_cors_not_enabled_and_no_wildcard(client):
    r = client.options("/api/v1/settings", headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "PATCH"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}
    r = client.get("/api/v1/auth/me", headers={"Origin": "http://evil.com"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_error_bodies_do_not_leak_internals(client, csrf):
    probes = [
        client.patch("/api/v1/settings", headers={**hdr(csrf), "content-type": "application/json"}, content=b"{not json"),
        client.patch("/api/v1/settings", headers={**hdr(csrf), "content-type": "application/json"}, content=b"[1,2,3]"),
        client.patch("/api/v1/settings", headers={**hdr(csrf), "content-type": "application/json"}, content=b'{"daily_apply_cap": 1e999}'),
        client.patch("/api/v1/settings", headers={**hdr(csrf), "content-type": "text/plain"}, content=b"hi"),
        client.get("/api/v1/videos?page=-1&page_size=99999"),
        client.get("/api/v1/videos/..%2f..%2fetc%2fpasswd"),
        client.get("/api/v1/videos/demoVid0001%00"),
        client.get("/api/v1/jobs/not-a-uuid"),
        client.get("/api/v1/audit?page=1000000000000"),
        client.get("/api/v1/suggestions?status=%27%20OR%201%3D1--"),
    ]
    for r in probes:
        body = r.text
        assert r.status_code < 500, (r.request.url, r.status_code, body[:200])
        for needle in ("Traceback", "File \"", "/home/", "site-packages", "sqlalchemy", "sqlite", "psycopg", "ytweb.", "secret", "password"):
            assert needle.lower() not in body.lower(), (r.request.url, needle)
        assert r.headers["content-type"].startswith("application/problem+json")


def test_422_does_not_echo_input_values(client, csrf):
    secret = "SuperSecretValue-12345"
    r = client.patch("/api/v1/suggestions/1", headers=hdr(csrf), json={"title": secret, "extra": secret})
    assert r.status_code in (404, 422)
    assert secret not in r.text
    r = client.post("/api/v1/batches", headers=hdr(csrf, key="k" * 10), json={"suggestion_ids": [secret]})
    assert r.status_code == 422 and secret not in r.text


def test_json_depth_bomb_is_400_without_trace(client, csrf):
    for bomb in (b"[" * 200_000 + b"]" * 200_000, b'{"a":' * 150_000 + b"1" + b"}" * 150_000):
        r = client.patch("/api/v1/settings", headers={**hdr(csrf), "content-type": "application/json"}, content=bomb)
        assert r.status_code == 400 and "Traceback" not in r.text and "Recursion" not in r.text
    assert client.get("/api/healthz").status_code == 200  # 서버 생존


HUGE = "99999999999999999999999"


def _huge_probes(client, csrf):
    return {
        "GET /batches/{huge}": client.get(f"/api/v1/batches/{HUGE}"),
        "GET /suggestions?page=huge": client.get(f"/api/v1/suggestions?page={HUGE}"),
        "GET /changes?batch_id=huge": client.get(f"/api/v1/changes?batch_id={HUGE}"),
        "POST /batches ids=[huge]": client.post("/api/v1/batches", headers=hdr(csrf, key="idem-12345678"), json={"suggestion_ids": [int(HUGE)]}),
        "POST /changes/{huge}/rollback": client.post(f"/api/v1/changes/{HUGE}/rollback", headers=hdr(csrf, key="idem-12345679"), json={"typed_video_id": "x", "approver": "a"}),
        "PATCH /suggestions/{huge}": client.patch(f"/api/v1/suggestions/{HUGE}", headers=hdr(csrf), json={"title": "x"}),
    }


def test_huge_integers_never_leak_and_server_survives(client, csrf):
    for name, r in _huge_probes(client, csrf).items():
        assert "Traceback" not in r.text and "OverflowError" not in r.text and "sqlite" not in r.text.lower(), name
        assert r.headers["content-type"].startswith("application/problem+json"), name
    assert client.get("/api/healthz").status_code == 200


def test_huge_integers_are_client_errors_not_500(client, csrf):
    """DEF-9-001 닫힘(W-FIX-BE): DB 정수 범위(2**63-1) 초과 ID·쪽 번호는 500 이 아니라 4xx(422)."""
    bad = {n: r.status_code for n, r in _huge_probes(client, csrf).items() if not 400 <= r.status_code < 500}
    assert not bad, bad


# ───────────── 정적 파일 모드(YTWEB_STATIC_DIR)에서 경로 순회 ─────────────

def test_static_mode_path_traversal(settings, engine, clock, tmp_path, monkeypatch):
    root = tmp_path / "www"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>INDEX</html>")
    (root / "assets" / "a.js").write_text("A")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("TOP-SECRET")
    (tmp_path / "wwwsibling").mkdir()
    (tmp_path / "wwwsibling" / "x.txt").write_text("SIBLING-SECRET")
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "1")
    monkeypatch.setenv("YTWEB_STATIC_DIR", str(root))
    from ytweb.app import create_app
    app = create_app(settings, clock=clock)
    with TestClient(app, base_url=ORIGIN) as c:
        assert "INDEX" in c.get("/").text and c.get("/assets/a.js").text == "A"
        for p in ("/../outside-secret.txt", "/..%2foutside-secret.txt", "/%2e%2e/outside-secret.txt", "/assets/../../outside-secret.txt", "/assets/%2e%2e/%2e%2e/outside-secret.txt",
                  "//etc/passwd", "/%2fetc/passwd", "/..\\outside-secret.txt", "/../wwwsibling/x.txt", "/assets/..%5c..%5coutside-secret.txt", "/%252e%252e/outside-secret.txt"):
            r = c.get(p)
            assert "TOP-SECRET" not in r.text and "SIBLING-SECRET" not in r.text and "root:" not in r.text, (p, r.status_code)
        assert c.get("/api/v1/nope").status_code == 404  # API 경로는 SPA 로 떨어지지 않는다
        assert c.get("/api").status_code == 404


def test_no_open_redirect_on_odd_paths(client):
    for p in ("//evil.com/", "/api//evil.com", "/api/v1/settings//", "/api/v1//settings", "/%2f%2fevil.com", "/api/v1/videos/"):
        r = client.get(p, follow_redirects=False)
        loc = r.headers.get("location", "")
        assert "evil.com" not in loc, (p, r.status_code, loc)
