"""관리자 로그인 PostgreSQL 전용 시험(YTWEB_TEST_PG_URL 이 없으면 건너뜀): 0003 마이그레이션, 동시 추측 잠금."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import sessionmaker

from tests.core.test_postgres import pg  # noqa: F401  (픽스처 재사용: 스키마 초기화 + upgrade head)
from ytweb.core import admin_account
from ytweb.core.errors import ProblemError
from ytweb.db.models import AdminAccount

pytestmark = pytest.mark.postgres
T0 = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)
ID, PW = "testadmin", "Test-Passw0rd!"


def test_migration_0003_creates_admin_accounts_and_is_head(pg):  # noqa: F811
    """TC-AL-101 head 가 0003 이고 admin_accounts 표·컬럼이 모델과 같다."""
    assert "admin_accounts" in inspect(pg).get_table_names()
    assert {c["name"] for c in inspect(pg).get_columns("admin_accounts")} == {"login_id", "password_hash", "created_at", "updated_at", "last_login_at"}
    with pg.connect() as c:
        assert c.execute(text("select version_num from alembic_version")).scalar_one() == "0003"


def test_concurrent_wrong_guesses_cannot_bypass_lockout(pg, tmp_path):  # noqa: F811
    """TC-AL-102 동시에 20개 틀린 추측을 보내도 실제 비밀번호 검증은 4번(401)뿐이고 나머지는 잠금(429)."""
    factory = sessionmaker(pg)
    with factory() as db:
        admin_account.create_admin(db, ID, PW, now=T0)
        db.commit()
    codes: list[str] = []
    lock = threading.Lock()

    def attempt():
        with factory() as db:
            try:
                admin_account.authenticate(db, ID, "wrong-password-1", now=T0)
                code = "ok"
            except ProblemError as e:
                code = e.code
            db.commit()
        with lock:
            codes.append(code)

    ts = [threading.Thread(target=attempt) for _ in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert codes.count("login_invalid") == 4 and codes.count("login_locked") == 16 and "ok" not in codes
    with factory() as db:
        with pytest.raises(ProblemError) as ei:
            admin_account.authenticate(db, ID, PW, now=T0)  # 잠금 중에는 맞는 비밀번호도 거부
        assert ei.value.code == "login_locked"
        assert db.get(AdminAccount, ID) is not None


def test_concurrent_setup_creates_exactly_one_account(pg):  # noqa: F811
    """TC-AL-103 동시에 최초 설정 20개를 보내도 계정은 정확히 1개(나머지는 setup_closed)."""
    factory = sessionmaker(pg)
    results: list[str] = []
    lock = threading.Lock()

    def attempt(i: int):
        with factory() as db:
            try:
                admin_account.create_admin(db, f"admin{i:04d}", PW, now=T0)
                db.commit()
                out = "ok"
            except ProblemError as e:
                db.rollback()
                out = e.code
        with lock:
            results.append(out)

    ts = [threading.Thread(target=attempt, args=(i,)) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count("ok") == 1 and results.count("setup_closed") == 19
    with factory() as db:
        assert len(db.scalars(select(AdminAccount)).all()) == 1
