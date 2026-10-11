"""API 요청·응답 스키마(Pydantic v2). WEB_DESIGN §3 의 스키마와 같은 이름·필드를 쓴다.

계약에 없는 추가 필드(선택, 프런트가 무시해도 되는 것): VideoDetail.preserved, BlockedItem.code.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

T = TypeVar("T")
VIDEO_ID = r"^[A-Za-z0-9_-]{11}$"
MAX_ID = 2**63 - 1       # DB 정수 범위. 이보다 큰 ID·쪽 번호는 DB 오류(500)가 되기 전에 스키마에서 422 로 거부한다(DEF-9-001)
MAX_PAGE = 1_000_000
WorkflowStatus = Literal["none", "suggested", "approved", "queued", "applied", "rolled_back"]
Validation = Literal["pass", "warn", "block"]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ReasonOut(BaseModel):
    code: str
    severity: Literal["block", "warn"]
    message: str


class ApprovalOut(BaseModel):
    approver: str
    approved_at: datetime
    expires_at: datetime


class SuggestionOut(BaseModel):
    id: int
    video_id: str
    title: str
    evidence: str | None
    source: str
    topic: str | None
    strict: bool
    validation_result: Validation | None
    reasons: list[ReasonOut]
    length: int
    match_ratio: float | None
    status: str
    plan_hash: str | None
    approval: ApprovalOut | None
    created_at: datetime


class VideoSummaryOut(BaseModel):
    video_id: str
    title: str
    privacy_status: str | None
    duration_sec: int | None
    is_short: bool
    excluded: bool
    exclusion_reasons: list[str]
    workflow_status: WorkflowStatus
    suggestion_count: int
    last_change_at: datetime | None
    views: int | None


class ChangeOut(BaseModel):
    id: int
    video_id: str
    video_title: str | None
    change_type: Literal["apply", "rollback"]
    previous_title: str
    new_title: str
    result: Literal["planned", "success", "failed", "aborted"]
    mode: Literal["demo", "live"]
    approver: str | None
    applied_at: datetime | None
    verified_at: datetime | None
    error_code: str | None
    rollbackable: bool
    batch_id: int | None


class LimitsOut(BaseModel):
    allowed: bool
    reasons: list[str]
    next_allowed_at: datetime | None


class PreservedOut(BaseModel):
    category_id: str | None
    tags: list[str]
    default_language: str | None
    default_audio_language: str | None
    description_chars: int


class VideoDetailOut(VideoSummaryOut):
    description_excerpt: str | None
    suggestions: list[SuggestionOut]
    changes: list[ChangeOut]
    limits: LimitsOut
    preserved: PreservedOut


class JobOut(BaseModel):
    id: str
    type: str
    status: str
    progress: int
    total: int
    error: str | None
    result: dict[str, Any] | None


class BatchItemOut(BaseModel):
    id: int
    suggestion_id: int
    video_id: str
    video_title: str | None
    previous_title: str
    new_title: str
    seq: int
    scheduled_date: date | None
    status: Literal["pending", "running", "success", "failed", "skipped", "cancelled"]
    skip_reason: str | None
    change_id: int | None


class BatchCounts(BaseModel):
    pending: int
    running: int
    success: int
    failed: int
    skipped: int
    cancelled: int


class ScheduleEntry(BaseModel):
    date: date
    count: int


class BlockedItem(BaseModel):
    suggestion_id: int
    reason: str
    code: str | None = None
    batch_id: int | None = None  # code=already_in_batch 일 때 제안을 붙잡고 있는 배치(초안이면 버릴 수 있다)


class PrecheckOut(BaseModel):
    item_count: int
    estimated_units: int
    daily_cap: int
    quota_remaining_units: int
    schedule: list[ScheduleEntry]
    warnings: list[str]
    blocked: list[BlockedItem]
    confirm_text: str
    notice: str | None = None  # 면책 고지(POL-002). 이 필드가 없던 옛 사전 점검 기록은 null


class BatchOut(BaseModel):
    id: int
    status: str
    note: str | None
    created_at: datetime
    executed_at: datetime | None
    counts: BatchCounts
    items: list[BatchItemOut]
    precheck: PrecheckOut | None = None


class BatchCreatedOut(BaseModel):
    batch: BatchOut
    precheck: PrecheckOut


class BatchExecutedOut(BaseModel):
    batch: BatchOut
    job: JobOut


class MetricDeltaOut(BaseModel):
    key: str
    label: str
    before: float | None
    after: float | None
    delta: float | None
    pct: float | None


class SnapshotOut(BaseModel):
    id: int
    taken_at: str
    phase: str
    source: str
    period_start: str | None
    period_end: str | None
    impressions: int | None
    ctr: float | None
    views: int | None
    watch_minutes: float | None


class ReportChangeOut(BaseModel):
    id: int
    change_type: str
    previous_title: str
    new_title: str
    at: str
    result: str
    approver: str | None


class VideoReportOut(BaseModel):
    video_id: str
    title: str | None
    status: Literal["no_change", "insufficient", "ok"]
    label: str | None
    baseline_missing: bool
    reasons: list[str]
    notes: list[str]
    changes: list[ReportChangeOut]
    target: ReportChangeOut | None
    before: SnapshotOut | None
    after: SnapshotOut | None
    metrics: list[MetricDeltaOut]
    expected_after_date: str | None


class ReportsOut(BaseModel):
    items: list[VideoReportOut]
    notes: list[str]


class QuotaOut(BaseModel):
    used: int
    limit: int
    remaining: int
    pt_date: date


class DashboardOut(BaseModel):
    mode: Literal["demo", "live"]
    live_enabled: bool
    google: dict[str, Any]
    counts: dict[str, int]
    today: dict[str, int]
    quota: QuotaOut
    active_job: JobOut | None
    queue: dict[str, Any]


class GoogleStatusOut(BaseModel):
    mode: Literal["demo", "read"]
    connected: bool
    message: str
    client_ready: bool = False
    last_error: str | None = None
    write_connected: bool = False      # 제목 수정(쓰기) 권한 로그인 여부(M3)
    live_write_enabled: bool = False   # YTWEB_LIVE_WRITE=1 여부
    live_allowed_count: int = 0        # 실제 수정이 허용된 영상 수
    live_write_ready: bool = False     # 위 3조건이 모두 맞아 실제 수정이 가능한 상태


# ───────────── 요청 ─────────────

class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SuggestionCreateIn(_In):
    count: int | None = Field(default=None, ge=1, le=5)


class GenerateIn(_In):
    video_ids: list[Annotated[str, StringConstraints(pattern=VIDEO_ID)]] = Field(min_length=1, max_length=200)
    count: int | None = Field(default=None, ge=1, le=5)


class TitleEditIn(_In):
    title: str = Field(min_length=1, max_length=2000)


class ApproveIn(_In):
    approver: str = Field(min_length=1, max_length=200)


class BatchCreateIn(_In):
    suggestion_ids: list[Annotated[int, Field(ge=1, le=MAX_ID)]] = Field(min_length=1, max_length=500)  # 50건 상한은 서비스가 한국어 메시지로 거부
    note: str | None = Field(default=None, max_length=1000)


class ExecuteIn(_In):
    confirm_text: str = Field(max_length=100)


class RollbackIn(_In):
    typed_video_id: str = Field(max_length=64)
    approver: str = Field(min_length=1, max_length=200)
