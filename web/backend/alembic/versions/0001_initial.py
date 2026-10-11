"""초기 스키마(WEB_DESIGN §2). 모델에서 렌더링한 PostgreSQL DDL 을 고정 문자열로 보관한다.

모델이 바뀌어도 이 파일은 바뀌지 않는다(스키마 변경은 새 리비전으로). 역할(ytweb_owner=마이그레이션,
ytweb_app=런타임 DML)과 기본 권한 생성은 인프라(web/docker/db)의 몫이다.
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE TABLE audit_log (
	id BIGSERIAL NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	actor VARCHAR(60) NOT NULL, 
	action VARCHAR(60) NOT NULL, 
	target_type VARCHAR(40), 
	target_id VARCHAR(80), 
	detail JSONB NOT NULL, 
	prev_hash VARCHAR(64) NOT NULL, 
	hash VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (hash)
)""",
    """CREATE TABLE batches (
	id BIGSERIAL NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	note VARCHAR(200), 
	precheck JSONB, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	executed_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_batches_status CHECK (status IN ('draft', 'queued', 'running', 'paused', 'done', 'cancelled'))
)""",
    """CREATE TABLE idempotency_keys (
	key VARCHAR(80) NOT NULL, 
	route VARCHAR(120) NOT NULL, 
	request_hash VARCHAR(64) NOT NULL, 
	response_status INTEGER, 
	response_body JSONB, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (key)
)""",
    """CREATE TABLE jobs (
	id VARCHAR(36) NOT NULL, 
	type VARCHAR(40) NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	payload JSONB NOT NULL, 
	result JSONB, 
	progress INTEGER NOT NULL, 
	total INTEGER NOT NULL, 
	error TEXT, 
	attempts INTEGER NOT NULL, 
	run_after TIMESTAMP WITH TIME ZONE NOT NULL, 
	locked_by VARCHAR(80), 
	locked_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_jobs_status CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled'))
)""",
    """CREATE INDEX ix_jobs_due ON jobs (status, run_after)""",
    """CREATE TABLE quota_usage (
	id BIGSERIAL NOT NULL, 
	pt_date DATE NOT NULL, 
	method VARCHAR(40) NOT NULL, 
	units INTEGER NOT NULL, 
	called_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	job_id VARCHAR(36), 
	status VARCHAR(10) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_quota_units CHECK (units >= 0), 
	CONSTRAINT ck_quota_status CHECK (status IN ('reserved', 'ok', 'failed'))
)""",
    """CREATE INDEX ix_quota_usage_pt_date ON quota_usage (pt_date)""",
    """CREATE TABLE sessions (
	id VARCHAR(64) NOT NULL, 
	csrf_token VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)""",
    """CREATE TABLE settings_kv (
	key VARCHAR(60) NOT NULL, 
	value JSONB NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (key)
)""",
    """CREATE TABLE videos (
	video_id VARCHAR(11) NOT NULL, 
	title TEXT NOT NULL, 
	category_id VARCHAR(16), 
	privacy_status VARCHAR(16), 
	made_for_kids BOOLEAN, 
	live_broadcast_content VARCHAR(16), 
	duration_sec INTEGER, 
	is_short BOOLEAN NOT NULL, 
	description_excerpt TEXT, 
	snippet JSONB NOT NULL, 
	views INTEGER, 
	exclusion_reasons JSONB NOT NULL, 
	source VARCHAR(16) NOT NULL, 
	fetched_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (video_id), 
	CONSTRAINT ck_videos_source CHECK (source IN ('demo', 'youtube'))
)""",
    """CREATE TABLE ai_runs (
	id BIGSERIAL NOT NULL, 
	video_id VARCHAR(11) NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	model VARCHAR(80), 
	params JSONB NOT NULL, 
	prompt_hash VARCHAR(64), 
	input_chars INTEGER NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	error TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_ai_runs_status CHECK (status IN ('ok', 'failed')), 
	FOREIGN KEY(video_id) REFERENCES videos (video_id)
)""",
    """CREATE TABLE metrics_snapshots (
	id BIGSERIAL NOT NULL, 
	video_id VARCHAR(11) NOT NULL, 
	taken_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	phase VARCHAR(10) NOT NULL, 
	source VARCHAR(8) NOT NULL, 
	period_start DATE, 
	period_end DATE, 
	impressions INTEGER, 
	ctr FLOAT, 
	views INTEGER, 
	watch_minutes FLOAT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_metrics_phase CHECK (phase IN ('before', 'after', 'periodic')), 
	CONSTRAINT ck_metrics_source CHECK (source IN ('api', 'csv', 'demo')), 
	FOREIGN KEY(video_id) REFERENCES videos (video_id)
)""",
    """CREATE INDEX ix_metrics_video_phase ON metrics_snapshots (video_id, phase, taken_at)""",
    """CREATE TABLE suggestions (
	id BIGSERIAL NOT NULL, 
	video_id VARCHAR(11) NOT NULL, 
	title TEXT NOT NULL, 
	evidence TEXT, 
	source VARCHAR(40) NOT NULL, 
	ai_run_id BIGINT, 
	topic VARCHAR(16), 
	strict_mode BOOLEAN NOT NULL, 
	validation_result VARCHAR(8), 
	validation_reasons JSONB NOT NULL, 
	match_ratio FLOAT, 
	dictionary_hash VARCHAR(64), 
	plan_hash VARCHAR(64), 
	status VARCHAR(16) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_suggestions_status CHECK (status IN ('candidate', 'approved', 'queued', 'applied', 'rolled_back', 'rejected', 'blocked', 'expired')), 
	CONSTRAINT ck_suggestions_result CHECK (validation_result IS NULL OR validation_result IN ('pass', 'warn', 'block')), 
	CONSTRAINT ck_suggestions_topic CHECK (topic IS NULL OR topic IN ('life', 'health', 'finance')), 
	CONSTRAINT uq_suggestions_video_title UNIQUE (video_id, title), 
	FOREIGN KEY(video_id) REFERENCES videos (video_id), 
	FOREIGN KEY(ai_run_id) REFERENCES ai_runs (id)
)""",
    """CREATE INDEX ix_suggestions_video_id ON suggestions (video_id)""",
    """CREATE TABLE approvals (
	id BIGSERIAL NOT NULL, 
	suggestion_id BIGINT NOT NULL, 
	plan_hash VARCHAR(64) NOT NULL, 
	approver VARCHAR(40) NOT NULL, 
	approved_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	used_at TIMESTAMP WITH TIME ZONE, 
	mac VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (suggestion_id), 
	FOREIGN KEY(suggestion_id) REFERENCES suggestions (id)
)""",
    """CREATE TABLE changes (
	id BIGSERIAL NOT NULL, 
	video_id VARCHAR(11) NOT NULL, 
	suggestion_id BIGINT, 
	batch_id BIGINT, 
	change_type VARCHAR(10) NOT NULL, 
	previous_title TEXT NOT NULL, 
	new_title TEXT NOT NULL, 
	backup_snippet JSONB, 
	reason TEXT, 
	approver VARCHAR(40), 
	approved_at TIMESTAMP WITH TIME ZONE, 
	plan_hash VARCHAR(64), 
	result VARCHAR(10) NOT NULL, 
	error_code VARCHAR(60), 
	mode VARCHAR(8) NOT NULL, 
	applied_at TIMESTAMP WITH TIME ZONE, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verify_result JSONB, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_changes_type CHECK (change_type IN ('apply', 'rollback')), 
	CONSTRAINT ck_changes_result CHECK (result IN ('planned', 'success', 'failed', 'aborted')), 
	CONSTRAINT ck_changes_mode CHECK (mode IN ('demo', 'live')), 
	FOREIGN KEY(video_id) REFERENCES videos (video_id), 
	FOREIGN KEY(suggestion_id) REFERENCES suggestions (id), 
	FOREIGN KEY(batch_id) REFERENCES batches (id)
)""",
    """CREATE INDEX ix_changes_video_applied ON changes (video_id, applied_at)""",
    """CREATE UNIQUE INDEX uq_changes_planned_per_video ON changes (video_id) WHERE result = 'planned'""",
    """CREATE TABLE batch_items (
	id BIGSERIAL NOT NULL, 
	batch_id BIGINT NOT NULL, 
	suggestion_id BIGINT NOT NULL, 
	video_id VARCHAR(11) NOT NULL, 
	seq INTEGER NOT NULL, 
	scheduled_date DATE, 
	status VARCHAR(12) NOT NULL, 
	skip_reason VARCHAR(200), 
	change_id BIGINT, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_batch_items_status CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped', 'cancelled')), 
	CONSTRAINT uq_batch_items_batch_suggestion UNIQUE (batch_id, suggestion_id), 
	FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE CASCADE, 
	FOREIGN KEY(suggestion_id) REFERENCES suggestions (id), 
	FOREIGN KEY(video_id) REFERENCES videos (video_id), 
	FOREIGN KEY(change_id) REFERENCES changes (id)
)""",
    """CREATE INDEX ix_batch_items_batch_id ON batch_items (batch_id)""",
    """CREATE INDEX ix_batch_items_due ON batch_items (status, scheduled_date)""",
    """CREATE UNIQUE INDEX uq_batch_items_active_suggestion ON batch_items (suggestion_id) WHERE status IN ('pending','running')""",
]

TABLES_DROP_ORDER = ['batch_items', 'changes', 'approvals', 'suggestions', 'metrics_snapshots', 'ai_runs', 'videos', 'settings_kv', 'sessions', 'quota_usage', 'jobs', 'idempotency_keys', 'batches', 'audit_log']

REVOKE_AUDIT_MUTATION = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ytweb_app') THEN
        REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM ytweb_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(sa.text(stmt.replace(":", "\\:")))
    op.execute(sa.text(REVOKE_AUDIT_MUTATION))


def downgrade() -> None:
    for table in TABLES_DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
