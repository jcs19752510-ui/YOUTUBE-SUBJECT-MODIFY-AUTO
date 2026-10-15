import type { Batch, Dashboard, Suggestion, VideoDetail, VideoSummary } from '../api/types';

export const video = (n: number, over: Partial<VideoSummary> = {}): VideoSummary => ({
  video_id: `vid${String(n).padStart(8, '0')}`,
  title: `테스트 영상 ${n}`,
  privacy_status: 'public',
  duration_sec: 180,
  is_short: false,
  excluded: false,
  exclusion_reasons: [],
  workflow_status: 'none',
  suggestion_count: 0,
  last_change_at: null,
  views: 1000 + n,
  ...over,
});

export const suggestion = (id: number, over: Partial<Suggestion> = {}): Suggestion => ({
  id,
  video_id: 'vid00000001',
  title: '테스트 영상 1 핵심 정리',
  evidence: '모의 근거',
  source: 'ai:mock',
  topic: '생활',
  strict: false,
  validation_result: 'pass',
  reasons: [],
  length: 15,
  match_ratio: 0.9,
  status: 'candidate',
  plan_hash: null,
  approval: null,
  created_at: '2026-10-10T00:00:00Z',
  ...over,
});

export const detail = (
  suggestions: Suggestion[],
  over: Partial<VideoDetail> = {},
): VideoDetail => ({
  ...video(1),
  description_excerpt: '설명',
  suggestions,
  changes: [],
  limits: { allowed: true, reasons: [], next_allowed_at: null },
  ...over,
});

export const dashboard = (over: Partial<Dashboard> = {}): Dashboard => ({
  mode: 'demo',
  live_enabled: false,
  google: { mode: 'demo', connected: false },
  counts: { videos: 200, excluded: 10, suggested: 3, approved: 2, queued: 0, applied: 5 },
  today: { applied: 2, cap: 10 },
  quota: { used: 1200, limit: 6000, remaining: 4800, pt_date: '2026-10-10' },
  active_job: null,
  queue: { pending_items: 0, next_run_date: null },
  ...over,
});

export const draftBatch = (over: Partial<Batch> = {}): Batch => ({
  id: 7,
  status: 'draft',
  note: null,
  created_at: '2026-10-10T00:00:00Z',
  executed_at: null,
  counts: { pending: 2, running: 0, success: 0, failed: 0, skipped: 0, cancelled: 0 },
  items: [1, 2].map((n) => ({
    id: n,
    suggestion_id: n,
    video_id: `vid0000000${n}`,
    video_title: `테스트 영상 ${n}`,
    previous_title: `이전 ${n}`,
    new_title: `새 제목 ${n}`,
    seq: n,
    scheduled_date: null,
    status: 'pending',
    skip_reason: null,
    change_id: null,
  })),
  precheck: {
    item_count: 2,
    estimated_units: 100,
    daily_cap: 10,
    quota_remaining_units: 4800,
    schedule: [{ date: '2026-10-10', count: 2 }],
    warnings: [],
    blocked: [],
    confirm_text: '실행 2건',
  },
  ...over,
});
