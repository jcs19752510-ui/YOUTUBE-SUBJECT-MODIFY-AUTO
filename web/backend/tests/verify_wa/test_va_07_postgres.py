"""독립 점검 7: PostgreSQL 16 실제 적용 — Alembic DDL 과 모델 일치, 최소 권한 역할, 동시성 (S-W12, S-W13a, S-W16).

PG 테스트는 대상 DB 의 public 스키마를 지우고 다시 만든다(YTWEB_TEST_PG_URL 은 일회용 DB 여야 한다).
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from ytweb import migrate
from ytweb.core import audit, jobs
from ytweb.core.errors import ProblemError
from ytweb.core.idempotency import run_idempotent
from ytweb.core.pin import check_pin, set_pin
from ytweb.db.models import AuditLog, Base, Job

pytestmark = pytest.mark.postgres
T0 = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)
APP_ROLE = "ytweb_app"


def _reset(url: str) -> None:
    eng = create_engine(url, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()"))
        c.execute(text("DROP SCHEMA IF EXISTS model_ref CASCADE"))
        c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    eng.dispose()


@pytest.fixture
def pg(pg_url):
    _reset(pg_url)
    migrate.upgrade(pg_url)
    eng = create_engine(pg_url, pool_size=10, max_overflow=10)
    yield eng
    eng.dispose()
    _reset(pg_url)


@pytest.fixture
def app_role(pg_url):
    """ytweb_app 역할을 (없으면) 만들고 인프라(schema-grants.sql)와 같은 기본 권한을 준다. 우리가 만든 경우에만 지운다."""
    _reset(pg_url)
    su = create_engine(pg_url, isolation_level="AUTOCOMMIT")
    created = False
    with su.connect() as c:
        if not c.execute(text("select 1 from pg_roles where rolname=:r"), {"r": APP_ROLE}).first():
            c.execute(text(f"CREATE ROLE {APP_ROLE} NOLOGIN"))
            created = True
        c.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        c.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"))
        c.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"))
    migrate.upgrade(pg_url)
    yield su
    su.dispose()
    _reset(pg_url)
    cl = create_engine(pg_url, isolation_level="AUTOCOMMIT")
    with cl.connect() as c:
        c.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {APP_ROLE}"))
        c.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {APP_ROLE}"))
        if created:
            c.execute(text(f"DROP OWNED BY {APP_ROLE}"))
            c.execute(text(f"DROP ROLE {APP_ROLE}"))
    cl.dispose()


# ---------------------------------------------------------------- Alembic 0001 == models.py

def _snapshot(conn, schema: str) -> dict:
    pat = f"{schema}\\."
    cols = conn.execute(text("""
        select table_name, column_name, data_type, udt_name, coalesce(character_maximum_length, -1), is_nullable,
               regexp_replace(coalesce(column_default, ''), :pat, '', 'g')
        from information_schema.columns where table_schema = :s and table_name <> 'alembic_version' order by 1, 2"""),
        {"s": schema, "pat": pat}).fetchall()
    idx = conn.execute(text("""
        select tablename, indexname, regexp_replace(indexdef, :pat, '', 'g') from pg_indexes
        where schemaname = :s and tablename <> 'alembic_version' order by 1, 2"""), {"s": schema, "pat": pat}).fetchall()
    con = conn.execute(text("""
        select cl.relname, c.conname, c.contype::text, regexp_replace(pg_get_constraintdef(c.oid), :pat, '', 'g')
        from pg_constraint c join pg_class cl on cl.oid = c.conrelid join pg_namespace n on n.oid = cl.relnamespace
        where n.nspname = :s and cl.relname <> 'alembic_version' order by 1, 2"""), {"s": schema, "pat": pat}).fetchall()
    seq = conn.execute(text("select sequencename from pg_sequences where schemaname = :s order by 1"), {"s": schema}).fetchall()
    return {"columns": [tuple(r) for r in cols], "indexes": [tuple(r) for r in idx],
            "constraints": [tuple(r) for r in con], "sequences": [tuple(r) for r in seq]}


@pytest.fixture
def both_schemas(pg):
    """public 에는 Alembic 결과가, model_ref 에는 models.py 에서 직접 만든(create_all) 스키마가 있다."""
    with pg.begin() as c:
        c.execute(text("CREATE SCHEMA model_ref"))
    with pg.connect().execution_options(schema_translate_map={None: "model_ref"}) as c:
        Base.metadata.create_all(c)
        c.commit()
    with pg.connect() as c:
        yield _snapshot(c, "public"), _snapshot(c, "model_ref")


@pytest.mark.parametrize("part", ["columns", "indexes", "constraints", "sequences"])
def test_alembic_0001_matches_models_py(both_schemas, part):
    """TC-VA-114 [S-W13a, S-W12] Alembic 0001 이 만든 실제 PG 스키마의 컬럼(타입·길이·NULL·기본값)/인덱스(부분 조건 포함)/제약(CHECK·FK·UNIQUE·PK)/시퀀스가 models.py 에서 직접 생성한 스키마와 항목별로 같다."""
    mig, mod = both_schemas
    assert mig[part], "비교 대상이 비어 있음"
    only_mig = [x for x in mig[part] if x not in mod[part]]
    only_mod = [x for x in mod[part] if x not in mig[part]]
    assert not only_mig and not only_mod, {"alembic에만": only_mig, "모델에만": only_mod}


def test_alembic_table_set_equals_model_tables_plus_version(both_schemas, pg):
    """TC-VA-115 [S-W13a] 테이블 집합이 모델 14개와 일치하고(alembic_version 제외) 누락/잉여 테이블이 없다."""
    mig, mod = both_schemas
    t_mig = {r[0] for r in mig["columns"]}
    assert t_mig == {t.name for t in Base.metadata.sorted_tables} == {r[0] for r in mod["columns"]}
    assert len(t_mig) == 14


def test_upgrade_twice_and_downgrade_upgrade_cycle_are_safe(pg_url, pg):
    """TC-VA-116 [S-W13a] upgrade head 를 한 번 더 실행해도 변화 없음, downgrade base 후 다시 upgrade 해도 성공하고 버전은 0001."""
    from alembic import command
    migrate.upgrade(pg_url)
    with pg.connect() as c:
        assert c.execute(text("select version_num from alembic_version")).scalar_one() == "0001"
    command.downgrade(migrate.alembic_config(pg_url), "base")
    with pg.connect() as c:
        left = c.execute(text("select count(*) from information_schema.tables where table_schema='public' and table_name <> 'alembic_version'")).scalar_one()
    assert left == 0
    migrate.upgrade(pg_url)
    with pg.connect() as c:
        assert c.execute(text("select count(*) from information_schema.tables where table_schema='public'")).scalar_one() == 15


def test_check_constraints_and_partial_unique_indexes_actually_reject_bad_rows(pg):
    """TC-VA-117 [S-W12] 실제 DB 가 CHECK(상태 열거)와 audit_log hash UNIQUE 를 강제한다."""
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        with pg.begin() as c:
            c.execute(text("insert into jobs(id,type,status,payload,progress,total,attempts,run_after,created_at) values ('x','t','bogus','{}',0,0,0,now(),now())"))
    with pytest.raises(IntegrityError):
        with pg.begin() as c:
            for _ in range(2):
                c.execute(text("insert into audit_log(ts,actor,action,detail,prev_hash,hash) values (now(),'a','b','{}',:p,:h)"), {"p": "0" * 64, "h": "1" * 64})


# ---------------------------------------------------------------- 최소 권한 역할

def _as_app(su, stmts_ok=(), stmts_denied=()):
    with su.connect() as c:
        c.execute(text(f"SET ROLE {APP_ROLE}"))
        for s in stmts_ok:
            c.execute(text(s))
        denied = []
        for s in stmts_denied:
            try:
                c.execute(text(s))
            except Exception as e:  # noqa: BLE001
                denied.append((s, "permission denied" in str(e) or "must be owner" in str(e)))
                c.rollback()
                c.execute(text(f"SET ROLE {APP_ROLE}"))
            else:
                denied.append((s, False))
        c.rollback()
        c.execute(text("RESET ROLE"))  # 풀에 돌아가는 접속에 SET ROLE 이 남지 않게 한다
    return denied


def test_app_role_audit_log_is_append_only_and_other_tables_dml_allowed(app_role):
    """TC-VA-118 [S-W16, S-W13a] ytweb_app: audit_log 는 INSERT/SELECT 만(UPDATE·DELETE·TRUNCATE·SELECT FOR UPDATE 거부, 꼬리 행 삭제 포함), 다른 테이블은 INSERT/UPDATE/DELETE 가능, DDL·권한 부여·트리거 조작은 모두 거부."""
    su = app_role
    ins = "INSERT INTO audit_log (ts,actor,action,detail,prev_hash,hash) VALUES (now(),'o','a','{}','%s','%s')" % ("0" * 64, "1" * 64)
    with su.connect() as c:
        c.execute(text(f"SET ROLE {APP_ROLE}"))
        c.execute(text(ins))
        assert c.execute(text("select count(*) from audit_log")).scalar_one() == 1
        # 다른 테이블 DML 허용(세션/설정/멱등성/잡)
        c.execute(text("insert into sessions(id,csrf_token,created_at,expires_at,last_seen) values ('s','c',now(),now(),now())"))
        c.execute(text("update sessions set csrf_token='d'"))
        c.execute(text("delete from sessions"))
        c.execute(text("insert into settings_kv(key,value,updated_at) values ('k','1',now())"))
        c.execute(text("update settings_kv set value='2'"))
        c.execute(text("insert into idempotency_keys(key,route,request_hash,created_at) values ('abcdefgh','r','h',now())"))
        c.execute(text("delete from idempotency_keys"))
        c.execute(text("insert into jobs(id,type,status,payload,progress,total,attempts,run_after,created_at) values ('j','t','queued','{}',0,0,0,now(),now())"))
        c.execute(text("select id from jobs where status='queued' order by run_after limit 1 for update skip locked"))
        c.commit()
        c.execute(text("RESET ROLE"))
    denied = _as_app(su, stmts_denied=[
        "UPDATE audit_log SET actor='x'", "DELETE FROM audit_log", "DELETE FROM audit_log WHERE id = (SELECT max(id) FROM audit_log)",
        "TRUNCATE audit_log", "SELECT * FROM audit_log FOR UPDATE",
        "DROP TABLE audit_log", "ALTER TABLE audit_log ADD COLUMN z int", "ALTER TABLE audit_log DISABLE TRIGGER ALL",
        "CREATE TABLE zzz_new(a int)", "ALTER TABLE audit_log OWNER TO ytweb_app",
        "CREATE TRIGGER t BEFORE INSERT ON audit_log FOR EACH ROW EXECUTE FUNCTION pg_catalog.suppress_redundant_updates_trigger()",
        "DROP TABLE sessions", "TRUNCATE sessions",
    ])
    bad = [s for s, ok in denied if not ok]
    assert not bad, bad
    with su.connect() as c:
        c.execute(text(f"SET ROLE {APP_ROLE}"))
        c.execute(text("GRANT UPDATE ON audit_log TO ytweb_app"))  # 소유자가 아니므로 경고만 나고 효과가 없다
        c.execute(text("RESET ROLE"))
        assert not c.execute(text("select has_table_privilege(:r,'audit_log','UPDATE') or has_table_privilege(:r,'audit_log','DELETE') or has_table_privilege(:r,'audit_log','TRUNCATE')"), {"r": APP_ROLE}).scalar_one()
        assert c.execute(text("select count(*) from audit_log")).scalar_one() == 1  # 거부된 문장은 행을 건드리지 못했다
        assert c.execute(text("select rolsuper, rolcreaterole, rolcreatedb, rolbypassrls from pg_roles where rolname=:r"), {"r": APP_ROLE}).one() == (False, False, False, False)
        assert not c.execute(text("select pg_has_role(:r, current_user, 'member')"), {"r": APP_ROLE}).scalar_one()  # 앱 역할은 소유자 역할의 구성원이 아니다
        assert c.execute(text("select count(*) from pg_tables where schemaname='public' and tableowner = :r"), {"r": APP_ROLE}).scalar_one() == 0


def test_whole_application_runs_end_to_end_as_least_privilege_role(app_role, pg_url, clock, fake_time):
    """TC-VA-119 [S-W16, S-W13a] 앱 전체 흐름(로그인·PIN·설정·감사 체인·잡 큐·멱등성)이 실제로 ytweb_app 권한(options=-c role)으로 동작하고 chain_ok 가 true 다."""
    from fastapi.testclient import TestClient
    from tests.conftest import CORE_ROUTERS, ORIGIN
    from tests.verify_wa.helpers import hdr
    from ytweb.app import create_app
    from ytweb.config import WebSettings
    from ytweb.core.ratelimit import RateLimits
    from pathlib import Path
    from tests.conftest import REPO_ROOT
    url = make_url(pg_url).update_query_string("options=-c role=" + APP_ROLE).render_as_string(hide_password=False)
    ws = WebSettings(mode="demo", database_url=url, base_dir=REPO_ROOT, secrets_dir=Path("/tmp/none"),
                     allowed_hosts=("127.0.0.1:8080", "localhost:8080"))
    app = create_app(ws, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time,
                     rate_limits=RateLimits(global_per_min=10_000, write_per_min=10_000, auth_per_min=10_000))
    with TestClient(app, base_url=ORIGIN) as c:
        r = c.post("/api/v1/auth/session", headers={"Origin": ORIGIN})
        assert r.status_code == 200, r.text
        csrf = r.json()["csrf_token"]
        assert c.patch("/api/v1/settings", json={"daily_apply_cap": 6, "tone": ["a"]}, headers=hdr(csrf)).status_code == 200
        assert c.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "2468"}}, headers=hdr(csrf)).status_code == 200
        r2 = c.get("/api/v1/audit").json()
        assert r2["chain_ok"] is True and r2["total"] == 3
        assert c.delete("/api/v1/auth/session", headers=hdr(csrf)).status_code == 204
        assert c.post("/api/v1/auth/session", json={"pin": "0000"}, headers={"Origin": ORIGIN}).status_code == 401
    f = sessionmaker(create_engine(url), expire_on_commit=False, autoflush=False)
    with f() as s:
        j = jobs.enqueue(s, type="t", payload={}, now=T0)
        k = run_idempotent(s, key="pg-app-role-1", route="r", request={"a": 1}, now=T0, handler=lambda: (201, {"ok": True}))
        s.commit()
        assert k == (201, {"ok": True})
        assert jobs.claim(s, worker_id="w", now=T0).id == j.id
        s.commit()
        assert audit.verify_chain(s) is True


def test_grants_given_after_migration_would_undo_revoke_documented_dependency(app_role, pg_url):
    """TC-VA-120 [S-W16] (특성화) 0001 의 REVOKE 는 '마이그레이션 시점'의 권한만 회수한다: 이후 인프라가 GRANT ALL ON ALL TABLES 를 하면 audit_log UPDATE 가 다시 열린다 -> 복원 뒤 audit-guard.sql 로 재회수해야 한다는 운영 의존성."""
    su = app_role
    with su.connect() as c:
        c.execute(text(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))
    d = _as_app(su, stmts_denied=["UPDATE audit_log SET actor='x'"])
    assert d == [("UPDATE audit_log SET actor='x'", False)]  # 거부되지 않음(= 의존성 확인)
    guard = (migrate.BACKEND_DIR.parent / "docker" / "db" / "audit-guard.sql").read_text(encoding="utf-8")
    with su.connect() as c:
        c.execute(text(guard.replace(":", "\\:")))
    d = _as_app(su, stmts_denied=["UPDATE audit_log SET actor='x'", "DELETE FROM audit_log", "TRUNCATE audit_log"])
    assert all(ok for _, ok in d), d


# ---------------------------------------------------------------- JSONB 왕복과 해시 체인

FLOATS = [1.0, 0.1, 100.0, 1e-7, 123456789.125, 1e15, 2**70, -5, 3.14159, True, None, "s", [1, 2.5], {"n": {"m": 0.5}}]


@pytest.mark.parametrize("val", FLOATS, ids=repr)
def test_jsonb_roundtrip_keeps_chain_valid_for_ordinary_values(pg, val):
    """TC-VA-121 [S-W16] JSONB 에 저장했다 읽어도 일반적인 detail 값(정수·소수·불리언·null·중첩)의 해시가 유지되어 체인이 유효하다."""
    f = sessionmaker(pg, expire_on_commit=False, autoflush=False)
    with f() as s:
        audit.record(s, actor="o", action="a", detail={"v": val}, now=T0)
        audit.record(s, actor="o", action="b", detail={"v": val}, now=T0 + timedelta(seconds=1))
        s.commit()
    with f() as s:
        assert audit.verify_chain(s) is True


@pytest.mark.parametrize("val", [1e22, 1e16, -0.0], ids=repr)
def test_jsonb_unstable_floats_rejected_before_chain_can_break(pg, val):
    """TC-VA-122 [S-W16] JSONB 가 정규화하는 float(지수 표기 큰 수, -0.0)는 기록 전에 거부되어 체인이 거짓 변조로 판정될 수 없다(DEF-6-008 수정 확인)."""
    f = sessionmaker(pg, expire_on_commit=False, autoflush=False)
    with f() as s:
        audit.record(s, actor="o", action="ok", detail={"v": 1}, now=T0)
        with pytest.raises(ValueError):
            audit.record(s, actor="o", action="a", detail={"nested": [{"v": val}]}, now=T0)
        s.commit()
    with f() as s:
        assert audit.verify_chain(s) is True


# ---------------------------------------------------------------- 동시성

def _factory(pg):
    return sessionmaker(pg, expire_on_commit=False, autoflush=False)


def test_idempotency_concurrent_same_key_runs_handler_once(pg):
    """TC-VA-123 [S-W12] 같은 Idempotency-Key 로 6개 스레드가 동시에 들어와도 핸들러는 정확히 1회 실행되고, 나머지는 409(처리 중) 또는 저장된 응답 재생이며 다른 예외는 없다."""
    f = _factory(pg)
    calls, results, errors = [], [], []
    lock = threading.Lock()
    start = threading.Barrier(6)

    def handler():
        with lock:
            calls.append(1)
        time.sleep(0.4)
        return 201, {"n": 1}

    def work():
        start.wait()
        with f() as s:
            try:
                r = run_idempotent(s, key="concurrent-key-1", route="r", request={"a": 1}, now=T0, handler=handler)
                s.commit()
                with lock:
                    results.append(r)
            except ProblemError as e:
                s.rollback()
                with lock:
                    errors.append((e.status, e.code))
            except Exception as e:  # noqa: BLE001
                with lock:
                    errors.append(("unexpected", repr(e)))

    ts = [threading.Thread(target=work) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(calls) == 1, calls
    assert results == [(201, {"n": 1})]
    assert all(e == (409, "idempotency_in_progress") for e in errors), errors
    assert len(errors) == 5
    with f() as s:  # 이제 재생
        assert run_idempotent(s, key="concurrent-key-1", route="r", request={"a": 1}, now=T0, handler=lambda: (500, {})) == (201, {"n": 1})


def test_queue_four_workers_each_job_executed_exactly_once(pg):
    """TC-VA-124 [S-W12] 워커 스레드 4개가 작업 40건을 process_next 로 동시에 처리해도 각 작업의 핸들러 실행은 정확히 1회이고 모두 succeeded 다."""
    f = _factory(pg)
    counts: dict[str, int] = {}
    lock = threading.Lock()

    def handler(factory, job):
        with lock:
            counts[job.id] = counts.get(job.id, 0) + 1
        time.sleep(0.005)
        return {"ok": 1}

    old = dict(jobs._HANDLERS)
    jobs.register_handler("t", handler)
    try:
        with f() as s:
            ids = {jobs.enqueue(s, type="t", payload={"i": i}, now=T0).id for i in range(40)}
            s.commit()

        def work(n):
            while jobs.process_next(f, worker_id=f"w{n}", clock=lambda: T0 + timedelta(minutes=1)):
                pass

        ts = [threading.Thread(target=work, args=(n,)) for n in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
    finally:
        jobs._HANDLERS.clear(); jobs._HANDLERS.update(old)
    assert set(counts) == ids and set(counts.values()) == {1}
    with f() as s:
        assert {r.status for r in s.query(Job).all()} == {"succeeded"}


def test_pin_lockout_holds_under_concurrent_guesses(pg):
    """TC-VA-125 [S-W08] 동시 PIN 추측: 8개 스레드가 동시에 틀린 PIN 을 보내도 잠금(5회)이 지켜져 401 응답은 4건을 넘지 않아야 한다(경쟁으로 잠금이 무력화되면 안 됨)."""
    f = _factory(pg)
    with f() as s:
        set_pin(s, "2468", now=T0)
        s.commit()
    outcomes = []
    lock = threading.Lock()
    start = threading.Barrier(8)

    def work():
        start.wait()
        with f() as s:
            try:
                check_pin(s, "0000", now=T0)
                res = "ok"
            except ProblemError as e:
                res = e.status
            with lock:
                outcomes.append(res)

    ts = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    n401 = outcomes.count(401)
    assert n401 <= 4, {"401": n401, "all": sorted(map(str, outcomes))}


def test_pin_lockout_holds_under_concurrent_http_logins(pg, pg_url, clock, fake_time):
    """TC-VA-126 [S-W08] HTTP 수준: 틀린 PIN 으로 10개 동시 로그인 요청을 보내도 401 은 4건을 넘지 않아야 한다(나머지는 429)."""
    from fastapi.testclient import TestClient
    from pathlib import Path
    from tests.conftest import CORE_ROUTERS, ORIGIN, REPO_ROOT
    from tests.verify_wa.helpers import hdr, login
    from ytweb.app import create_app
    from ytweb.config import WebSettings
    from ytweb.core.ratelimit import RateLimits
    ws = WebSettings(mode="demo", database_url=pg_url, base_dir=REPO_ROOT, secrets_dir=Path("/tmp/none"),
                     allowed_hosts=("127.0.0.1:8080", "localhost:8080"))
    app = create_app(ws, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time,
                     rate_limits=RateLimits(global_per_min=100_000, write_per_min=100_000, auth_per_min=100_000))
    with TestClient(app, base_url=ORIGIN) as c:
        csrf = login(c)
        assert c.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "2468"}}, headers=hdr(csrf)).status_code == 200
    codes, lock = [], threading.Lock()
    start = threading.Barrier(10)

    def work():
        tc = TestClient(app, base_url=ORIGIN)
        start.wait()
        r = tc.post("/api/v1/auth/session", json={"pin": "0000"}, headers={"Origin": ORIGIN})
        with lock:
            codes.append(r.status_code)

    ts = [threading.Thread(target=work) for _ in range(10)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert codes.count(401) <= 4, sorted(codes)


def test_claim_skips_row_locked_by_another_transaction_instead_of_blocking(pg):
    """TC-VA-142 [S-W12] 결정적 SKIP LOCKED 시험: 트랜잭션 A 가 첫 작업 행을 FOR UPDATE 로 잡고 있어도 워커 B 의 claim 은 막히지 않고 두 번째 작업을 가져간다(5초 안). 잠금 건너뛰기가 없으면 B 가 막히거나 아무것도 못 가져간다."""
    f = _factory(pg)
    with f() as s:
        first = jobs.enqueue(s, type="t", payload={}, now=T0).id
        second = jobs.enqueue(s, type="t", payload={}, now=T0 + timedelta(seconds=1)).id
        s.commit()
    holder = f()
    try:
        holder.execute(text("SELECT id FROM jobs WHERE id = :i FOR UPDATE"), {"i": first})  # 커밋하지 않고 행 잠금 유지
        box: dict = {}

        def work():
            with f() as s:
                s.execute(text("SET LOCAL lock_timeout = '4s'"))
                try:
                    j = jobs.claim(s, worker_id="B", now=T0 + timedelta(minutes=1))
                    box["id"] = j.id if j else None
                    s.commit()
                except Exception as e:  # noqa: BLE001
                    box["err"] = repr(e)

        t = threading.Thread(target=work)
        t0 = time.time()
        t.start(); t.join(timeout=8)
        assert not t.is_alive(), "claim 이 8초 넘게 막힘(SKIP LOCKED 미사용 추정)"
        assert box.get("id") == second, box
        assert time.time() - t0 < 3.5
    finally:
        holder.rollback(); holder.close()
    with f() as s:
        assert s.get(Job, first).status == "queued" and s.get(Job, second).status == "running"


def test_concurrent_audit_writers_keep_one_linear_chain(pg):
    """TC-VA-143 [S-W16, S-W12] 8개 스레드가 각각 10건씩 동시에 감사 기록을 남겨도 80행 모두 prev_hash 가 서로 달라 한 줄 체인이고 verify_chain 이 True 다(advisory lock)."""
    f = _factory(pg)
    start = threading.Barrier(8)
    errors: list = []

    def work(n):
        start.wait()
        for i in range(10):
            try:
                with f() as s:
                    audit.record(s, actor="t", action=f"a{n}", detail={"i": i}, now=T0 + timedelta(microseconds=n * 100 + i))
                    s.commit()
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

    ts = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors, errors[:3]
    with f() as s:
        rows = s.query(AuditLog).order_by(AuditLog.id).all()
        assert len(rows) == 80
        assert len({r.prev_hash for r in rows}) == 80, "체인이 갈라짐(같은 prev_hash 를 가진 행이 둘 이상)"
        assert audit.verify_chain(s) is True
