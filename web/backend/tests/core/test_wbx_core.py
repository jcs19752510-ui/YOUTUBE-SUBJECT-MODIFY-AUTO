"""수정 단위 W-FIX-BE(2026-10-11) 코어 시험 TC-WBX-019~: 세션 유휴 만료(DEF-9-003), stale 작업 재큐(DEF-7B-001), 설정값."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from tests.conftest import FakeClock, hdr, login
from ytweb.config import load_web_settings
from ytweb.core import jobs
from ytweb.core.sessions import create_session, lookup_session, purge_expired
from ytweb.db.models import Job, SessionRow
from ytweb.worker import REAP_EVERY, Worker

T0 = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)
IDLE = timedelta(minutes=30)


@pytest.fixture(autouse=True)
def _clean_handlers():
    saved = dict(jobs._HANDLERS)
    jobs._HANDLERS.clear()
    yield
    jobs._HANDLERS.clear()
    jobs._HANDLERS.update(saved)


# ───────────── DEF-9-003: 세션 유휴 만료 ─────────────

@pytest.mark.parametrize("gap,alive", [(timedelta(minutes=29, seconds=59), True), (IDLE, False), (IDLE + timedelta(seconds=1), False)])
def test_tc_wbx_019_idle_boundary(db, gap, alive):
    token, _ = create_session(db, now=T0, ttl_hours=12, idle_timeout=IDLE)
    db.commit()
    assert (lookup_session(db, token, now=T0 + gap, idle_timeout=IDLE) is not None) is alive
    db.commit()
    assert (db.execute(select(SessionRow)).first() is not None) is alive   # 만료된 세션은 지워진다


def test_tc_wbx_020_use_refreshes_idle_clock_but_absolute_ttl_still_applies(db):
    token, _ = create_session(db, now=T0, ttl_hours=1, idle_timeout=IDLE)
    for minutes in (20, 40, 60 - 1):
        assert lookup_session(db, token, now=T0 + timedelta(minutes=minutes), idle_timeout=IDLE) is not None
    assert lookup_session(db, token, now=T0 + timedelta(hours=1), idle_timeout=IDLE) is None   # 절대 만료는 그대로


def test_tc_wbx_021_without_idle_timeout_only_absolute_expiry_applies(db):
    token, _ = create_session(db, now=T0, ttl_hours=12)
    assert lookup_session(db, token, now=T0 + timedelta(hours=11), idle_timeout=None) is not None


def test_tc_wbx_022_purge_removes_idle_sessions_and_create_purges_them_too(db):
    old, _ = create_session(db, now=T0, ttl_hours=12, idle_timeout=IDLE)
    db.commit()
    assert purge_expired(db, now=T0 + timedelta(minutes=31)) == 0                       # 유휴 기준을 주지 않으면 그대로(옛 동작)
    assert purge_expired(db, now=T0 + timedelta(minutes=31), idle_timeout=IDLE) == 1
    create_session(db, now=T0, ttl_hours=12, idle_timeout=IDLE)
    create_session(db, now=T0 + timedelta(hours=1), ttl_hours=12, idle_timeout=IDLE)    # 이 호출이 위 세션을 정리
    db.commit()
    assert len(db.execute(select(SessionRow)).scalars().all()) == 1
    assert old


def test_tc_wbx_023_http_idle_session_gets_401_and_activity_keeps_it_alive(client, clock, csrf):
    assert client.get("/api/v1/settings").status_code == 200
    for _ in range(4):                      # 20분씩 4번 = 80분. 매번 사용하므로 유휴 30분에 걸리지 않는다
        clock.advance(minutes=20)
        assert client.get("/api/v1/settings").status_code == 200
    clock.advance(minutes=31)
    r = client.get("/api/v1/settings")
    assert r.status_code == 401 and r.json()["code"] == "session_required"
    assert client.get("/api/v1/auth/me").json()["authenticated"] is False


def test_tc_wbx_024_http_me_and_csrf_paths_also_honor_idle(client, clock, csrf):
    clock.advance(minutes=31)
    assert client.get("/api/v1/auth/me").json() == {"authenticated": False, "pin_required": False, "csrf_token": None,
                                                              "login_required": False, "admin_login_id": None, "idle_timeout_seconds": 1800}
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 3}, headers=hdr(csrf))
    assert r.status_code == 401 and r.json()["code"] == "session_required"
    assert login(client)  # 다시 로그인하면 새 세션


def test_tc_wbx_025_idle_setting_parsing(tmp_path):
    base = {"YTWEB_DATABASE_URL": "sqlite://", "YTWEB_BASE_DIR": str(tmp_path)}
    assert load_web_settings(base).session_idle_timeout == timedelta(minutes=30)
    assert load_web_settings({**base, "YTWEB_SESSION_IDLE_MINUTES": "5"}).session_idle_timeout == timedelta(minutes=5)
    assert load_web_settings({**base, "YTWEB_SESSION_IDLE_MINUTES": "0"}).session_idle_timeout is None
    with pytest.raises(ValueError):
        load_web_settings({**base, "YTWEB_SESSION_IDLE_MINUTES": "-1"})
    with pytest.raises(ValueError):
        load_web_settings({**base, "YTWEB_SESSION_IDLE_MINUTES": "abc"})


# ───────────── DEF-7B-001: stale 작업 ─────────────

def _running(db, job_type, locked_at, attempts=1):
    j = jobs.enqueue(db, type=job_type, payload={}, now=T0)
    db.execute(update(Job).where(Job.id == j.id).values(status="running", locked_by="dead:1", locked_at=locked_at, attempts=attempts))
    db.commit()
    return j.id


@pytest.mark.parametrize("age,requeued", [(timedelta(minutes=4, seconds=59), 0), (timedelta(minutes=5), 0), (timedelta(minutes=5, seconds=1), 1)])
def test_tc_wbx_026_batch_execute_goes_stale_after_five_minutes(db, age, requeued):
    jid = _running(db, "batch.execute", T0)
    assert jobs.requeue_stale(db, now=T0 + age) == (requeued, 0)
    db.commit()
    db.expire_all()
    assert db.get(Job, jid).status == ("queued" if requeued else "running")


def test_tc_wbx_027_other_job_types_keep_the_ten_minute_rule(db):
    jid = _running(db, "videos.sync", T0)
    assert jobs.requeue_stale(db, now=T0 + timedelta(minutes=9)) == (0, 0)
    assert jobs.requeue_stale(db, now=T0 + timedelta(minutes=10, seconds=1)) == (1, 0)
    db.commit()
    assert db.get(Job, jid).status == "queued"


def test_tc_wbx_028_zero_stale_after_releases_everything_running_and_caps_attempts(db):
    fresh = _running(db, "batch.execute", T0 - timedelta(seconds=1))
    nolock = _running(db, "videos.sync", None)
    worn = _running(db, "batch.execute", T0 - timedelta(seconds=1), attempts=jobs.MAX_ATTEMPTS)
    assert jobs.requeue_stale(db, now=T0, stale_after=timedelta(0)) == (2, 1)
    db.commit()
    db.expire_all()
    assert [db.get(Job, i).status for i in (fresh, nolock, worn)] == ["queued", "queued", "failed"]
    assert db.get(Job, worn).error == "worker_lost"
    assert db.get(Job, fresh).locked_by is None and db.get(Job, fresh).locked_at is None


def test_tc_wbx_029_job_without_heartbeat_is_orphan_even_by_default_rule(db):
    jid = _running(db, "videos.sync", None)
    assert jobs.requeue_stale(db, now=T0) == (1, 0)
    db.commit()
    assert db.get(Job, jid).status == "queued"


def test_tc_wbx_030_worker_start_requeues_orphans_after_item_recovery_and_runs_them(factory, db):
    calls: list[str] = []
    jobs.register_handler("batch.execute", lambda f, j: calls.append(j.id) or {"ok": True})
    jid = _running(db, "batch.execute", T0 - timedelta(seconds=30))
    order: list[str] = []
    w = Worker(factory, clock=lambda: T0, startup_recover=lambda f, now, stale_after: order.append("items") or 0)
    w.stop_event.set()                      # 시작 처리만 하고 반복에는 들어가지 않는다
    w.run()
    db.expire_all()
    assert order == ["items"] and db.get(Job, jid).status == "queued" and db.get(Job, jid).attempts == 1
    assert jobs.process_next(factory, worker_id="w2", clock=lambda: T0) is True
    db.expire_all()
    assert calls == [jid] and db.get(Job, jid).status == "succeeded" and db.get(Job, jid).attempts == 2


def test_tc_wbx_031_crash_loop_poison_job_ends_failed_after_three_starts(factory, db):
    jid = _running(db, "batch.execute", T0 - timedelta(seconds=30), attempts=0)
    for expected in ("queued", "queued", "queued", "failed"):
        w = Worker(factory, clock=lambda: T0)
        w.stop_event.set()
        w.run()
        db.expire_all()
        assert db.get(Job, jid).status == expected
        if expected == "queued":            # 다시 잡혀서 또 죽은 것을 흉내낸다
            db.execute(update(Job).where(Job.id == jid).values(status="running", locked_by="dead:1", locked_at=T0 - timedelta(seconds=30), attempts=Job.attempts + 1))
            db.commit()
    assert db.get(Job, jid).error == "worker_lost"


def test_tc_wbx_032_tick_reaps_stale_batch_job_without_waiting_for_maintenance_and_at_most_once_a_minute(factory, db):
    jobs.register_handler("batch.execute", lambda f, j: {"ok": True})
    t = [T0 + timedelta(minutes=6)]
    jid = _running(db, "batch.execute", T0)
    w = Worker(factory, clock=lambda: t[0])
    w._last_maintenance = t[0]                          # 10분 정비는 아직 차례가 아니다
    w.tick()
    db.expire_all()
    assert db.get(Job, jid).status == "succeeded" and db.get(Job, jid).attempts == 2   # 재큐된 뒤 같은 틱에서 다시 처리됐다
    db.execute(update(Job).where(Job.id == jid).values(status="running", locked_by="dead:1", locked_at=T0))
    db.commit()
    t[0] += REAP_EVERY - timedelta(seconds=1)
    assert w.reap_stale_jobs() == (0, 0)                # 1분 안에는 다시 보지 않는다
    t[0] += timedelta(seconds=1)
    assert w.reap_stale_jobs() == (1, 0)


def test_tc_wbx_033_reap_failure_in_tick_is_logged_and_does_not_stop_the_tick(factory, monkeypatch, caplog):
    w = Worker(factory, clock=FakeClock())
    monkeypatch.setattr(w, "reap_stale_jobs", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    with caplog.at_level("ERROR"):
        assert w.tick() == 0
    assert any("stale 작업 정리 실패" in r.message for r in caplog.records)
