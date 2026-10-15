"""출처 검증 · 쿠키 세션 · CSRF · PIN."""
from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select

from tests.conftest import ORIGIN, hdr, login
from ytweb.core.pin import hash_pin, verify_pin_hash
from ytweb.db.models import AuditLog, SessionRow, SettingKV


def _set_pin(client, csrf, pin="1234", current=None):
    body = {"pin": {"action": "set", "new_pin": pin}}
    if current:
        body["pin"]["current_pin"] = current
    return client.patch("/api/v1/settings", json=body, headers=hdr(csrf))


def test_me_unauthenticated(client):
    """TC-WA-024 세션이 없으면 authenticated=false, csrf_token=null, pin_required=false. (DEC-055: 로그인 관련 필드 3개 추가 — 로그인 모드가 아니면 login_required=false)"""
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json() == {"authenticated": False, "pin_required": False, "csrf_token": None,
                        "login_required": False, "setup_required": False, "admin_login_id": None, "idle_timeout_seconds": 1800}


def test_session_cookie_attributes(client, web_settings):
    """TC-WA-025 쿠키: 이름 ytw_session, HttpOnly, SameSite=Strict, Path=/api, Max-Age=TTL, Secure 없음, __Host- 접두사 없음."""
    r = client.post("/api/v1/auth/session", headers={"Origin": ORIGIN})
    assert r.status_code == 200
    sc = r.headers["set-cookie"]
    assert sc.startswith("ytw_session=")
    low = sc.lower()
    assert "httponly" in low
    assert "samesite=strict" in low
    assert "path=/api" in low
    assert f"max-age={web_settings.session_ttl_hours * 3600}" in low
    assert "secure" not in low
    assert "__host-" not in low


def test_session_token_stored_only_as_sha256(client, db):
    """TC-WA-026 DB 에는 토큰 원문이 없고 sha256 만 있다. 응답 본문에도 쿠키 토큰이 없다."""
    r = client.post("/api/v1/auth/session", headers={"Origin": ORIGIN})
    token = client.cookies.get("ytw_session")
    assert token and token not in r.text
    row = db.execute(select(SessionRow)).scalar_one()
    assert row.id == hashlib.sha256(token.encode()).hexdigest()
    assert token not in (row.id, row.csrf_token)
    assert row.csrf_token == r.json()["csrf_token"]


def test_me_authenticated_returns_csrf(client, csrf):
    """TC-WA-027 세션이 있으면 me 가 같은 csrf_token 을 돌려준다."""
    j = client.get("/api/v1/auth/me").json()
    assert j["authenticated"] is True and j["csrf_token"] == csrf


def test_session_issue_requires_origin(client):
    """TC-WA-028 Origin 없이 세션을 발급하면 403 origin_not_allowed."""
    r = client.post("/api/v1/auth/session")
    assert r.status_code == 403 and r.json()["code"] == "origin_not_allowed"
    assert "set-cookie" not in r.headers


@pytest.mark.parametrize("origin", ["http://evil.example", "http://127.0.0.1:9999", "https://127.0.0.1:8080", "null", "http://127.0.0.1:8080.evil.com"])
def test_foreign_origin_rejected(client, origin):
    """TC-WA-029 허용 출처가 아닌 Origin 은 거부."""
    r = client.post("/api/v1/auth/session", headers={"Origin": origin})
    assert r.status_code == 403 and r.json()["code"] == "origin_not_allowed"


def test_allowed_alternative_origin_localhost(client):
    """TC-WA-030 http://localhost:8080 도 허용 출처."""
    assert client.post("/api/v1/auth/session", headers={"Origin": "http://localhost:8080"}).status_code == 200


@pytest.mark.parametrize("site", ["cross-site", "same-site", "none"])
def test_sec_fetch_site_not_same_origin_rejected(client, site):
    """TC-WA-031 Sec-Fetch-Site 가 same-origin 이 아니면(same-site 포함) Origin 이 맞아도 거부."""
    r = client.post("/api/v1/auth/session", headers={"Origin": ORIGIN, "Sec-Fetch-Site": site})
    assert r.status_code == 403 and r.json()["code"] == "cross_site_request"


def test_sec_fetch_site_same_origin_passes(client):
    """TC-WA-032 Sec-Fetch-Site: same-origin + 허용 Origin 은 통과."""
    assert client.post("/api/v1/auth/session", headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_sec_fetch_site_header_absent_uses_origin(client):
    """TC-WA-033 Sec-Fetch-Site 가 없는 비브라우저 클라이언트는 Origin 일치만으로 통과, 불일치면 거부."""
    assert client.post("/api/v1/auth/session", headers={"Origin": ORIGIN}).status_code == 200
    assert client.post("/api/v1/auth/session", headers={"Origin": "http://evil.example"}).status_code == 403


def test_state_change_sec_fetch_site_enforced_after_login(client, csrf):
    """TC-WA-034 상태 변경(PATCH)에서도 same-site 요청은 CSRF 토큰이 맞아도 거부."""
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers={**hdr(csrf), "Sec-Fetch-Site": "same-site"})
    assert r.status_code == 403 and r.json()["code"] == "cross_site_request"


def test_csrf_missing_rejected(client, csrf):
    """TC-WA-035 X-CSRF-Token 누락은 403 csrf_invalid."""
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers={"Origin": ORIGIN})
    assert r.status_code == 403 and r.json()["code"] == "csrf_invalid"


def test_csrf_mismatch_rejected(client, csrf):
    """TC-WA-036 틀린 CSRF 토큰은 403 (같은 길이여도)."""
    wrong = ("A" if csrf[0] != "A" else "B") + csrf[1:]
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers=hdr(wrong))
    assert r.status_code == 403 and r.json()["code"] == "csrf_invalid"
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers=hdr("x"))
    assert r.status_code == 403


def test_csrf_match_accepted(client, csrf):
    """TC-WA-037 올바른 CSRF 토큰 + 허용 Origin 이면 200."""
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers=hdr(csrf))
    assert r.status_code == 200 and r.json()["daily_apply_cap"] == 5


def test_csrf_is_per_session(client, csrf):
    """TC-WA-038 CSRF 토큰은 세션마다 다르고, 이전 세션의 토큰은 새 세션에서 통하지 않는다."""
    second = login(client)
    assert second != csrf
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers=hdr(csrf))
    assert r.status_code == 403


def test_bad_origin_checked_before_session(client):
    """TC-WA-039 허용되지 않은 출처는 세션 유무와 무관하게 403(세션 존재 여부를 알려 주지 않음)."""
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "origin_not_allowed"


def test_state_change_without_session_401(client):
    """TC-WA-040 세션 없이 상태 변경하면 (출처가 맞아도) 401 session_required."""
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers={"Origin": ORIGIN, "X-CSRF-Token": "x"})
    assert r.status_code == 401 and r.json()["code"] == "session_required"


def test_read_without_session_401(client):
    """TC-WA-041 세션 없이 GET /settings, /audit 은 401."""
    assert client.get("/api/v1/settings").status_code == 401
    assert client.get("/api/v1/audit").status_code == 401


@pytest.mark.no_idle
def test_session_expires_after_ttl(client, csrf, clock):
    """TC-WA-042 TTL(12시간) 경과 후 요청은 401, me 는 authenticated=false."""
    clock.advance(hours=11, minutes=59)
    assert client.get("/api/v1/settings").status_code == 200
    clock.advance(minutes=2)
    r = client.get("/api/v1/settings")
    assert r.status_code == 401 and r.json()["code"] == "session_required"
    assert client.get("/api/v1/auth/me").json()["authenticated"] is False


def test_unknown_cookie_token_rejected(client):
    """TC-WA-043 위조 쿠키는 401."""
    client.cookies.set("ytw_session", "forged-token-value", path="/api")
    assert client.get("/api/v1/settings").status_code == 401
    client.cookies.set("ytw_session", "x" * 500, path="/api")
    assert client.get("/api/v1/settings").status_code == 401


def test_logout_deletes_session_and_cookie(client, csrf, db):
    """TC-WA-044 로그아웃은 204, 쿠키 삭제 지시, DB 세션 행 삭제, 이후 요청 401."""
    r = client.delete("/api/v1/auth/session", headers=hdr(csrf))
    assert r.status_code == 204
    sc = r.headers["set-cookie"].lower()
    assert "ytw_session=" in sc and ("max-age=0" in sc or "expires=" in sc) and "path=/api" in sc
    assert db.execute(select(func.count()).select_from(SessionRow)).scalar_one() == 0
    assert client.get("/api/v1/settings").status_code == 401


def test_logout_requires_csrf(client, csrf):
    """TC-WA-045 토큰 없는 로그아웃은 403 이고 세션은 유지된다."""
    assert client.delete("/api/v1/auth/session", headers={"Origin": ORIGIN}).status_code == 403
    assert client.get("/api/v1/settings").status_code == 200


def test_session_count_capped(client, db):
    """TC-WA-046 활성 세션 수는 20개로 제한된다(오래된 것부터 삭제)."""
    for _ in range(23):
        login(client)
    assert db.execute(select(func.count()).select_from(SessionRow)).scalar_one() == 20


def test_pin_hash_scrypt_with_salt():
    """TC-WA-047 PIN 은 scrypt+솔트로 저장: 같은 PIN 도 해시가 다르고 원문이 없으며 검증 가능."""
    a, b = hash_pin("123456"), hash_pin("123456")
    assert a != b and a.startswith("scrypt$") and "123456" not in a
    assert verify_pin_hash("123456", a) and not verify_pin_hash("123457", a)
    assert not verify_pin_hash("123456", "garbage") and not verify_pin_hash("1", "md5$1$2$3$4$5")


def test_pin_set_then_required_for_session(client, csrf, db):
    """TC-WA-048 PIN 설정 후 세션 발급은 PIN 이 필요하고, 정답이면 발급된다. DB 에 PIN 원문 없음."""
    assert _set_pin(client, csrf, "4321").status_code == 200
    stored = db.get(SettingKV, "pin_hash").value
    assert "4321" not in stored and stored.startswith("scrypt$")
    assert client.get("/api/v1/auth/me").json()["pin_required"] is True
    other = client.__class__(client.app, base_url=ORIGIN)
    r = other.post("/api/v1/auth/session", headers={"Origin": ORIGIN})
    assert r.status_code == 401 and r.json()["code"] == "pin_invalid"
    r = other.post("/api/v1/auth/session", json={"pin": "4321"}, headers={"Origin": ORIGIN})
    assert r.status_code == 200 and "ytw_session" in other.cookies


def test_pin_wrong_rejected_and_no_cookie(client, csrf):
    """TC-WA-049 PIN 오답은 401 이고 쿠키가 발급되지 않는다."""
    _set_pin(client, csrf, "4321")
    other = client.__class__(client.app, base_url=ORIGIN)
    r = other.post("/api/v1/auth/session", json={"pin": "0000"}, headers={"Origin": ORIGIN})
    assert r.status_code == 401 and "set-cookie" not in r.headers


def test_pin_lockout_after_failures_and_recovery(client, csrf, clock):
    """TC-WA-050 PIN 5회 연속 실패 시 429 pin_locked(+Retry-After), 잠금 중에는 정답도 거부, 시간이 지나면 정답으로 복구."""
    _set_pin(client, csrf, "4321")
    other = client.__class__(client.app, base_url=ORIGIN)
    h = {"Origin": ORIGIN}
    for _ in range(4):
        assert other.post("/api/v1/auth/session", json={"pin": "0000"}, headers=h).status_code == 401
    r = other.post("/api/v1/auth/session", json={"pin": "0000"}, headers=h)
    assert r.status_code == 429 and r.json()["code"] == "pin_locked"
    assert int(r.headers["retry-after"]) > 0
    r = other.post("/api/v1/auth/session", json={"pin": "4321"}, headers=h)
    assert r.status_code == 429
    clock.advance(minutes=5, seconds=1)
    assert other.post("/api/v1/auth/session", json={"pin": "4321"}, headers=h).status_code == 200


def test_pin_lock_escalates(client, csrf, clock):
    """TC-WA-051 두 번째 잠금은 더 길어진다(5분 → 10분)."""
    _set_pin(client, csrf, "4321")
    other = client.__class__(client.app, base_url=ORIGIN)
    h = {"Origin": ORIGIN}
    for _ in range(5):
        other.post("/api/v1/auth/session", json={"pin": "0"}, headers=h)
    clock.advance(minutes=5, seconds=1)
    for _ in range(5):
        r = other.post("/api/v1/auth/session", json={"pin": "0"}, headers=h)
    assert r.status_code == 429
    assert 540 <= int(r.headers["retry-after"]) <= 600


def test_pin_success_resets_failure_counter(client, csrf):
    """TC-WA-052 정답을 입력하면 실패 횟수가 초기화된다."""
    _set_pin(client, csrf, "4321")
    other = client.__class__(client.app, base_url=ORIGIN)
    h = {"Origin": ORIGIN}
    for _ in range(4):
        other.post("/api/v1/auth/session", json={"pin": "0000"}, headers=h)
    assert other.post("/api/v1/auth/session", json={"pin": "4321"}, headers=h).status_code == 200
    for _ in range(4):
        assert other.post("/api/v1/auth/session", json={"pin": "0000"}, headers=h).status_code == 401


def test_pin_change_and_clear_require_current_pin(client, csrf):
    """TC-WA-053 PIN 변경·해제에는 현재 PIN 이 필요하다(없거나 틀리면 401, 값은 그대로)."""
    assert _set_pin(client, csrf, "1111").status_code == 200
    r = _set_pin(client, csrf, "2222")
    assert r.status_code == 401
    r = _set_pin(client, csrf, "2222", current="9999")
    assert r.status_code == 401
    r = client.patch("/api/v1/settings", json={"pin": {"action": "clear"}}, headers=hdr(csrf))
    assert r.status_code == 401
    assert _set_pin(client, csrf, "2222", current="1111").status_code == 200
    r = client.patch("/api/v1/settings", json={"pin": {"action": "clear", "current_pin": "2222"}}, headers=hdr(csrf))
    assert r.status_code == 200 and r.json()["pin_enabled"] is False
    assert client.get("/api/v1/auth/me").json()["pin_required"] is False


def test_pin_clear_when_not_set_is_conflict(client, csrf):
    """TC-WA-054 설정된 PIN 이 없을 때 해제하면 409."""
    r = client.patch("/api/v1/settings", json={"pin": {"action": "clear"}}, headers=hdr(csrf))
    assert r.status_code == 409 and r.json()["code"] == "pin_not_set"


@pytest.mark.parametrize("bad", ["12", "abcd", "1234567890123", "12 34", "", None, 1234])
def test_pin_format_validation(client, csrf, bad):
    """TC-WA-055 PIN 형식(숫자 4~12자리) 위반은 422."""
    r = client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": bad}}, headers=hdr(csrf))
    assert r.status_code == 422


def test_pin_set_invalidates_other_sessions(client, csrf):
    """TC-WA-056 PIN 설정 시 현재 세션 외 다른 세션은 폐기된다."""
    other = client.__class__(client.app, base_url=ORIGIN)
    login(other)
    assert other.get("/api/v1/settings").status_code == 200
    assert _set_pin(client, csrf, "4321").status_code == 200
    assert other.get("/api/v1/settings").status_code == 401
    assert client.get("/api/v1/settings").status_code == 200


def test_session_and_denial_audited(client, db):
    """TC-WA-057 세션 발급·거부·로그아웃이 감사 로그에 남고 비밀은 포함되지 않는다."""
    csrf = login(client)
    _set_pin(client, csrf, "4321")
    other = client.__class__(client.app, base_url=ORIGIN)
    other.post("/api/v1/auth/session", json={"pin": "0000"}, headers={"Origin": ORIGIN})
    client.delete("/api/v1/auth/session", headers=hdr(csrf))
    db.expire_all()
    rows = db.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()
    assert [r.action for r in rows] == ["session.create", "settings.update", "session.denied", "session.delete"]
    dump = " ".join(str(r.detail) + str(r.target_id) for r in rows)
    assert "4321" not in dump and "0000" not in dump and csrf not in dump


def test_session_request_rejects_unknown_fields(client):
    """TC-WA-058 세션 요청 본문의 알 수 없는 필드는 422."""
    r = client.post("/api/v1/auth/session", json={"pin": None, "admin": True}, headers={"Origin": ORIGIN})
    assert r.status_code == 422
