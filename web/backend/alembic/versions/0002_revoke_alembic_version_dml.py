"""앱 계정이 마이그레이션 버전표(alembic_version)를 바꾸지 못하게 한다(DEF-VA-012, 설계: 앱 계정은 구조 변경 불가).

alembic_version 은 Alembic 이 소유자 계정으로 만들기 때문에 인프라의 기본 권한(ALTER DEFAULT PRIVILEGES ... GRANT SELECT, INSERT,
UPDATE, DELETE ON TABLES TO ytweb_app)이 그대로 적용돼 앱 계정이 버전 행을 고치거나 지울 수 있었다. SELECT 만 남긴다.
0001 은 바꾸지 않는다(이미 배포된 DB 도 이 리비전 적용으로 같은 상태가 된다). 역할이 없는 환경(개발·테스트)에서는 건너뛴다.
이후 인프라가 다시 `GRANT ... ON ALL TABLES` 를 주면 이 회수는 무효가 된다(0001 의 audit_log 회수와 같은 한계) —
`web/docker/db/audit-guard.sql` 쪽에서 복원 후에도 같은 회수를 하도록 하는 것이 W-INF 몫(제안으로 보고).
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

REVOKE_VERSION_TABLE_DML = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ytweb_app') THEN
        REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON alembic_version FROM ytweb_app;
    END IF;
END
$$
"""

RESTORE_VERSION_TABLE_DML = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ytweb_app') THEN
        GRANT INSERT, UPDATE, DELETE ON alembic_version TO ytweb_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    op.execute(sa.text(REVOKE_VERSION_TABLE_DML))


def downgrade() -> None:
    op.execute(sa.text(RESTORE_VERSION_TABLE_DML))
