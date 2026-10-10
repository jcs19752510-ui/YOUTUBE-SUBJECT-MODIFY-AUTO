// WEB_DESIGN §3 계약을 그대로 옮긴 타입. 필드명은 서버와 일치해야 한다.
// 서버 문서에 스키마가 없는 부분(VideoReport, Settings, AuditEntry 등)은 "추정" 표시를 달았다.

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProblemJson {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  hint?: string;
}

export interface AuthMe {
  authenticated: boolean;
  pin_required: boolean;
  csrf_token: string | null;
}
export interface SessionResponse {
  csrf_token: string;
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | (string & {});
export interface Job {
  id: string;
  type: string;
  status: JobStatus;
  progress: number;
  total: number;
  error: string | null;
  result: Record<string, unknown> | null;
}

export interface Dashboard {
  mode: 'demo' | 'live';
  live_enabled: boolean;
  google: { mode: string; connected: boolean };
  counts: {
    videos: number;
    excluded: number;
    suggested: number;
    approved: number;
    queued: number;
    applied: number;
  };
  today: { applied: number; cap: number };
  quota: { used: number; limit: number; remaining: number; pt_date: string };
  /** 서버 문서에 형태가 없음(추정): 진행 중 작업이 없으면 null */
  active_job: Pick<Job, 'id' | 'type' | 'status' | 'progress' | 'total'> | null;
  queue: { pending_items: number; next_run_date: string | null };
}

export type WorkflowStatus =
  'none' | 'suggested' | 'approved' | 'queued' | 'applied' | 'rolled_back';

export interface VideoSummary {
  video_id: string;
  title: string;
  privacy_status: string | null;
  duration_sec: number | null;
  is_short: boolean;
  excluded: boolean;
  exclusion_reasons: string[];
  workflow_status: WorkflowStatus;
  suggestion_count: number;
  last_change_at: string | null;
  views: number | null;
}

export type ValidationResult = 'pass' | 'warn' | 'block';
export interface ValidationReason {
  code: string;
  severity: string;
  message: string;
}
export type SuggestionStatus =
  'candidate' | 'approved' | 'rejected' | 'queued' | 'applied' | 'expired' | (string & {});
export interface Approval {
  approver: string;
  approved_at: string;
  expires_at: string;
}
export interface Suggestion {
  id: number;
  video_id: string;
  title: string;
  evidence: string | null;
  source: string;
  topic: string | null;
  strict: boolean;
  validation_result: ValidationResult | null;
  reasons: ValidationReason[];
  length: number;
  match_ratio: number | null;
  status: SuggestionStatus;
  plan_hash: string | null;
  approval: Approval | null;
  created_at: string;
}

export interface Change {
  id: number;
  video_id: string;
  video_title: string;
  change_type: 'apply' | 'rollback' | (string & {});
  previous_title: string;
  new_title: string;
  result: string;
  mode: string;
  approver: string | null;
  applied_at: string | null;
  verified_at: string | null;
  error_code: string | null;
  rollbackable: boolean;
  batch_id: number | null;
}

/** reasons 원소가 문자열인지 {code,message}인지 서버 문서에 없어 둘 다 받는다(추정). */
export type LimitReason = string | { code?: string; message: string };
export interface VideoDetail extends VideoSummary {
  description_excerpt: string | null;
  suggestions: Suggestion[];
  changes: Change[];
  limits: { allowed: boolean; reasons: LimitReason[]; next_allowed_at: string | null };
}

export type BatchItemStatus =
  'pending' | 'running' | 'success' | 'failed' | 'skipped' | 'cancelled' | (string & {});
export interface BatchItem {
  id: number;
  suggestion_id: number;
  video_id: string;
  video_title: string;
  previous_title: string;
  new_title: string;
  seq: number;
  scheduled_date: string | null;
  status: BatchItemStatus;
  skip_reason: string | null;
  change_id: number | null;
}
export interface BatchCounts {
  pending: number;
  running: number;
  success: number;
  failed: number;
  skipped: number;
  cancelled: number;
}
export type BatchStatus =
  'draft' | 'running' | 'completed' | 'cancelled' | 'failed' | (string & {});
export interface Precheck {
  item_count: number;
  estimated_units: number;
  daily_cap: number;
  quota_remaining_units: number;
  schedule: { date: string; count: number }[];
  warnings: string[];
  blocked: { suggestion_id: number; reason: string }[];
  confirm_text: string;
}
export interface Batch {
  id: number;
  status: BatchStatus;
  note: string | null;
  created_at: string;
  executed_at: string | null;
  counts: BatchCounts;
  items: BatchItem[];
  /** 서버 문서의 Batch 스키마에는 없음. 있으면 초안 점검 표를 새로고침 후에도 복구한다(요청 사항). */
  precheck?: Precheck | null;
}
export interface BatchCreated {
  batch: Batch;
  precheck: Precheck;
}
export interface BatchExecuted {
  batch: Batch;
  job: Job;
}

// ---- 추정 스키마(서버 문서 없음) ----
export interface MetricSnapshot {
  id: number;
  taken_at: string;
  phase: string;
  source: string;
  period_start: string | null;
  period_end: string | null;
  impressions: number | null;
  ctr: number | null;
  views: number | null;
  watch_minutes: number | null;
}
export interface MetricDelta {
  key: string;
  label: string;
  before: number | null;
  after: number | null;
  delta: number | null;
  pct: number | null;
}
export interface VideoReport {
  video_id: string;
  title: string | null;
  status: 'no_change' | 'insufficient' | 'ok' | (string & {});
  before: MetricSnapshot | null;
  after: MetricSnapshot | null;
  baseline_missing: boolean;
  reasons: string[];
  notes: string[];
  metrics: MetricDelta[];
  expected_after_date: string | null;
}
export interface ReportsResponse {
  items: VideoReport[];
  notes: string[];
}

export interface SettingsData {
  daily_apply_cap: number;
  suggestions_per_video: number;
  tone: string;
  pin_set: boolean;
  live_enabled: boolean;
  allowed_video_ids: string[];
}
export interface SettingsPatch {
  daily_apply_cap?: number;
  suggestions_per_video?: number;
  tone?: string;
  /** 문자열=PIN 설정, null=PIN 해제 */
  pin?: string | null;
}

export interface AuditEntry {
  id: number;
  ts: string;
  actor: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail: Record<string, unknown>;
}
export interface AuditPage extends Page<AuditEntry> {
  chain_ok: boolean;
}

export interface GoogleStatus {
  mode: string;
  connected: boolean;
  message: string;
}

export interface VideoListQuery {
  q?: string;
  status?: WorkflowStatus | '';
  excluded?: 'true' | 'false' | '';
  sort?: string;
  order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}
