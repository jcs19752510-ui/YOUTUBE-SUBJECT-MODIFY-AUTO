"""PIN 무차별 대입·속도 제한(승인된 방어적 시험, 데모, 외부호출 차단)."""
import time, statistics
import pytest
from fastapi.testclient import TestClient
from ytweb.app import create_app
from ytweb.core.ratelimit import RateLimits
from ytweb.core import pin as pinmod
from ytweb.db.session import make_session_factory
from tests.conftest import ORIGIN

PIN = "482916"

def mk(web_settings, engine, clock, fake_time, monkeypatch, limits):
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "1"); monkeypatch.delenv("YTWEB_STATIC_DIR", raising=False)
    with make_session_factory(engine)() as s:
        pinmod.set_pin(s, PIN, now=clock()); s.commit()
    return create_app(web_settings, clock=clock, time_fn=fake_time, rate_limits=limits)

@pytest.fixture
def pc(web_settings, engine, clock, fake_time, monkeypatch):
    app = mk(web_settings, engine, clock, fake_time, monkeypatch, RateLimits(10_000, 10_000, 10_000))
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as c:
        yield c

def login(c, pin, extra=None):
    h = {"Origin": ORIGIN}; h.update(extra or {})
    return c.post("/api/v1/auth/session", json={"pin": pin}, headers=h)

def test_lock_after_5_and_correct_pin_blocked_while_locked(pc):
    codes = [login(pc, "000%d" % i).status_code for i in range(5)]
    assert codes == [401, 401, 401, 401, 429], codes
    r = login(pc, PIN)
    assert r.status_code == 429, "잠금 중 올바른 PIN 통과 = 결함"
    assert int(r.headers["Retry-After"]) > 0
    assert "ytw_session" not in pc.cookies

@pytest.mark.parametrize("hdrs", [{"X-Forwarded-For": "10.9.9.9"}, {"X-Real-IP": "1.2.3.4"}, {"Forwarded": "for=8.8.8.8"}, {"User-Agent": "x"}])
def test_lock_not_bypassed_by_headers_or_new_client(pc, web_settings, hdrs):
    for i in range(5): login(pc, "111%d" % i, hdrs)
    assert login(pc, PIN, {**hdrs, "X-Forwarded-For": "203.0.113.%d" % (len(hdrs)+7)}).status_code == 429
    pc.cookies.clear()
    assert login(pc, PIN, hdrs).status_code == 429

def test_unlock_after_wait_and_escalation(pc, clock):
    for i in range(5): login(pc, "222%d" % i)
    clock.advance(minutes=4, seconds=50); assert login(pc, PIN).status_code == 429
    clock.advance(seconds=20)
    for i in range(5): r = login(pc, "333%d" % i)          # 두번째 잠금은 10분이어야 함
    assert r.status_code == 429
    clock.advance(minutes=6); assert login(pc, PIN).status_code == 429, "2차 잠금이 5분으로 안 늘었음"
    clock.advance(minutes=5); assert login(pc, PIN).status_code == 200

def test_success_resets_counter(pc):
    for i in range(4): login(pc, "444%d" % i)
    assert login(pc, PIN).status_code == 200
    for i in range(4): assert login(pc, "555%d" % i).status_code == 401

def test_lock_check_before_hash_and_pin_none_counts(pc):
    for i in range(4): pc.post("/api/v1/auth/session", headers={"Origin": ORIGIN})   # PIN 없음 요청도 실패로 센다
    r = pc.post("/api/v1/auth/session", headers={"Origin": ORIGIN})
    assert r.status_code == 429, r.status_code

def test_default_rate_limit_auth_10_per_min(web_settings, engine, clock, fake_time, monkeypatch):
    app = mk(web_settings, engine, clock, fake_time, monkeypatch, RateLimits())
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as c:
        codes = [login(c, PIN if i == 3 else "9%03d" % i).status_code for i in range(12)]
    print("codes", codes)
    assert 429 in codes

@pytest.mark.parametrize("h,expect_ok", [({"Sec-Fetch-Site": "cross-site"}, True), ({"Origin": "http://evil.example"}, False)])
def test_foreign_get_flood_owner_window(web_settings, engine, clock, fake_time, monkeypatch, h, expect_ok):
    """첫 실행: 두 번째 변형(Sec-Fetch-Site 없는 비브라우저 GET 폭주)은 소유자 한도 소진 = Low 결함 후보로 기록."""
    app = mk(web_settings, engine, clock, fake_time, monkeypatch, RateLimits())
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as c:
        for _ in range(700): c.get("/api/v1/auth/me", headers=h)
        r = c.get("/api/v1/auth/me", headers={"Origin": ORIGIN})
        print("owner after flood", h, r.status_code)
        assert (r.status_code == 200) == expect_ok

def test_timing_pin_length_and_value_reference(pc, clock):
    import ytweb.core.pin as p
    # 서버 경로 직접: verify_pin_hash 시간 (scrypt 고정 비용이라 길이/값 무관해야 함)
    h = p.hash_pin(PIN)
    def t(x, n=15):
        v = []
        for _ in range(n):
            a = time.perf_counter(); p.verify_pin_hash(x, h); v.append(time.perf_counter() - a)
        return statistics.median(v)
    ts = {x: t(x) for x in ["1", "1234", PIN, "482917", "4829160000", "9" * 12, "x" * 64]}
    print("timing", ts)
    lo, hi = min(ts.values()), max(ts.values())
    assert hi / lo < 1.5, ts
