"""독립 점검 2: 쿠키 속성 · 세션(고정·만료·상한) · CSRF · PIN 잠금 (S-W02, S-W03, S-W04, S-W08, S-W16)."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from ytweb.core import pin as pin_mod
from ytweb.db.models import SettingKV

from tests.verify_wa.helpers import (
    ORIGIN,
    SECRET_PIN,
    asgi_call,
    body_json,
    hdr,
    login,
    parse_set_cookie,
    set_cookie_values,
)

ME = "/api/v1/auth/me"
URLSAFE = re.compile(r"^[A-Za-z0-9_-]+$")


def _cookie(client) -> str:
    return client.cookies.get("ytw_session")


def _me_with_cookie(app, token: str | None):
    h = [("host", "127.0.0.1:8080")]
    if token:
        h.append(("cookie", f"ytw_session={token}"))
    return body_json(asgi_call(app, "GET", ME, h))


def _set_pin(client, csrf, pin=SECRET_PIN):
    r = client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": pin}}, headers=hdr(csrf))
    assert r.status_code == 200, r.text
    return r


# ---------------------------------------------------------------- 쿠키 속성

def test_cookie_attributes_exact(client, web_settings):
    """TC-VA-029 [S-W04] Set-Cookie: HttpOnly, SameSite=Strict, Path=/api, Max-Age=TTL초, Domain 없음, Expires 없음(Max-Age 우선), 이름 ytw_session."""
    r = client.post("/api/v1/auth/session", headers={"Origin": ORIGIN})
    raws = set_cookie_values(r)
    assert len(raws) == 1
    name, value, attrs = parse_set_cookie(raws[0])
    assert name == "ytw_session" and len(value) >= 43
    assert "httponly" in attrs
    assert attrs["samesite"].lower() == "strict"
    assert attrs["path"] == "/api"
    assert int(attrs["max-age"]) == web_settings.session_ttl_hours * 3600
    assert "domain" not in attrs
    assert "secure" not in attrs  # 알려진 설계(Q-WA-1): http://127.0.0.1 이라 Secure 미사용. 바뀌면 이 케이스가 알려 준다.
    assert value not in r.text  # 토큰 원문은 본문에 없다(쿠키로만)


def test_logout_cookie_deletion_attributes_and_server_side_invalidation(client, app):
    """TC-VA-030 [S-W04] 로그아웃은 같은 Path 로 Max-Age=0 삭제 쿠키를 내리고, 서버에서도 토큰이 즉시 무효가 된다."""
    csrf = login(client)
    token = _cookie(client)
    assert _me_with_cookie(app, token)["authenticated"] is True
    r = client.delete("/api/v1/auth/session", headers=hdr(csrf))
    assert r.status_code == 204
    name, value, attrs = parse_set_cookie(set_cookie_values(r)[0])
    assert name == "ytw_session" and value in ("", '""')
    assert attrs["path"] == "/api" and int(attrs["max-age"]) == 0 and "httponly" in attrs
    assert _me_with_cookie(app, token)["authenticated"] is False  # 훔친 쿠키를 다시 써도 무효


def test_session_token_entropy_and_uniqueness(client, engine, clock):
    """TC-VA-031 [S-W08] 세션 토큰/CSRF 토큰은 URL-safe 43자(256비트)이고 40회 발급해도 겹치지 않으며 서로 다르다."""
    tokens, csrfs = set(), set()
    for _ in range(40):
        clock.advance(seconds=1)
        c = login(client)
        t = _cookie(client)
        assert len(t) == 43 and URLSAFE.match(t) and len(c) == 43 and URLSAFE.match(c)
        assert t != c
        tokens.add(t)
        csrfs.add(c)
    assert len(tokens) == 40 and len(csrfs) == 40
    assert not (tokens & csrfs)
    # 문자 다양성(상수/카운터 같은 구현 방지): 40개 토큰 전체에서 40종 이상의 문자가 나온다.
    assert len(set("".join(tokens))) > 40


def test_db_stores_only_sha256_of_session_token(client, engine):
    """TC-VA-032 [S-W08] DB 의 sessions.id 는 sha256(토큰) 이고 sessions 테이블 어디에도 쿠키 토큰 원문이 없다."""
    login(client)
    token = _cookie(client)
    with engine.connect() as c:
        rows = c.execute(text("select * from sessions")).fetchall()
    assert len(rows) == 1
    dump = repr(rows[0])
    assert token not in dump
    assert rows[0][0] == hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- 세션 고정·만료·상한

def test_session_fixation_attacker_supplied_cookie_not_adopted(client, app, engine):
    """TC-VA-033 [S-W02] 세션 고정: 공격자가 심은 쿠키 값을 서버가 채택하지 않고 새 토큰을 발급하며, 심은 값은 인증되지 않는다."""
    planted = "A" * 43
    r = client.post("/api/v1/auth/session", headers={"Origin": ORIGIN, "Cookie": f"ytw_session={planted}"})
    assert r.status_code == 200
    new = parse_set_cookie(set_cookie_values(r)[0])[1]
    assert new != planted
    assert _me_with_cookie(app, planted)["authenticated"] is False
    with engine.connect() as c:
        ids = {x[0] for x in c.execute(text("select id from sessions"))}
    assert hashlib.sha256(planted.encode()).hexdigest() not in ids


@pytest.mark.parametrize("bad", ["", "x", "A" * 43, "A" * 129, "A" * 5000, "../../etc/passwd", "a b", "%00", "'; DROP TABLE sessions;--", "é" * 10])
def test_malformed_session_cookie_is_plain_unauthenticated(app, engine, bad):
    """TC-VA-034 [S-W02] 이상한 세션 쿠키(빈 값·초장문·SQL·경로 문자열)는 500 없이 단순히 미인증(401/authenticated=false) 처리."""
    try:
        cookie = f"ytw_session={bad}".encode("latin-1").decode("latin-1")
    except UnicodeEncodeError:  # latin-1 로 못 보내는 값은 HTTP 에도 못 실린다
        pytest.skip("HTTP 헤더에 실릴 수 없는 값")
    out = asgi_call(app, "GET", "/api/v1/settings", [("host", "127.0.0.1:8080"), ("cookie", cookie)])
    assert out["status"] == 401
    out = asgi_call(app, "GET", ME, [("host", "127.0.0.1:8080"), ("cookie", cookie)])
    assert out["status"] == 200 and body_json(out)["authenticated"] is False
    with engine.connect() as c:
        assert c.execute(text("select count(*) from sessions")).scalar_one() == 0


@pytest.mark.no_idle
def test_session_expiry_boundary_is_exclusive_absolute_and_row_deleted(client, app, clock, engine):
    """TC-VA-035 [S-W08] 만료 경계: 발급+TTL-1µs 까지 유효, 정확히 +TTL 에서 무효(행 삭제). 중간에 활동해도 만료 시각은 연장되지 않는다(절대 만료)."""
    login(client)
    token = _cookie(client)
    clock.advance(hours=11, minutes=59)
    assert _me_with_cookie(app, token)["authenticated"] is True  # 활동(last_seen 갱신)
    clock.advance(minutes=1)
    clock.now -= timedelta(microseconds=1)
    assert _me_with_cookie(app, token)["authenticated"] is True  # +12h-1µs
    clock.advance(microseconds=1)  # 정확히 +12h
    assert _me_with_cookie(app, token)["authenticated"] is False
    with engine.connect() as c:
        assert c.execute(text("select count(*) from sessions")).scalar_one() == 0


def test_expired_session_cannot_mutate(client, clock, engine):
    """TC-VA-036 [S-W03, S-W08] 만료된 세션 + 올바른 CSRF 로는 상태 변경이 401 이고 값이 바뀌지 않는다."""
    csrf = login(client)
    clock.advance(hours=12)
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 4}, headers=hdr(csrf))
    assert r.status_code == 401 and r.json()["code"] == "session_required"
    with engine.connect() as c:
        assert c.execute(select(text("count(*)")).select_from(SettingKV)).scalar_one() == 0


def test_active_session_cap_is_20_and_oldest_evicted(client, app, clock, engine):
    """TC-VA-037 [S-W08] 세션은 최대 20개: 25번 발급하면 20개만 남고 가장 오래된 5개 토큰은 무효, 최신 20개는 유효."""
    tokens = []
    for _ in range(25):
        clock.advance(seconds=1)
        login(client)
        tokens.append(_cookie(client))
    with engine.connect() as c:
        assert c.execute(text("select count(*) from sessions")).scalar_one() == 20
    assert [_me_with_cookie(app, t)["authenticated"] for t in tokens] == [False] * 5 + [True] * 20


def test_new_login_does_not_invalidate_previous_session_characterization(client, app, clock):
    """TC-VA-038 [S-W08] (특성화) 재로그인은 이전 세션을 회전/폐기하지 않는다(복수 세션 허용). 로그아웃은 그 세션만 폐기한다."""
    login(client)
    t1 = _cookie(client)
    clock.advance(seconds=1)
    csrf2 = login(client)
    t2 = _cookie(client)
    assert t1 != t2
    assert _me_with_cookie(app, t1)["authenticated"] and _me_with_cookie(app, t2)["authenticated"]
    client.delete("/api/v1/auth/session", headers=hdr(csrf2))
    assert _me_with_cookie(app, t1)["authenticated"] is True and _me_with_cookie(app, t2)["authenticated"] is False


# ---------------------------------------------------------------- CSRF

def test_csrf_rejected_variants_and_accepted_exact(client):
    """TC-VA-039 [S-W03] CSRF: 없음·빈 값·접두/접미 변형·대소문자 변경·공백·유니코드·세션 토큰·다른 세션의 토큰은 403 csrf_invalid, 정확한 값만 200."""
    csrf = login(client)
    session_token = _cookie(client)
    other = login(client)  # 같은 jar 에서 두 번째 세션(쿠키는 교체됨)
    # 두 번째 세션 쿠키로 첫 세션 CSRF 를 쓰면 거부
    variants = {
        "empty": "", "prefix": csrf[:-1], "suffix": csrf + "x", "upper": csrf.swapcase(), "space": " " + csrf,
        "trailing_space": csrf + " ", "session_token": session_token, "other_session_csrf": csrf,
        "zero": "0", "long": "A" * 4096,
    }
    for name, value in variants.items():
        if name == "other_session_csrf":
            r = client.patch("/api/v1/settings", json={"daily_apply_cap": 2}, headers={"Origin": ORIGIN, "X-CSRF-Token": value})
        else:
            r = client.patch("/api/v1/settings", json={"daily_apply_cap": 2}, headers={"Origin": ORIGIN, "X-CSRF-Token": value})
        assert r.status_code == 403 and r.json()["code"] == "csrf_invalid", (name, r.status_code, r.text)
    # latin-1 비ASCII 문자가 든 토큰(httpx 로는 못 보냄)은 ASGI 로 직접 보낸다: 500 이 아니라 403.
    out = asgi_call(client.app, "PATCH", "/api/v1/settings",
                    [("host", "127.0.0.1:8080"), ("origin", ORIGIN), ("content-type", "application/json"),
                     ("cookie", f"ytw_session={_cookie(client)}"), ("x-csrf-token", other[:-1] + "é")], [b'{"daily_apply_cap":2}'])
    assert out["status"] == 403 and body_json(out)["code"] == "csrf_invalid"
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 2}, headers=hdr(other))
    assert r.status_code == 200
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 2})  # 헤더 없음
    assert r.status_code == 403  # Origin 없음
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 2}, headers={"Origin": ORIGIN})
    assert r.status_code == 403 and r.json()["code"] == "csrf_invalid"


def test_csrf_token_is_per_session_and_stable_within_session(client):
    """TC-VA-040 [S-W03] CSRF 토큰은 세션별로 다르고, 같은 세션의 /me 가 같은 값을 돌려준다(로테이션으로 인한 정상 요청 실패 없음)."""
    c1 = login(client)
    assert client.get(ME).json()["csrf_token"] == c1
    assert client.get(ME).json()["csrf_token"] == c1
    c2 = login(client)
    assert c1 != c2 and client.get(ME).json()["csrf_token"] == c2


def test_csrf_error_does_not_disclose_expected_value(client):
    """TC-VA-041 [S-W03, S-W09] CSRF 거부 응답에 기대 토큰이나 세션 정보가 담기지 않는다."""
    csrf = login(client)
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 2}, headers={"Origin": ORIGIN, "X-CSRF-Token": "wrong-token-value"})
    assert csrf not in r.text and _cookie(client) not in r.text and "wrong-token-value" not in r.text


def test_unsafe_methods_all_require_csrf_and_session(client):
    """TC-VA-042 [S-W03] DELETE /auth/session, PATCH /settings 는 CSRF 없이는 403, 세션 없이는 401(상태 변경 불가)."""
    r = client.delete("/api/v1/auth/session", headers={"Origin": ORIGIN, "X-CSRF-Token": "x"})
    assert r.status_code == 401
    csrf = login(client)
    r = client.delete("/api/v1/auth/session", headers={"Origin": ORIGIN})
    assert r.status_code == 403
    assert client.get(ME).json()["authenticated"] is True  # 거부된 로그아웃은 세션을 건드리지 않음
    assert csrf


# ---------------------------------------------------------------- PIN

def test_pin_lockout_exact_boundary_4_ok_5th_locks_correct_pin_rejected_while_locked(client, clock):
    """TC-VA-043 [S-W08] PIN 잠금 경계: 틀림 1~4회는 401, 5회째가 429(잠금 300초). 잠금 중엔 올바른 PIN 도 429, 299초 후도 429, 300초 후에야 성공."""
    csrf = login(client)
    _set_pin(client, csrf)
    client.delete("/api/v1/auth/session", headers=hdr(csrf))
    codes = []
    for _ in range(5):
        codes.append(client.post("/api/v1/auth/session", json={"pin": "0000"}, headers={"Origin": ORIGIN}).status_code)
    assert codes == [401, 401, 401, 401, 429]
    r = client.post("/api/v1/auth/session", json={"pin": SECRET_PIN}, headers={"Origin": ORIGIN})
    assert r.status_code == 429 and r.json()["code"] == "pin_locked"
    assert 1 <= int(r.headers["retry-after"]) <= 300
    clock.advance(seconds=299)
    assert client.post("/api/v1/auth/session", json={"pin": SECRET_PIN}, headers={"Origin": ORIGIN}).status_code == 429
    clock.advance(seconds=1)
    assert client.post("/api/v1/auth/session", json={"pin": SECRET_PIN}, headers={"Origin": ORIGIN}).status_code == 200


def test_pin_success_resets_failure_counter(client, clock):
    """TC-VA-044 [S-W08] 4회 실패 뒤 성공하면 카운터가 0 으로 돌아가 다시 4회까지 실패해도 잠기지 않는다."""
    csrf = login(client)
    _set_pin(client, csrf)
    client.delete("/api/v1/auth/session", headers=hdr(csrf))
    o = {"Origin": ORIGIN}
    for _ in range(4):
        assert client.post("/api/v1/auth/session", json={"pin": "1111"}, headers=o).status_code == 401
    assert client.post("/api/v1/auth/session", json={"pin": SECRET_PIN}, headers=o).status_code == 200
    for _ in range(4):
        assert client.post("/api/v1/auth/session", json={"pin": "1111"}, headers=o).status_code == 401
    assert client.post("/api/v1/auth/session", json={"pin": "1111"}, headers=o).status_code == 429


def test_pin_lock_duration_doubles_up_to_one_hour_cap(client, clock):
    """TC-VA-045 [S-W08] 잠금 시간이 300→600→1200→2400→3600→3600초로 늘고 1시간에서 멈춘다(Retry-After 로 확인)."""
    csrf = login(client)
    _set_pin(client, csrf)
    client.delete("/api/v1/auth/session", headers=hdr(csrf))
    o = {"Origin": ORIGIN}
    seen = []
    for _ in range(6):
        for i in range(5):
            r = client.post("/api/v1/auth/session", json={"pin": "2222"}, headers=o)
        assert r.status_code == 429
        wait = int(r.headers["retry-after"])
        seen.append(wait)
        clock.advance(seconds=wait)
    assert seen == [300, 600, 1200, 2400, 3600, 3600]


def test_pin_lock_survives_app_restart(web_settings, engine, clock, fake_time, client, monkeypatch):
    """TC-VA-046 [S-W08] 잠금 상태는 DB 에 있어 프로세스를 새로 띄워도 유지된다(재시작으로 우회 불가)."""
    from fastapi.testclient import TestClient
    from ytweb.app import create_app
    from ytweb.core.ratelimit import RateLimits

    from tests.conftest import CORE_ROUTERS
    csrf = login(client)
    _set_pin(client, csrf)
    client.delete("/api/v1/auth/session", headers=hdr(csrf))
    for _ in range(5):
        client.post("/api/v1/auth/session", json={"pin": "0000"}, headers={"Origin": ORIGIN})
    app2 = create_app(web_settings, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time,
                      rate_limits=RateLimits(global_per_min=10_000, write_per_min=10_000, auth_per_min=10_000))
    with TestClient(app2, base_url=ORIGIN) as c2:
        r = c2.post("/api/v1/auth/session", json={"pin": SECRET_PIN}, headers={"Origin": ORIGIN})
        assert r.status_code == 429


def test_pin_lock_shared_with_settings_pin_change_path(client, clock):
    """TC-VA-047 [S-W08] PIN 변경 경로(PATCH /settings pin)의 current_pin 오류도 같은 잠금 카운터를 소모해 5회에 잠기고, 잠기면 세션 발급도 막힌다."""
    csrf = login(client)
    _set_pin(client, csrf)
    codes = []
    for _ in range(5):
        r = client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "7777", "current_pin": "0000"}}, headers=hdr(csrf))
        codes.append(r.status_code)
    assert codes == [401, 401, 401, 401, 429]
    assert client.post("/api/v1/auth/session", json={"pin": SECRET_PIN}, headers={"Origin": ORIGIN}).status_code == 429


def test_pin_wrong_type_or_missing_counts_as_failure(client):
    """TC-VA-048 [S-W08] PIN 이 필요한데 본문 없음/null/빈 문자열이면 401 로 실패 처리(우회 불가)되고 세션 쿠키가 내려가지 않는다."""
    csrf = login(client)
    _set_pin(client, csrf)
    client.delete("/api/v1/auth/session", headers=hdr(csrf))
    client.cookies.clear()
    o = {"Origin": ORIGIN}
    for body in (None, {}, {"pin": None}, {"pin": ""}):
        r = client.post("/api/v1/auth/session", json=body, headers=o) if body is not None else client.post("/api/v1/auth/session", headers=o)
        assert r.status_code == 401, (body, r.status_code)
        assert not set_cookie_values(r)
    r = client.post("/api/v1/auth/session", json={"pin": 135792468}, headers=o)
    assert r.status_code == 422 and not set_cookie_values(r)


@pytest.mark.parametrize("pin,ok", [("1234", True), ("123", False), ("123456789012", True), ("1234567890123", False),
                                    ("0001", True), ("12a4", False), ("١٢٣٤", False), ("12 34", False), ("", False),
                                    ("-123", False), ("1.23", False), ("+1234", False)])
def test_pin_format_boundaries(client, pin, ok):
    """TC-VA-049 [S-W08] PIN 형식 경계: ASCII 숫자 4~12자리만 허용(3/13자리, 문자, 유니코드 숫자, 공백, 부호는 422)."""
    csrf = login(client)
    r = client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": pin}}, headers=hdr(csrf))
    assert (r.status_code == 200) is ok, (pin, r.status_code, r.text)
    if not ok:
        assert r.status_code == 422 and client.get("/api/v1/settings").json()["pin_enabled"] is False


@pytest.mark.parametrize("pin", ["1234\n", "123456789012\n"])
def test_pin_trailing_newline_rejected(client, pin):
    """TC-VA-050 [S-W08] 끝에 줄바꿈이 붙은 PIN 은 형식 위반으로 422 여야 한다."""
    csrf = login(client)
    r = client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": pin}}, headers=hdr(csrf))
    assert r.status_code == 422


def test_pin_hash_scheme_salt_and_params(client, engine):
    """TC-VA-051 [S-W08] PIN 은 scrypt(N>=2^14,r=8,p=1)+16바이트 무작위 솔트로 저장되고 같은 PIN 도 해시가 매번 다르며 평문이 DB 에 없다."""
    h1, h2 = pin_mod.hash_pin("2468"), pin_mod.hash_pin("2468")
    assert h1 != h2
    scheme, n, r_, p, salt, digest = h1.split("$")
    assert scheme == "scrypt" and int(n) >= 2**14 and int(r_) == 8 and int(p) == 1
    assert len(base64.b64decode(salt)) == 16 and len(base64.b64decode(digest)) == 32
    csrf = login(client)
    _set_pin(client, csrf, "9753")
    with engine.connect() as c:
        stored = json.loads(c.execute(text("select value from settings_kv where key='pin_hash'")).scalar_one())
        keys = [k for (k,) in c.execute(text("select key from settings_kv"))]
    assert isinstance(stored, str) and stored.startswith("scrypt$16384$8$1$") and stored != "9753"
    assert pin_mod.verify_pin_hash("9753", stored) and not pin_mod.verify_pin_hash("9754", stored)
    assert "pin" not in keys  # 평문 PIN 용 키가 따로 없다


@pytest.mark.parametrize("stored", ["", "scrypt", "scrypt$a$b$c$d$e", "md5$16384$8$1$AAAA$AAAA", "scrypt$0$8$1$AAAA$AAAA",
                                    "scrypt$16384$8$1$!!!$!!!", "scrypt$16384$8$1$AAAA$AAAA$extra"])
def test_verify_pin_hash_tolerates_corrupt_storage(stored):
    """TC-VA-052 [S-W08] 저장된 해시가 손상돼도 예외 없이 False(로그인 500 방지)."""
    assert pin_mod.verify_pin_hash("1234", stored) is False


def test_pin_change_and_clear_revoke_other_sessions_but_keep_current(client, app, clock):
    """TC-VA-053 [S-W08] PIN 설정/변경/해제 시 현재 세션 외 모든 세션이 폐기되고 현재 세션은 유지된다."""
    login(client)
    other_token = _cookie(client)
    clock.advance(seconds=1)
    csrf = login(client)
    cur_token = _cookie(client)
    assert _me_with_cookie(app, other_token)["authenticated"] is True
    _set_pin(client, csrf)
    assert _me_with_cookie(app, other_token)["authenticated"] is False
    assert _me_with_cookie(app, cur_token)["authenticated"] is True
    clock.advance(seconds=1)
    client.delete("/api/v1/auth/session", headers=hdr(csrf))
    t3 = login(client, SECRET_PIN) and _cookie(client)
    clock.advance(seconds=1)
    csrf4 = login(client, SECRET_PIN)
    cur4 = _cookie(client)
    r = client.patch("/api/v1/settings", json={"pin": {"action": "clear", "current_pin": SECRET_PIN}}, headers=hdr(csrf4))
    assert r.status_code == 200 and r.json()["pin_enabled"] is False
    assert _me_with_cookie(app, t3)["authenticated"] is False and _me_with_cookie(app, cur4)["authenticated"] is True


def test_clear_pin_requires_current_pin_when_set(client):
    """TC-VA-054 [S-W08] PIN 해제는 현재 PIN 이 맞아야 하며(없거나 틀리면 401), 설정이 없을 때 해제는 409."""
    csrf = login(client)
    assert client.patch("/api/v1/settings", json={"pin": {"action": "clear"}}, headers=hdr(csrf)).status_code == 409
    _set_pin(client, csrf)
    assert client.patch("/api/v1/settings", json={"pin": {"action": "clear"}}, headers=hdr(csrf)).status_code == 401
    assert client.patch("/api/v1/settings", json={"pin": {"action": "clear", "current_pin": "0000"}}, headers=hdr(csrf)).status_code == 401
    assert client.get("/api/v1/settings").json()["pin_enabled"] is True


def test_pin_never_in_audit_rows_or_responses(client, engine):
    """TC-VA-055 [S-W08, S-W16] PIN 값/해시/쿠키/CSRF 토큰이 감사 로그 행과 설정 응답 어디에도 없다. 실패·잠금·성공이 감사에 남는다."""
    csrf = login(client)
    tok = _cookie(client)
    r = _set_pin(client, csrf)
    client.delete("/api/v1/auth/session", headers=hdr(csrf))
    for _ in range(5):
        client.post("/api/v1/auth/session", json={"pin": "00009999"}, headers={"Origin": ORIGIN})
    with engine.connect() as c:
        rows = c.execute(text("select action, detail, target_id from audit_log order by id")).fetchall()
        kv = json.loads(c.execute(text("select value from settings_kv where key='pin_hash'")).scalar_one())
    blob = repr(rows) + r.text
    for secret in (SECRET_PIN, "00009999", tok, csrf, str(kv)):
        assert secret not in blob
    actions = [x[0] for x in rows]
    assert actions.count("session.denied") == 5 and "settings.update" in actions and "session.delete" in actions
