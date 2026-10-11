"""TC-VFB-110~: 세션 유휴 만료(DEF-9-003 / 기본 30분) — 경계, 슬라이딩, 절대 TTL 병행, 설정 검증, 정리 경로 일관성."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from ytweb.config import load_web_settings
from ytweb.core import audit, sessions
from ytweb.core.sessions import create_session, lookup_session, purge_expired
from ytweb.db.models import SessionRow
from ytweb.worker import Worker

from tests.conftest import ORIGIN
from tests.verify_fix_be.conftest import hdr

T0 = datetime(2026, 10, 10, 3, 0, 0, tzinfo=timezone.utc)
IDLE = timedelta(minutes=30)
US = timedelta(microseconds=1)


def _count(factory):
    with factory() as s:
        return s.execute(select(func.count()).select_from(SessionRow)).scalar_one()


# ───────────── lookup / purge 단위 ─────────────

@pytest.mark.parametrize("gap,alive", [(IDLE - US, True), (IDLE, False), (IDLE + US, False), (timedelta(0), True), (timedelta(minutes=1), True)])
def test_tc_vfb_110_lookup_idle_boundary_is_inclusive_expiry(db, gap, alive):
    token, _ = create_session(db, now=T0, ttl_hours=12, idle_timeout=IDLE); db.commit()
    got = lookup_session(db, token, now=T0 + gap, idle_timeout=IDLE); db.commit()
    assert (got is not None) is alive
    assert _rows(db) == (1 if alive else 0)


def _rows(db):
    return db.execute(select(func.count()).select_from(SessionRow)).scalar_one()


def test_tc_vfb_111_lookup_without_idle_timeout_ignores_inactivity(db):
    token, _ = create_session(db, now=T0, ttl_hours=12); db.commit()
    assert lookup_session(db, token, now=T0 + timedelta(hours=11, minutes=59)) is not None


@pytest.mark.parametrize("ttl_gap,alive", [(timedelta(hours=12) - US, True), (timedelta(hours=12), False)])
def test_tc_vfb_112_absolute_ttl_applies_even_with_constant_activity(db, ttl_gap, alive):
    token, _ = create_session(db, now=T0, ttl_hours=12, idle_timeout=IDLE); db.commit()
    t = T0
    while t + timedelta(minutes=25) < T0 + ttl_gap:            # 25분마다 계속 사용
        t += timedelta(minutes=25)
        assert lookup_session(db, token, now=t, idle_timeout=IDLE) is not None
        db.commit()
    got = lookup_session(db, token, now=T0 + ttl_gap, idle_timeout=IDLE)
    assert (got is not None) is alive


def test_tc_vfb_113_activity_slides_the_idle_window(db):
    token, _ = create_session(db, now=T0, ttl_hours=12, idle_timeout=IDLE); db.commit()
    for k in range(1, 6):
        assert lookup_session(db, token, now=T0 + timedelta(minutes=29 * k), idle_timeout=IDLE) is not None
        db.commit()
    assert lookup_session(db, token, now=T0 + timedelta(minutes=29 * 5 + 30), idle_timeout=IDLE) is None


def test_tc_vfb_114_purge_expired_idle_boundary_matches_lookup_boundary(db):
    for gap in (IDLE - US, IDLE, IDLE + US):
        db.query(SessionRow).delete()
        token, _ = create_session(db, now=T0, ttl_hours=12); db.commit()
        by_purge = purge_expired(db, now=T0 + gap, idle_timeout=IDLE); db.commit()
        db.query(SessionRow).delete()
        token2, _ = create_session(db, now=T0, ttl_hours=12); db.commit()
        by_lookup = lookup_session(db, token2, now=T0 + gap, idle_timeout=IDLE) is None
        assert (by_purge == 1) == by_lookup, gap
    db.query(SessionRow).delete(); db.commit()


def test_tc_vfb_115_purge_without_idle_removes_only_absolute_expired(db):
    create_session(db, now=T0, ttl_hours=1); db.commit()
    assert purge_expired(db, now=T0 + timedelta(minutes=59)) == 0
    assert purge_expired(db, now=T0 + timedelta(hours=1)) == 1


def test_tc_vfb_116_create_session_purges_idle_dead_sessions_but_keeps_live_ones(db):
    _, dead = create_session(db, now=T0, ttl_hours=12, idle_timeout=IDLE); db.commit()
    live_tok, live = create_session(db, now=T0 + timedelta(minutes=20), ttl_hours=12, idle_timeout=IDLE); db.commit()
    lookup_session(db, live_tok, now=T0 + timedelta(minutes=45), idle_timeout=IDLE); db.commit()
    create_session(db, now=T0 + timedelta(minutes=50), ttl_hours=12, idle_timeout=IDLE); db.commit()
    ids = set(db.execute(select(SessionRow.id)).scalars())
    assert dead.session_id not in ids and live.session_id in ids and len(ids) == 2


def test_tc_vfb_117_token_edge_cases_still_rejected(db):
    assert lookup_session(db, None, now=T0, idle_timeout=IDLE) is None
    assert lookup_session(db, "", now=T0, idle_timeout=IDLE) is None
    assert lookup_session(db, "a" * 129, now=T0, idle_timeout=IDLE) is None
    assert lookup_session(db, "nope", now=T0, idle_timeout=IDLE) is None


# ───────────── 설정 ─────────────

def _env(**kw):
    base = {"YTWEB_DATABASE_URL": "sqlite:///x.db", "YTWEB_ALLOWED_HOSTS": "127.0.0.1:8080", "YTWEB_MODE": "demo"}
    return {**base, **kw}


def _settings(**kw):
    try:
        return load_web_settings(_env(**kw))
    except KeyError:
        pytest.skip("필수 환경 변수 이름이 다름")


def test_tc_vfb_120_default_is_30_minutes():
    s = _settings()
    assert s.session_idle_minutes == 30 and s.session_idle_timeout == timedelta(minutes=30)


@pytest.mark.parametrize("raw,minutes", [("1", 1), ("45", 45), ("0", 0), ("1440", 1440)])
def test_tc_vfb_121_configured_values(raw, minutes):
    s = _settings(YTWEB_SESSION_IDLE_MINUTES=raw)
    assert s.session_idle_minutes == minutes
    assert s.session_idle_timeout == (timedelta(minutes=minutes) if minutes else None)


@pytest.mark.parametrize("raw", ["-1", "-30", "abc", "", "1.5", "3 0"])
def test_tc_vfb_122_invalid_values_fail_closed_at_startup(raw):
    with pytest.raises(ValueError):
        _settings(YTWEB_SESSION_IDLE_MINUTES=raw)


# ───────────── HTTP ─────────────

def test_tc_vfb_130_http_idle_expiry_boundary_and_401_for_every_protected_call(api, csrf, clock):
    clock.advance(minutes=29, seconds=59)
    assert api.get("/api/v1/auth/me").json()["authenticated"] is True          # 29:59 → 살아 있음, 이 요청이 시계를 갱신
    clock.advance(minutes=30)
    me = api.get("/api/v1/auth/me").json()
    assert me["authenticated"] is False and me["csrf_token"] is None
    for method, url in (("get", "/api/v1/audit"), ("get", "/api/v1/settings")):
        r = getattr(api, method)(url)
        assert r.status_code == 401 and r.json()["code"] == "session_required", url
    r = api.patch("/api/v1/settings", json={"daily_apply_cap": 3}, headers=hdr(csrf))
    assert r.status_code == 401 and r.json()["code"] == "session_required"


def test_tc_vfb_131_http_exact_30_minutes_is_expired_29m59s_is_alive(api, csrf, clock):
    clock.advance(minutes=30)
    r = api.get("/api/v1/audit")
    assert r.status_code == 401


def test_tc_vfb_132_http_sliding_session_survives_beyond_30_minutes_total(api, csrf, clock):
    for _ in range(5):
        clock.advance(minutes=20)
        assert api.get("/api/v1/audit").status_code == 200
    clock.advance(minutes=31)
    assert api.get("/api/v1/audit").status_code == 401


def test_tc_vfb_133_http_new_session_after_idle_expiry_works_and_old_cookie_is_dead(api, csrf, clock):
    old_cookie = api.cookies.get("ytw_session")
    clock.advance(minutes=31)
    assert api.get("/api/v1/audit").status_code == 401
    r = api.post("/api/v1/auth/session", json=None, headers={"Origin": ORIGIN})
    assert r.status_code == 200
    new_csrf = r.json()["csrf_token"]
    assert api.get("/api/v1/audit").status_code == 200
    assert api.patch("/api/v1/settings", json={"daily_apply_cap": 3}, headers=hdr(new_csrf)).status_code == 200
    from ytweb.core.sessions import hash_token
    with api.app.state.session_factory() as s:
        assert s.get(SessionRow, hash_token(old_cookie)) is None        # 옛 토큰 행은 삭제됨


def test_tc_vfb_134_expired_old_token_cannot_be_revived_by_replaying_it(app, factory, clock):
    from fastapi.testclient import TestClient
    from tests.conftest import login
    with TestClient(app, base_url=ORIGIN) as c1:
        login(c1)
        token = c1.cookies.get("ytw_session")
    clock.advance(minutes=31)
    with TestClient(app, base_url=ORIGIN) as c2:
        c2.cookies.set("ytw_session", token, path="/api")
        assert c2.get("/api/v1/auth/me").json()["authenticated"] is False
        clock.advance(seconds=-60 * 31)           # 시계를 되돌려도(이론상) 이미 지워진 세션은 부활하지 않는다
        assert c2.get("/api/v1/auth/me").json()["authenticated"] is False


@pytest.mark.no_idle
def test_tc_vfb_135_idle_disabled_by_zero_only_absolute_ttl_applies(api, csrf, clock):
    clock.advance(hours=11, minutes=59)
    assert api.get("/api/v1/audit").status_code == 200
    clock.advance(hours=12)
    assert api.get("/api/v1/audit").status_code == 401


@pytest.mark.parametrize("final,status", [(timedelta(hours=12) - timedelta(seconds=1), 200), (timedelta(hours=12), 401)])
def test_tc_vfb_136_absolute_ttl_still_cuts_an_active_http_session(api, csrf, clock, final, status):
    start = clock.now
    while clock.now + timedelta(minutes=25) < start + final:
        clock.advance(minutes=25)
        assert api.get("/api/v1/audit").status_code == 200      # 25분마다 계속 사용(유휴 만료에는 안 걸림)
    clock.now = start + final
    assert api.get("/api/v1/audit").status_code == status


def test_tc_vfb_137_pin_flow_not_weakened_idle_expiry_requires_pin_again(web_settings, engine, clock, fake_time, monkeypatch):
    from fastapi.testclient import TestClient
    from tests.conftest import CORE_ROUTERS, login
    from ytweb.app import create_app
    from ytweb.core.ratelimit import RateLimits
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "1")
    app = create_app(web_settings, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time,
                     rate_limits=RateLimits(global_per_min=10_000, write_per_min=10_000, auth_per_min=10_000))
    with TestClient(app, base_url=ORIGIN) as c:
        t = login(c)
        assert c.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "123456"}}, headers=hdr(t)).status_code == 200
        clock.advance(minutes=31)
        assert c.get("/api/v1/audit").status_code == 401
        no_pin = c.post("/api/v1/auth/session", json=None, headers={"Origin": ORIGIN})
        assert no_pin.status_code in (401, 403, 422)                        # PIN 없이는 새 세션을 못 받는다
        assert c.post("/api/v1/auth/session", json={"pin": "123456"}, headers={"Origin": ORIGIN}).status_code == 200
        assert c.get("/api/v1/audit").status_code == 200


# ───────────── Worker ─────────────

def test_tc_vfb_140_worker_maintenance_purges_idle_sessions_when_configured(factory, clock, db):
    create_session(db, now=clock(), ttl_hours=12); db.commit()
    clock.advance(minutes=31)
    w = Worker(factory, clock=clock, worker_id="vfb", session_idle_timeout=IDLE)
    w.maintenance()
    db.expire_all()
    assert _rows(db) == 0


def test_tc_vfb_141_worker_maintenance_without_idle_keeps_sessions_until_ttl(factory, clock, db):
    create_session(db, now=clock(), ttl_hours=12); db.commit()
    clock.advance(minutes=31)
    w = Worker(factory, clock=clock, worker_id="vfb")
    w.maintenance()
    db.expire_all()
    assert _rows(db) == 1


def test_tc_vfb_142_http_session_issue_purges_idle_dead_sessions(api, csrf, clock, factory):
    """POST auth/session 경로(settings.session_idle_timeout 전달)에서도 유휴 만료 세션이 정리된다."""
    assert _count(factory) == 1
    clock.advance(minutes=31)
    assert api.post("/api/v1/auth/session", json=None, headers={"Origin": ORIGIN}).status_code == 200
    assert _count(factory) == 1          # 옛 세션은 지워지고 새 세션만 남는다


def test_tc_vfb_143_worker_main_passes_configured_idle_timeout(monkeypatch, tmp_path):
    import ytweb.worker as w
    seen = {}

    class Rec:
        def __init__(self, factory, **kw):
            seen.update(kw)

        def request_stop(self, *a): ...
        def run(self): ...

    monkeypatch.setattr(w, "Worker", Rec)
    monkeypatch.setattr(w, "setup_logging", lambda **k: None)
    monkeypatch.setattr(w, "load_domain_handlers", lambda: None)
    monkeypatch.setattr(w.signal, "signal", lambda *a: None)
    monkeypatch.setenv("YTWEB_DATABASE_URL", f"sqlite:///{tmp_path / 'm.db'}")
    monkeypatch.setenv("YTWEB_SESSION_IDLE_MINUTES", "7")
    monkeypatch.setenv("YTWEB_ALLOWED_HOSTS", "127.0.0.1:8080")
    w.main()
    assert seen["session_idle_timeout"] == timedelta(minutes=7)
