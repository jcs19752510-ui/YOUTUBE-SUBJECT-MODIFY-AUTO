import type { ApiClient } from './client';
import type {
  AuditPage,
  Batch,
  BatchCreated,
  BatchExecuted,
  Change,
  Dashboard,
  GoogleStatus,
  Job,
  Page,
  ReportsResponse,
  SettingsData,
  SettingsPatch,
  Suggestion,
  VideoDetail,
  VideoListQuery,
  VideoSummary,
} from './types';

const V1 = '/api/v1';

export function createEndpoints(c: ApiClient) {
  return {
    dashboard: () => c.request<Dashboard>('GET', `${V1}/dashboard`),
    videos: (q: VideoListQuery) =>
      c.request<Page<VideoSummary>>('GET', `${V1}/videos`, { query: { ...q } }),
    video: (id: string) => c.request<VideoDetail>('GET', `${V1}/videos/${encodeURIComponent(id)}`),
    syncVideos: () => c.request<Job>('POST', `${V1}/videos/sync`, { body: {} }),
    suggestForVideo: (id: string, count?: number) =>
      c.request<Suggestion[]>('POST', `${V1}/videos/${encodeURIComponent(id)}/suggestions`, {
        body: count ? { count } : {},
      }),
    generateSuggestions: (videoIds: string[], count?: number) =>
      c.request<Job>('POST', `${V1}/suggestions/generate`, {
        body: count ? { video_ids: videoIds, count } : { video_ids: videoIds },
      }),
    suggestions: (q: {
      video_id?: string;
      status?: string;
      result?: string;
      page?: number;
      page_size?: number;
    }) => c.request<Page<Suggestion>>('GET', `${V1}/suggestions`, { query: q }),
    editSuggestion: (id: number, title: string) =>
      c.request<Suggestion>('PATCH', `${V1}/suggestions/${id}`, { body: { title } }),
    approve: (id: number, approver: string) =>
      c.request<Suggestion>('POST', `${V1}/suggestions/${id}/approve`, { body: { approver } }),
    reject: (id: number) =>
      c.request<Suggestion>('POST', `${V1}/suggestions/${id}/reject`, { body: {} }),
    createBatch: (suggestionIds: number[], note: string | undefined, key: string) =>
      c.request<BatchCreated>('POST', `${V1}/batches`, {
        body: note ? { suggestion_ids: suggestionIds, note } : { suggestion_ids: suggestionIds },
        risky: true,
        idempotencyKey: key,
      }),
    batches: (q: { page?: number; page_size?: number }) =>
      c.request<Page<Batch>>('GET', `${V1}/batches`, { query: q }),
    batch: (id: number) => c.request<Batch>('GET', `${V1}/batches/${id}`),
    executeBatch: (id: number, confirmText: string, key: string) =>
      c.request<BatchExecuted>('POST', `${V1}/batches/${id}/execute`, {
        body: { confirm_text: confirmText },
        risky: true,
        idempotencyKey: key,
      }),
    cancelBatch: (id: number) =>
      c.request<Batch>('POST', `${V1}/batches/${id}/cancel`, { body: {} }),
    job: (id: string) => c.request<Job>('GET', `${V1}/jobs/${encodeURIComponent(id)}`),
    changes: (q: {
      video_id?: string;
      batch_id?: number;
      result?: string;
      page?: number;
      page_size?: number;
    }) => c.request<Page<Change>>('GET', `${V1}/changes`, { query: q }),
    rollback: (id: number, typedVideoId: string, approver: string, key: string) =>
      c.request<Change>('POST', `${V1}/changes/${id}/rollback`, {
        body: { typed_video_id: typedVideoId, approver },
        risky: true,
        idempotencyKey: key,
      }),
    reports: (videoId?: string) =>
      c.request<ReportsResponse>('GET', `${V1}/reports/changes`, { query: { video_id: videoId } }),
    reportCsv: () => c.requestBlob(`${V1}/reports/export.csv`),
    audit: (q: { page?: number; page_size?: number }) =>
      c.request<AuditPage>('GET', `${V1}/audit`, { query: q }),
    settings: () => c.request<SettingsData>('GET', `${V1}/settings`),
    patchSettings: (patch: SettingsPatch) =>
      c.request<SettingsData>('PATCH', `${V1}/settings`, { body: patch }),
    google: () => c.request<GoogleStatus>('GET', `${V1}/google/status`),
    googleConnect: () =>
      c.request<{ auth_url: string }>('POST', `${V1}/google/connect`, { body: {} }),
    googleDisconnect: () =>
      c.request<{ connected: boolean }>('POST', `${V1}/google/disconnect`, { body: {} }),
  };
}

export type Endpoints = ReturnType<typeof createEndpoints>;
