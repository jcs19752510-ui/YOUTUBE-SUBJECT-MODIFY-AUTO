"""감사 로그 변조: alembic 적용 + 앱 전용 계정(ytweb_app)으로 UPDATE/DELETE/TRUNCATE 시도, 해시 체인 검증. DB ytweb_test_f 만."""
import pathlib, datetime as dt
import pytest, psycopg
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from ytweb.core import audit

BACKEND = pathlib.Path(__file__).resolve().parents[2] / "backend"
GUARD = BACKEND.parent / "docker" / "db" / "audit-guard.sql"
GRANTS = BACKEND.parent / "docker" / "db" / "schema-grants.sql"
HOST = "host=127.0.0.1 port=54329 dbname=ytweb_test_f"
SU = f"postgresql+psycopg://postgres@127.0.0.1:54329/ytweb_test_f"
OWN = f"postgresql+psycopg://ytweb_owner:ow@127.0.0.1:54329/ytweb_test_f"
APP = f"postgresql+psycopg://ytweb_app:ap@127.0.0.1:54329/ytweb_test_f"

@pytest.fixture(scope="module")
def pg():
    su = create_engine(SU, isolation_level="AUTOCOMMIT")
    with su.connect() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        c.execute(text("CREATE ROLE ytweb_owner LOGIN PASSWORD 'ow'"))
        c.execute(text("CREATE ROLE ytweb_app LOGIN PASSWORD 'ap'"))
        c.execute(text("GRANT ALL ON DATABASE ytweb_test_f TO ytweb_owner"))
        c.execute(text("GRANT CONNECT ON DATABASE ytweb_test_f TO ytweb_app"))
    raw = psycopg.connect("host=127.0.0.1 port=54329 dbname=ytweb_test_f user=postgres", autocommit=True)
    raw.execute(GRANTS.read_text())
    cfg = Config(str(BACKEND / "alembic.ini")); cfg.set_main_option("script_location", str(BACKEND / "alembic")); cfg.attributes["url"] = OWN
    command.upgrade(cfg, "head")
    yield
    raw2 = psycopg.connect("host=127.0.0.1 port=54329 dbname=ytweb_test_f user=postgres", autocommit=True)
    raw2.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    raw2.execute("DROP OWNED BY ytweb_app; DROP OWNED BY ytweb_owner; DROP ROLE ytweb_app; DROP ROLE ytweb_owner")

def now(): return dt.datetime(2026, 10, 12, 1, 0, tzinfo=dt.timezone.utc)

def seed(n=4):
    e = create_engine(APP)
    with Session(e) as s:
        for i in range(n):
            audit.record(s, actor="owner", action=f"t.{i}", target_type="x", target_id=str(i), detail={"i": i}, now=now()); s.commit()
    return e

def test_app_can_insert_and_chain_verifies(pg):
    e = seed()
    with Session(e) as s: assert audit.verify_chain(s) is True

@pytest.mark.parametrize("sql", ["UPDATE audit_log SET actor='evil'", "UPDATE audit_log SET hash='0'", "DELETE FROM audit_log", "DELETE FROM audit_log WHERE id=1",
    "TRUNCATE audit_log", "UPDATE alembic_version SET version_num='x'", "DELETE FROM alembic_version", "INSERT INTO alembic_version VALUES ('x')",
    "DROP TABLE audit_log", "ALTER TABLE audit_log DISABLE TRIGGER ALL", "CREATE TABLE zzz(a int)", ])
def test_app_account_cannot_tamper(pg, sql):
    e = create_engine(APP)
    with e.connect() as c:
        with pytest.raises(Exception) as ei:
            c.execute(text(sql)); c.commit()
        print(sql, "->", type(ei.value).__name__, str(ei.value).splitlines()[0][:90])

def test_app_grant_has_no_effect(pg):
    e = create_engine(APP)
    with e.connect() as c:
        try: c.execute(text("GRANT UPDATE, DELETE ON audit_log TO ytweb_app")); c.commit()
        except Exception as ex: print("grant raised", type(ex).__name__)
        assert c.execute(text("select has_table_privilege('ytweb_app','audit_log','UPDATE') or has_table_privilege('ytweb_app','audit_log','DELETE')")).scalar() is False

def test_chain_detects_tamper_by_owner_and_deletion(pg):
    e = seed(1)
    own = create_engine(OWN, isolation_level="AUTOCOMMIT")
    with Session(e) as s: assert audit.verify_chain(s)
    with own.connect() as c:
        c.execute(text("UPDATE audit_log SET actor='evil' WHERE id=(SELECT min(id)+1 FROM audit_log)"))
    with Session(e) as s: assert audit.verify_chain(s) is False, "행 변조 미탐지"
    # 복구 후 중간 행 삭제 탐지
    with own.connect() as c:
        c.execute(text("UPDATE audit_log SET actor='owner' WHERE actor='evil'"))
    with Session(e) as s: assert audit.verify_chain(s) is True
    with own.connect() as c:
        c.execute(text("DELETE FROM audit_log WHERE id=(SELECT min(id)+1 FROM audit_log)"))
    with Session(e) as s: assert audit.verify_chain(s) is False, "중간 행 삭제 미탐지"

def test_tail_truncation_not_detected_known_limit(pg):
    """꼬리 행 삭제는 해시 체인만으로는 탐지 불가(앵커 없음) — 소유자 권한이 필요한 공격이라 참고 기록."""
    own = create_engine(OWN, isolation_level="AUTOCOMMIT")
    with own.connect() as c: c.execute(text("TRUNCATE audit_log"))
    e = seed(2)
    with Session(e) as s: assert audit.verify_chain(s) is True
    with own.connect() as c:
        c.execute(text("DELETE FROM audit_log WHERE id=(SELECT max(id) FROM audit_log)"))
    with Session(e) as s: r = audit.verify_chain(s)
    print("tail delete detected?", not r)
    assert r is True   # 한계 확인(탐지 안 됨) - 결함 후보 Low/Info

def test_guard_sql_restores_revoke_after_grant(pg):
    su = psycopg.connect("host=127.0.0.1 port=54329 dbname=ytweb_test_f user=ytweb_owner password=ow", autocommit=True)
    su.execute("GRANT UPDATE, DELETE ON audit_log TO ytweb_app")
    e = create_engine(APP)
    with e.connect() as c:
        c.execute(text("UPDATE audit_log SET actor=actor WHERE id=-1")); c.commit()      # 권한 부여 상태 = 통과(전제 확인)
    su.execute(GUARD.read_text())
    with e.connect() as c:
        with pytest.raises(Exception): c.execute(text("UPDATE audit_log SET actor=actor WHERE id=-1")); c.commit()
