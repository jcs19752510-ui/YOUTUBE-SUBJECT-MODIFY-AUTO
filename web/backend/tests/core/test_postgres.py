"""PostgreSQL 전용 동작(YTWEB_TEST_PG_URL 이 없으면 건너뜀). 이 DB 의 public 스키마를 지우고 다시 만든다(일회용 테스트 DB 전용)."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from ytweb import migrate
from ytweb.core import audit, jobs
from ytweb.db.models import AuditLog, Base, Job

pytestmark = pytest.mark.postgres
T0 = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)
APP_ROLE = "ytweb_app"


def _reset(url: str) -> None:
    eng = create_engine(url, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        # 앞선 테스트가 남긴 열린 트랜잭션이 DROP 을 막지 않도록 이 DB 의 다른 접속을 끊는다.
        c.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()"))
        c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    eng.dispose()


@pytest.fixture
def pg(pg_url):
    _reset(pg_url)
    migrate.upgrade(pg_url)
    eng = create_engine(pg_url, pool_size=5)
    yield eng
    eng.dispose()
    _reset(pg_url)


def test_alembic_upgrade_head_creates_all_model_tables(pg):
    """TC-WA-147 실제 PostgreSQL 에 `alembic upgrade head` 가 적용되고 모델의 모든 테이블이 생긴다."""
    names = set(inspect(pg).get_table_names())
    assert set(Base.metadata.tables) <= names and "alembic_version" in names
    with pg.connect() as c:
        assert c.execute(text("select version_num from alembic_version")).scalar_one() == "0002"


def test_migrated_schema_matches_models_columns(pg):
    """TC-WA-148 마이그레이션 결과의 컬럼 이름이 모델과 일치(드리프트 점검)."""
    insp = inspect(pg)
    for t in Base.metadata.sorted_tables:
        assert {c["name"] for c in insp.get_columns(t.name)} == {c.name for c in t.columns}, t.name


def test_downgrade_drops_everything(pg_url, pg):
    """TC-WA-149 downgrade base 가 모든 테이블을 지운다."""
    command.downgrade(migrate.alembic_config(pg_url), "base")
    assert set(inspect(pg).get_table_names()) - {"alembic_version"} == set()


def test_partial_unique_index_one_planned_change_per_video(pg):
    """TC-WA-150 같은 영상에 planned 변경 2개는 거부, success 가 섞이는 것은 허용."""
    s = sessionmaker(pg)()
    s.execute(text("INSERT INTO videos (video_id,title,snippet,exclusion_reasons,source,fetched_at,is_short) VALUES ('v1','t','{}','[]','demo',now(),false)"))
    ins = "INSERT INTO changes (video_id,change_type,previous_title,new_title,result,mode,created_at) VALUES ('v1','apply','a','b',:r,'demo',now())"
    s.execute(text(ins), {"r": "planned"})
    s.execute(text(ins), {"r": "success"})
    s.execute(text(ins), {"r": "success"})
    s.commit()
    with pytest.raises(IntegrityError):
        s.execute(text(ins), {"r": "planned"})
        s.commit()
    s.rollback()


def test_partial_unique_index_active_batch_item_per_suggestion(pg):
    """TC-WA-151 한 제안이 pending/running 항목을 동시에 2개 가질 수 없다(완료 후에는 가능)."""
    s = sessionmaker(pg)()
    s.execute(text("INSERT INTO videos (video_id,title,snippet,exclusion_reasons,source,fetched_at,is_short) VALUES ('v1','t','{}','[]','demo',now(),false)"))
    s.execute(text("INSERT INTO suggestions (video_id,title,source,strict_mode,validation_reasons,status,created_at,updated_at) VALUES ('v1','n','manual',false,'[]','approved',now(),now())"))
    for _ in range(2):
        s.execute(text("INSERT INTO batches (status,created_at,updated_at) VALUES ('draft',now(),now())"))
    sid = s.execute(text("select id from suggestions")).scalar_one()
    bids = [r[0] for r in s.execute(text("select id from batches order by id"))]
    ins = "INSERT INTO batch_items (batch_id,suggestion_id,video_id,seq,status,updated_at) VALUES (:b,:s,'v1',1,:st,now())"
    s.execute(text(ins), {"b": bids[0], "s": sid, "st": "pending"})
    s.commit()
    with pytest.raises(IntegrityError):
        s.execute(text(ins), {"b": bids[1], "s": sid, "st": "running"})
        s.commit()
    s.rollback()
    s.execute(text("UPDATE batch_items SET status='success'"))
    s.execute(text(ins), {"b": bids[1], "s": sid, "st": "pending"})
    s.commit()


def test_skip_locked_claim_gives_different_jobs_to_concurrent_workers(pg):
    """TC-WA-152 FOR UPDATE SKIP LOCKED: 한 트랜잭션이 잠근 작업을 다른 워커는 건너뛰고 다음 작업을 가져간다."""
    f = sessionmaker(pg, expire_on_commit=False, autoflush=False)
    with f() as s:
        a = jobs.enqueue(s, type="t", payload={}, now=T0).id
        b = jobs.enqueue(s, type="t", payload={}, now=T0 + timedelta(seconds=1)).id
        s.commit()
    s1, s2 = f(), f()
    try:
        j1 = jobs.claim(s1, worker_id="w1", now=T0 + timedelta(minutes=1))  # 커밋 전: 행 잠금 유지
        j2 = jobs.claim(s2, worker_id="w2", now=T0 + timedelta(minutes=1))
        assert {j1.id, j2.id} == {a, b} and j1.id != j2.id
        s1.commit()
        s2.commit()
        with f() as s3:
            assert jobs.claim(s3, worker_id="w3", now=T0 + timedelta(minutes=1)) is None
    finally:
        s1.close()
        s2.close()


def test_skip_locked_present_in_emitted_sql(pg):
    """TC-WA-153 PostgreSQL 에서 claim 이 실제로 FOR UPDATE SKIP LOCKED 를 내보낸다."""
    from sqlalchemy import event
    seen: list[str] = []
    event.listen(pg, "before_cursor_execute", lambda conn, cur, stmt, *a: seen.append(stmt))
    with sessionmaker(pg)() as s:
        jobs.claim(s, worker_id="w", now=T0)
        s.rollback()
    assert any("FOR UPDATE SKIP LOCKED" in q for q in seen)


def test_concurrent_claims_never_double_assign(pg):
    """TC-WA-154 스레드 8개가 동시에 claim 해도 같은 작업을 두 번 가져가지 않는다."""
    f = sessionmaker(pg, expire_on_commit=False, autoflush=False)
    with f() as s:
        ids = {jobs.enqueue(s, type="t", payload={"i": i}, now=T0).id for i in range(20)}
        s.commit()
    got: list[str] = []
    lock = threading.Lock()

    def work(n):
        while True:
            with f() as s:
                j = jobs.claim(s, worker_id=f"w{n}", now=T0 + timedelta(minutes=1))
                s.commit()
            if j is None:
                return
            with lock:
                got.append(j.id)

    ts = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(got) == sorted(ids)
    with f() as s:
        assert s.execute(select(Job).where(Job.status == "running")).scalars().all().__len__() == 20


def test_concurrent_audit_writes_keep_chain_valid(pg):
    """TC-WA-155 여러 스레드가 동시에 감사 기록을 남겨도 해시 체인이 갈라지지 않는다(advisory lock)."""
    f = sessionmaker(pg, expire_on_commit=False, autoflush=False)

    def work(n):
        for i in range(10):
            with f() as s:
                audit.record(s, actor="o", action="t.c", detail={"n": n, "i": i}, now=T0 + timedelta(milliseconds=n * 100 + i))
                s.commit()

    ts = [threading.Thread(target=work, args=(n,)) for n in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    with f() as s:
        assert s.execute(select(text("count(*)")).select_from(AuditLog)).scalar_one() == 50
        assert audit.verify_chain(s) is True


def test_app_role_cannot_update_or_delete_audit_log(pg_url):
    """TC-WA-156 ytweb_app 역할은 audit_log 에 INSERT/SELECT 만 가능, UPDATE/DELETE/TRUNCATE 는 권한 거부(다른 테이블 UPDATE 는 가능)."""
    _reset(pg_url)
    su = create_engine(pg_url, isolation_level="AUTOCOMMIT")
    created = False
    with su.connect() as c:
        if not c.execute(text("select 1 from pg_roles where rolname=:r"), {"r": APP_ROLE}).first():
            c.execute(text(f"CREATE ROLE {APP_ROLE} NOLOGIN"))
            created = True
        c.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        c.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {APP_ROLE}"))
        c.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"))
    try:
        migrate.upgrade(pg_url)
        with su.connect() as c:
            c.execute(text(f"SET ROLE {APP_ROLE}"))
            c.execute(text("INSERT INTO audit_log (ts,actor,action,detail,prev_hash,hash) VALUES (now(),'o','a','{}',:p,:h)"), {"p": "0" * 64, "h": "1" * 64})
            assert c.execute(text("select count(*) from audit_log")).scalar_one() == 1
            for stmt in ("UPDATE audit_log SET actor='x'", "DELETE FROM audit_log", "TRUNCATE audit_log"):
                with pytest.raises(ProgrammingError) as e:
                    c.execute(text(stmt))
                assert "permission denied" in str(e.value)
            c.execute(text("INSERT INTO settings_kv (key,value,updated_at) VALUES ('k','1',now())"))
            c.execute(text("UPDATE settings_kv SET value='2'"))
    finally:
        su.dispose()
        _reset(pg_url)  # 다른 접속을 끊으므로 정리용 엔진은 새로 만든다
        cleanup = create_engine(pg_url, isolation_level="AUTOCOMMIT")
        with cleanup.connect() as c:
            c.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {APP_ROLE}"))
            c.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {APP_ROLE}"))
            if created:
                c.execute(text(f"DROP OWNED BY {APP_ROLE}"))
                c.execute(text(f"DROP ROLE {APP_ROLE}"))
        cleanup.dispose()


def test_migration_works_without_app_role(pg_url):
    """TC-WA-157 ytweb_app 역할이 없는 DB 에서도 마이그레이션이 실패하지 않는다(REVOKE 는 역할이 있을 때만)."""
    with create_engine(pg_url, isolation_level="AUTOCOMMIT").connect() as c:
        if c.execute(text("select 1 from pg_roles where rolname=:r"), {"r": APP_ROLE}).first():
            pytest.skip("ytweb_app 역할이 클러스터에 이미 있어 '역할 없음' 경로를 검증할 수 없음")
    _reset(pg_url)
    migrate.upgrade(pg_url)
    _reset(pg_url)
