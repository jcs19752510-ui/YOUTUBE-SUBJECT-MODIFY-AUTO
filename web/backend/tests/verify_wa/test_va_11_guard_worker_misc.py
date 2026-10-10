"""TC-VA-159~: 커버리지 보강(가드 예외 경로, 팩토리, 라우터 탐색, 워커 기동 정리, claim 경쟁)."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, update

from tests.verify_wa.helpers import asgi_call, body_json, header
from ytweb.app import app_from_env, create_app, discover_routers
from ytweb.core import jobs
from ytweb.core.guard import GuardMiddleware
from ytweb.core.ratelimit import RateLimiter, RateLimits
from ytweb.db.models import Job
from ytweb.worker import Worker

T0 = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)


def _guard(inner):
    return GuardMiddleware(inner, allowed_hosts=("127.0.0.1:8080",), limiter=RateLimiter(RateLimits()))


def test_guard_unhandled_error_before_response_is_clean_500(caplog):
    """TC-VA-159 [S-W09] 내부 앱이 응답 시작 전에 예외를 던지면 500 problem+json + 보안 헤더, 예외 메시지는 응답에 없다."""
    async def inner(scope, receive, send):
        raise RuntimeError("/secret/path password=hunter2")
    out = asgi_call(_guard(inner), "GET", "/api/x", [("host", "127.0.0.1:8080")])
    assert out["status"] == 500 and body_json(out)["code"] == "internal_error"
    assert b"hunter2" not in out["body"] and b"secret" not in out["body"]
    assert header(out, "x-content-type-options") == "nosniff" and header(out, "x-request-id")


def test_guard_error_after_response_started_is_reraised_not_double_sent():
    """TC-VA-160 응답이 이미 시작된 뒤 예외가 나면 두 번째 응답을 덧붙이지 않고 예외를 다시 올린다(연결 정리는 서버 몫)."""
    sent = []

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("late")

    async def go():
        async def recv():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def snd(m):
            sent.append(m)
        scope = {"type": "http", "method": "GET", "path": "/api/x", "headers": [(b"host", b"127.0.0.1:8080")]}
        await _guard(inner)(scope, recv, snd)

    with pytest.raises(RuntimeError, match="late"):
        asyncio.run(go())
    assert [m["type"] for m in sent] == ["http.response.start"]
    assert sent[0]["status"] == 200


def test_guard_ignores_lifespan_scope():
    """TC-VA-161 http/websocket 이외 스코프(lifespan)는 그대로 통과시킨다."""
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(_guard(inner)({"type": "lifespan", "headers": []}, None, None))
    assert seen == ["lifespan"]


def test_guard_logs_only_safe_fields(caplog):
    """TC-VA-162 [S-W09] 접근 로그에 쿼리 문자열·헤더 값·본문이 들어가지 않는다(method/path/status/ms/request_id 만)."""
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})
    with caplog.at_level(logging.INFO, logger="ytweb.access"):
        asgi_call(_guard(inner), "GET", "/api/x", [("host", "127.0.0.1:8080"), ("cookie", "ytw_session=SECRETCOOKIE")], query=b"token=SECRETQUERY")
    rec = [r for r in caplog.records if r.name == "ytweb.access"][-1]
    dump = json.dumps(rec.__dict__, default=str)
    assert "SECRETCOOKIE" not in dump and "SECRETQUERY" not in dump
    assert rec.status == 200 and rec.path == "/api/x" and rec.method == "GET"


def test_app_from_env_builds_working_app(tmp_path, monkeypatch):
    """TC-VA-163 uvicorn --factory 진입점이 환경변수로 앱을 만들고 /healthz 가 200."""
    monkeypatch.setenv("YTWEB_DATABASE_URL", f"sqlite:///{tmp_path / 'e.db'}")
    monkeypatch.setenv("YTWEB_BASE_DIR", str(tmp_path.parents[0]))
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "1")
    monkeypatch.delenv("YTWEB_STATIC_DIR", raising=False)
    app = app_from_env()
    assert asgi_call(app, "GET", "/healthz", [("host", "x")])["status"] == 200
    assert asgi_call(app, "GET", "/api/readyz", [("host", "127.0.0.1:8080")])["status"] == 200
    assert asgi_call(app, "GET", "/api/readyz", [("host", "evil")])["status"] == 200  # 헬스는 Host 면제(설계 결정 4)


def test_discover_routers_skips_underscore_and_modules_without_router(tmp_path, monkeypatch):
    """TC-VA-164 라우터 자동 탐색: `_` 로 시작하는 모듈과 router 속성 없는 모듈은 제외, 나머지는 정렬해서 반환."""
    pkg = tmp_path / "va_routers_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "_hidden.py").write_text("router = 1\n")
    (pkg / "plain.py").write_text("x = 1\n")
    (pkg / "zeta.py").write_text("router = 1\n")
    (pkg / "alpha.py").write_text("router = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert discover_routers("va_routers_pkg") == ["va_routers_pkg.alpha", "va_routers_pkg.zeta"]
    sys.modules.pop("va_routers_pkg", None)


def test_static_dir_without_index_gives_problem_404(web_settings, engine, clock, tmp_path, monkeypatch):
    """TC-VA-165 정적 폴더에 index.html 이 없으면 SPA 폴백은 problem+json 404(500 아님)."""
    d = tmp_path / "dist"
    d.mkdir()
    monkeypatch.setenv("YTWEB_STATIC_DIR", str(d))
    app = create_app(web_settings, clock=clock, router_modules=["ytweb.routers.health"])
    out = asgi_call(app, "GET", "/some/screen", [("host", "127.0.0.1:8080")])
    assert out["status"] == 404 and body_json(out)["code"] == "not_found"


def test_worker_startup_recover_runs_with_zero_stale_and_failure_does_not_block(factory, log_capture):
    """TC-VA-166 워커 기동 시 startup_recover 가 stale_after=0 으로 호출되고, 이 함수가 예외를 던져도 워커는 작업 처리를 계속한다."""
    calls = []

    def recover(f, now, *, stale_after):
        calls.append(stale_after)
        raise RuntimeError("recover boom")

    w = Worker(factory, clock=lambda: T0, startup_recover=recover, poll_seconds=0.01)
    ticks = []
    orig = w.tick
    w.tick = lambda: (ticks.append(1), w.request_stop(), orig())[-1]
    w.run()
    assert calls == [timedelta(0)] and ticks == [1]
    assert "정리 실패" in log_capture.getvalue()


def test_claim_loses_race_returns_none_on_sqlite(engine, factory):
    """TC-VA-167 SQLite 경로: SELECT 후 UPDATE 사이에 다른 처리자가 먼저 가져가면 claim 은 None(중복 실행 방지)."""
    with factory() as s:
        jobs.enqueue(s, type="t", payload={}, now=T0)
        s.commit()
    fired = []

    @event.listens_for(engine, "before_cursor_execute")
    def steal(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE JOBS") and not fired:
            fired.append(1)
            with engine.begin() as other:  # 다른 연결이 먼저 상태를 바꾼다
                other.execute(update(Job).values(status="running", locked_by="thief"))

    try:
        with factory() as s:
            got = jobs.claim(s, worker_id="w1", now=T0)
            s.commit()
    finally:
        event.remove(engine, "before_cursor_execute", steal)
    assert fired and got is None
    with factory() as s:
        row = s.query(Job).one()
        assert row.locked_by == "thief" and row.attempts == 0


@pytest.mark.parametrize("advance,expected", [(0.0, "60"), (30.5, "30"), (30.0, "30"), (59.9, "1"), (59.999, "1")])
def test_retry_after_is_ceiling_seconds_never_zero(web_settings, engine, clock, fake_time, advance, expected):
    """TC-VA-168 [S-W13] 429 의 Retry-After 는 남은 시간의 올림(최소 1초)이다: 0 이 되어 클라이언트가 즉시 재시도 폭주하지 않게 한다."""
    app = create_app(web_settings, clock=clock, router_modules=["ytweb.routers.auth"], time_fn=fake_time,
                     rate_limits=RateLimits(global_per_min=1, write_per_min=100, auth_per_min=100))
    h = [("host", "127.0.0.1:8080")]
    assert asgi_call(app, "GET", "/api/v1/auth/me", h)["status"] == 200
    fake_time.t += advance
    out = asgi_call(app, "GET", "/api/v1/auth/me", h)
    assert out["status"] == 429
    assert header(out, "retry-after") == expected


@pytest.mark.parametrize("method,foreign", [("POST", True), ("PUT", True), ("PATCH", True), ("DELETE", True), ("GET", False), ("HEAD", False)])
def test_missing_origin_counts_as_foreign_only_for_state_changing_methods(web_settings, engine, clock, fake_time, method, foreign):
    """TC-VA-169 Origin 없는 요청은 상태 변경 메서드 4종에서만 외부로 분류되어 소유자 한도를 쓰지 않는다(GET/HEAD 는 소유자 한도 사용)."""
    app = create_app(web_settings, clock=clock, router_modules=["ytweb.routers.auth"], time_fn=fake_time,
                     rate_limits=RateLimits(global_per_min=1, write_per_min=100, auth_per_min=100))
    h = [("host", "127.0.0.1:8080")]
    asgi_call(app, method, "/api/v1/auth/me", h, [b""])           # 첫 요청(분류에 따라 소유자 한도 1 을 쓸 수도, 안 쓸 수도)
    second = asgi_call(app, "GET", "/api/v1/auth/me", h)["status"]
    assert (second == 200) == foreign


def test_session_issue_purges_expired_rows(web_settings, engine, factory, clock, app, client):
    """TC-VA-170 [S-W08] 세션 발급 시 만료된 세션 행이 정리된다(만료 행이 20개 한도를 차지하거나 쌓이지 않는다)."""
    from sqlalchemy import func, select

    from tests.conftest import login
    from ytweb.db.models import SessionRow
    for _ in range(3):
        login(client)
    clock.advance(hours=12, seconds=1)
    login(client)
    with factory() as s:
        assert s.execute(select(func.count()).select_from(SessionRow)).scalar_one() == 1


def test_session_lookup_updates_last_seen_but_not_expiry(client, clock, factory):
    """TC-VA-171 [S-W08] 세션 사용 시 last_seen 은 현재 시각으로 갱신되고 만료 시각(절대 TTL)은 늘어나지 않는다."""
    from sqlalchemy import select

    from tests.conftest import login
    from ytweb.db.models import SessionRow
    login(client)
    with factory() as s:
        before = s.execute(select(SessionRow)).scalar_one()
        created, expires = before.created_at, before.expires_at
    clock.advance(hours=3)
    assert client.get("/api/v1/auth/me").json()["authenticated"] is True
    with factory() as s:
        row = s.execute(select(SessionRow)).scalar_one()
        assert row.last_seen == created + timedelta(hours=3)
        assert row.expires_at == expires


@pytest.mark.parametrize("gap,reruns", [(timedelta(minutes=9, seconds=59), False), (timedelta(minutes=10), True), (timedelta(minutes=30), True)])
def test_worker_maintenance_interval_is_ten_minutes(factory, monkeypatch, gap, reruns):
    """TC-VA-172 정비(stale 정리·만료 삭제)는 10분 간격: 9분59초 뒤엔 건너뛰고 정확히 10분 뒤엔 다시 실행한다(상수가 아닌 리터럴로 비교)."""
    now = [T0]
    calls = []
    monkeypatch.setattr(jobs, "requeue_stale", lambda s, *, now: calls.append(now) or (0, 0))
    w = Worker(factory, clock=lambda: now[0])
    w.maintenance()
    now[0] = T0 + gap
    w.maintenance()
    assert len(calls) == (2 if reruns else 1)


def _alembic_cli(*args: str) -> str:
    import os
    import subprocess
    from pathlib import Path
    backend = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if not k.startswith("YTWEB_")}
    env["PYTHONPATH"] = str(backend)
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=backend, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
    return r.stdout


def test_alembic_cli_offline_upgrade_and_downgrade_render():
    """TC-VA-173 [S-W13a] 운영자가 쓰는 실제 CLI(`alembic upgrade head --sql` / `downgrade 0001:base --sql`)가 DB 없이 성공하고,
    14개 테이블 생성 + audit_log 변경 권한 회수(REVOKE)를 포함하며, 데이터를 읽는 쪽 권한을 새로 주는 GRANT 는 없다."""
    up = _alembic_cli("upgrade", "head", "--sql")
    assert up.count("CREATE TABLE ") == 15 and "CREATE TABLE alembic_version" in up  # 모델 14 + alembic_version
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM ytweb_app" in up
    assert "GRANT" not in up.upper().replace("INTEGRITY", "")
    down = _alembic_cli("downgrade", "0001:base", "--sql")
    assert down.count("DROP TABLE IF EXISTS") == 14 and "DELETE FROM alembic_version" in down


@pytest.mark.parametrize("val,bad", [(1e22, True), (1e16, True), (-1e300, True), (-0.0, True), (0.0, False), (1e15, False),
                                     (0.1, False), (1e-7, False), (-5, False), (2**70, False), ("1e22", False)])
def test_audit_record_rejects_only_jsonb_unstable_floats_at_any_depth(db, val, bad):
    """TC-VA-174 [S-W16] 감사 detail 의 JSONB 불안정 float(지수 표기 큰 수·-0.0)는 중첩 위치와 무관하게 기록 전에 ValueError, 평범한 값은 허용(SQLite 수준, DEF-6-008 회귀)."""
    from ytweb.core import audit
    for detail in ({"v": val}, {"a": [{"b": val}]}, {"a": ({"b": val},)}):
        if bad:
            with pytest.raises(ValueError):
                audit.record(db, actor="o", action="a", detail=detail, now=T0)
        else:
            audit.record(db, actor="o", action="a", detail=detail, now=T0)
    if bad:
        assert audit.verify_chain(db) is True  # 거부된 기록은 행을 남기지 않아 체인이 그대로 유효


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_refuses_non_finite_numbers(db, bad):
    """TC-VA-175 [S-W16] 정규 JSON 은 NaN/Infinity 를 거부한다(JSON 표준 밖 값이 해시 입력에 섞이지 않게). 감사 기록도 같은 이유로 실패하고 행을 남기지 않는다."""
    from ytweb.core import audit
    from ytweb.core.canonical import canonical_json
    with pytest.raises(ValueError):
        canonical_json({"a": [bad]})
    with pytest.raises(ValueError):
        audit.record(db, actor="o", action="a", detail={"v": bad}, now=T0)
    from sqlalchemy import func, select

    from ytweb.db.models import AuditLog
    assert db.execute(select(func.count()).select_from(AuditLog)).scalar_one() == 0


@pytest.mark.parametrize("ch,ok", [("\x00", False), ("\x1f", False), ("\n", False), ("\t", False), (" ", True), ("가", True), ("é", True)])
def test_tone_control_character_boundary(client, csrf, ch, ok):
    """TC-VA-176 [S-W13] tone 항목 안의 제어문자 경계: 0x00~0x1f 는 422, 0x20(공백)·일반 문자는 허용."""
    from tests.conftest import hdr
    r = client.patch("/api/v1/settings", json={"tone": [f"a{ch}b"]}, headers=hdr(csrf))
    assert (r.status_code == 200) == ok, r.text


def test_pin_lock_retry_after_never_zero(db, clock):
    """TC-VA-177 [S-W08] 잠금이 1초도 안 남았을 때 Retry-After/hint 는 0 이 아니라 1 이다."""
    from ytweb.core import pin
    from ytweb.core.errors import ProblemError
    pin.set_pin(db, "246810", now=T0)
    db.commit()
    for _ in range(4):
        with pytest.raises(ProblemError) as e:
            pin.check_pin(db, "000000", now=T0)
        assert e.value.status == 401
    with pytest.raises(ProblemError) as e:
        pin.check_pin(db, "000000", now=T0)
    assert e.value.status == 429 and e.value.headers["Retry-After"] == "300"
    with pytest.raises(ProblemError) as e:
        pin.check_pin(db, "246810", now=T0 + timedelta(seconds=299, milliseconds=500))
    assert e.value.status == 429 and e.value.headers["Retry-After"] == "1"


@pytest.mark.parametrize("bad", [1234, 246810, ["246810"], {"a": 1}, b"246810", 24.6])
def test_check_pin_non_string_input_is_plain_failure_not_crash(db, bad):
    """TC-VA-178 [S-W08] 문자열이 아닌 PIN 값(정수·목록·바이트 등)은 500 이 아니라 일반 실패(401)로 처리되고 실패 횟수에 반영된다."""
    from ytweb.core import pin
    from ytweb.core.errors import ProblemError
    pin.set_pin(db, "246810", now=T0)
    with pytest.raises(ProblemError) as e:
        pin.check_pin(db, bad, now=T0)
    assert e.value.status == 401 and e.value.code == "pin_invalid"
    assert pin._fail_state(db)["count"] == 1


def test_pin_hash_with_other_scheme_label_never_verifies():
    """TC-VA-179 [S-W08] 저장 해시의 방식 표지가 scrypt 가 아니면(나머지 값이 정상이어도) 검증 실패 — 방식 혼동 방지."""
    from ytweb.core import pin
    good = pin.hash_pin("246810")
    assert pin.verify_pin_hash("246810", good) is True
    assert pin.verify_pin_hash("246810", good.replace("scrypt$", "md5$", 1)) is False
    assert pin.verify_pin_hash("246810", good.replace("scrypt$", "SCRYPT$", 1)) is False


def test_audit_session_target_is_truncated_id_not_full_hash(client, csrf, factory):
    """TC-VA-180 [S-W08, S-W16] 감사 로그의 세션 대상 식별자는 12자 접두사뿐이다(세션 해시 전체가 감사에 남지 않는다)."""
    from sqlalchemy import select

    from ytweb.db.models import AuditLog, SessionRow
    with factory() as s:
        sid = s.execute(select(SessionRow.id)).scalar_one()
        rows = s.execute(select(AuditLog).where(AuditLog.action == "session.create")).scalars().all()
    assert len(rows) == 1 and rows[0].target_id == sid[:12] and len(rows[0].target_id) == 12
    assert sid not in str(rows[0].detail)


def test_docs_enabled_exposes_only_docs_and_openapi(web_settings, engine, clock):
    """TC-VA-181 [S-W04] enable_docs=True(개발 프로필)에서만 /docs·/openapi.json 이 열리고 /redoc 는 계속 닫혀 있다. Host 검증은 여전히 적용."""
    from dataclasses import replace
    app = create_app(replace(web_settings, enable_docs=True), clock=clock, router_modules=["ytweb.routers.health"])
    h = [("host", "127.0.0.1:8080")]
    assert asgi_call(app, "GET", "/docs", h)["status"] == 200
    assert asgi_call(app, "GET", "/openapi.json", h)["status"] == 200
    assert asgi_call(app, "GET", "/redoc", h)["status"] == 404
    assert asgi_call(app, "GET", "/docs", [("host", "evil.com")])["status"] == 403
