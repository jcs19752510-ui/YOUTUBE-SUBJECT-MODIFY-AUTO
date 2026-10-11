"""데이터 모델 원본(WEB_DESIGN §2). PostgreSQL이 운영 대상이고, 단위 테스트용으로 SQLite도 동작하도록 타입 variant를 둔다.

규칙
- 시각은 모두 UTC timestamptz. SQLite에서도 항상 tz-aware UTC로 돌려준다(UTCDateTime).
- 상태·종류 문자열은 CHECK 제약으로 닫는다(오타·임의 값 차단).
- 이중 반영 차단: 부분 고유 인덱스 2개(batch_items 진행 중 제안 1개, changes planned 영상당 1개).
- audit_log는 앱 계정에 INSERT/SELECT만 부여한다(UPDATE/DELETE 없음, web/docker/db 초기화 참고).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")
BigPK = BigInteger().with_variant(Integer(), "sqlite")  # SQLite는 INTEGER PRIMARY KEY만 자동 증가


class UTCDateTime(TypeDecorator):
    """항상 tz-aware UTC로 저장·반환한다(SQLite 테스트 호환)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime 은 저장할 수 없습니다(UTC tz-aware 필요).")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


SUGGESTION_STATUSES = ("candidate", "approved", "queued", "applied", "rolled_back", "rejected", "blocked", "expired")
VALIDATION_RESULTS = ("pass", "warn", "block")
BATCH_STATUSES = ("draft", "queued", "running", "paused", "done", "cancelled")
BATCH_ITEM_STATUSES = ("pending", "running", "success", "failed", "skipped", "cancelled")
CHANGE_TYPES = ("apply", "rollback")
CHANGE_RESULTS = ("planned", "success", "failed", "aborted")
JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
QUOTA_STATUSES = ("reserved", "ok", "failed")
TOPICS = ("life", "health", "finance")


class Video(Base):
    __tablename__ = "videos"

    video_id: Mapped[str] = mapped_column(String(11), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(16))
    privacy_status: Mapped[str | None] = mapped_column(String(16))
    made_for_kids: Mapped[bool | None] = mapped_column(Boolean)
    live_broadcast_content: Mapped[str | None] = mapped_column(String(16))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    is_short: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description_excerpt: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[dict] = mapped_column(JSONType, nullable=False)  # 반영 전 보존·롤백용 전체 snippet
    views: Mapped[int | None] = mapped_column(Integer)
    exclusion_reasons: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="demo")
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    __table_args__ = (CheckConstraint(_in("source", ("demo", "youtube")), name="ck_videos_source"),)


class AiRun(Base):
    __tablename__ = "ai_runs"

    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.video_id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str | None] = mapped_column(String(80))
    params: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))  # 원문 대신 해시만 보관(S-W07)
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    __table_args__ = (CheckConstraint(_in("status", ("ok", "failed")), name="ck_ai_runs_status"),)


class Suggestion(Base):
    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.video_id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), nullable=False)  # 'ai:mock' | 'manual'
    ai_run_id: Mapped[int | None] = mapped_column(ForeignKey("ai_runs.id"))
    topic: Mapped[str | None] = mapped_column(String(16))
    strict_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_result: Mapped[str | None] = mapped_column(String(8))
    validation_reasons: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)  # [{code,severity,message}]
    match_ratio: Mapped[float | None] = mapped_column(Float)
    dictionary_hash: Mapped[str | None] = mapped_column(String(64))
    plan_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    video: Mapped[Video] = relationship()
    approval: Mapped["Approval | None"] = relationship(back_populates="suggestion", uselist=False)

    __table_args__ = (
        CheckConstraint(_in("status", SUGGESTION_STATUSES), name="ck_suggestions_status"),
        CheckConstraint(f"validation_result IS NULL OR {_in('validation_result', VALIDATION_RESULTS)}", name="ck_suggestions_result"),
        CheckConstraint(f"topic IS NULL OR {_in('topic', TOPICS)}", name="ck_suggestions_topic"),
        UniqueConstraint("video_id", "title", name="uq_suggestions_video_title"),
    )


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    suggestion_id: Mapped[int] = mapped_column(ForeignKey("suggestions.id"), nullable=False, unique=True)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approver: Mapped[str] = mapped_column(String(40), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    mac: Mapped[str] = mapped_column(String(64), nullable=False)  # 변조 탐지용 HMAC-SHA256(키는 secrets 폴더)

    suggestion: Mapped[Suggestion] = relationship(back_populates="approval")


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    note: Mapped[str | None] = mapped_column(String(200))
    precheck: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    items: Mapped[list["BatchItem"]] = relationship(back_populates="batch", order_by="BatchItem.seq", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint(_in("status", BATCH_STATUSES), name="ck_batches_status"),)


class BatchItem(Base):
    __tablename__ = "batch_items"

    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    suggestion_id: Mapped[int] = mapped_column(ForeignKey("suggestions.id"), nullable=False)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.video_id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column(Date)  # KST 기준 날짜
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    skip_reason: Mapped[str | None] = mapped_column(String(200))
    change_id: Mapped[int | None] = mapped_column(ForeignKey("changes.id"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    batch: Mapped[Batch] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint(_in("status", BATCH_ITEM_STATUSES), name="ck_batch_items_status"),
        UniqueConstraint("batch_id", "suggestion_id", name="uq_batch_items_batch_suggestion"),
        # 같은 제안이 두 배치에서 동시에 진행되지 않게 한다(S-W12).
        Index(
            "uq_batch_items_active_suggestion",
            "suggestion_id",
            unique=True,
            postgresql_where=text("status IN ('pending','running')"),
            sqlite_where=text("status IN ('pending','running')"),
        ),
        Index("ix_batch_items_due", "status", "scheduled_date"),
    )


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.video_id"), nullable=False)
    suggestion_id: Mapped[int | None] = mapped_column(ForeignKey("suggestions.id"))
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"))
    change_type: Mapped[str] = mapped_column(String(10), nullable=False)
    previous_title: Mapped[str] = mapped_column(Text, nullable=False)
    new_title: Mapped[str] = mapped_column(Text, nullable=False)
    backup_snippet: Mapped[dict | None] = mapped_column(JSONType)
    reason: Mapped[str | None] = mapped_column(Text)
    approver: Mapped[str | None] = mapped_column(String(40))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    plan_hash: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60))
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default="demo")
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    verify_result: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    __table_args__ = (
        CheckConstraint(_in("change_type", CHANGE_TYPES), name="ck_changes_type"),
        CheckConstraint(_in("result", CHANGE_RESULTS), name="ck_changes_result"),
        CheckConstraint(_in("mode", ("demo", "live")), name="ck_changes_mode"),
        # 영상당 'planned' 변경은 동시에 1개만(이중 반영 차단).
        Index(
            "uq_changes_planned_per_video",
            "video_id",
            unique=True,
            postgresql_where=text("result = 'planned'"),
            sqlite_where=text("result = 'planned'"),
        ),
        Index("ix_changes_video_applied", "video_id", "applied_at"),
    )


class QuotaUsage(Base):
    __tablename__ = "quota_usage"

    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    pt_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # 태평양 시간 기준일
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    called_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(10), nullable=False)

    __table_args__ = (
        CheckConstraint("units >= 0", name="ck_quota_units"),
        CheckConstraint(_in("status", QUOTA_STATUSES), name="ck_quota_status"),
    )


class MetricsSnapshot(Base):
    __tablename__ = "metrics_snapshots"

    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.video_id"), nullable=False)
    taken_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    phase: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    impressions: Mapped[int | None] = mapped_column(Integer)
    ctr: Mapped[float | None] = mapped_column(Float)
    views: Mapped[int | None] = mapped_column(Integer)
    watch_minutes: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        CheckConstraint(_in("phase", ("before", "after", "periodic")), name="ck_metrics_phase"),
        CheckConstraint(_in("source", ("api", "csv", "demo")), name="ck_metrics_source"),
        Index("ix_metrics_video_phase", "video_id", "phase", "taken_at"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued")
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONType)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_after: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(80))
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    __table_args__ = (
        CheckConstraint(_in("status", JOB_STATUSES), name="ck_jobs_status"),
        Index("ix_jobs_due", "status", "run_after"),
    )


class AuditLog(Base):
    """추가 전용. 앱 계정은 INSERT/SELECT만 가진다. hash = sha256(prev_hash || canonical_json(행 내용))."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigPK, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    actor: Mapped[str] = mapped_column(String(60), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class SettingKV(Base):
    __tablename__ = "settings_kv"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 쿠키 토큰의 sha256(원문은 저장하지 않음)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    route: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
