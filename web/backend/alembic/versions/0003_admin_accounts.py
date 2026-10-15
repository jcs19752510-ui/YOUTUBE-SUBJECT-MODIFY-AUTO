"""관리자 로그인 계정 표(DEC-055). 앱 계정(ytweb_app)은 인프라의 기본 권한으로 DML 만 받는다(구조 변경 불가).

비밀번호 원문은 저장하지 않는다(scrypt 해시). 아이디·비밀번호 값은 이 파일에 없다(비밀 파일에서 API 시작 시 반영).
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_accounts",
        sa.Column("login_id", sa.String(40), primary_key=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("admin_accounts")
