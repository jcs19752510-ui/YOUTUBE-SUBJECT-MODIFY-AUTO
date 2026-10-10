import { ko } from '../i18n/ko';
import type { Tone } from '../components/Badge';
import type { Job, LimitReason } from '../api/types';

const lookup = (map: Record<string, string>, key: string | null | undefined): string =>
  (key && map[key]) || key || '-';

export const workflowLabel = (s: string) => lookup(ko.workflow, s);
export const suggestionStatusLabel = (s: string) => lookup(ko.suggestionStatus, s);
export const batchStatusLabel = (s: string) => lookup(ko.batchStatus, s);
export const itemStatusLabel = (s: string) => lookup(ko.itemStatus, s);
export const changeTypeLabel = (s: string) => lookup(ko.changeType, s);
export const changeResultLabel = (s: string) => lookup(ko.changeResult, s);
export const privacyLabel = (s: string | null) => lookup(ko.privacy, s);

export function workflowTone(s: string): Tone {
  if (s === 'applied') return 'success';
  if (s === 'approved' || s === 'queued') return 'info';
  if (s === 'rolled_back') return 'warning';
  return 'neutral';
}
export function resultTone(r: string): Tone {
  if (r === 'success' || r === 'verified') return 'success';
  if (r === 'failed') return 'danger';
  if (r === 'rolled_back' || r === 'unverified') return 'warning';
  return 'neutral';
}
export function itemTone(r: string): Tone {
  if (r === 'success') return 'success';
  if (r === 'failed') return 'danger';
  if (r === 'skipped' || r === 'cancelled') return 'warning';
  if (r === 'running') return 'info';
  return 'neutral';
}

export const limitReasonText = (r: LimitReason): string => (typeof r === 'string' ? r : r.message);

export type JobPhase = 'active' | 'success' | 'failed';
export function jobPhase(j: Pick<Job, 'status'>): JobPhase {
  const s = String(j.status);
  if (['succeeded', 'success', 'done', 'completed', 'finished'].includes(s)) return 'success';
  if (['failed', 'error', 'cancelled', 'canceled'].includes(s)) return 'failed';
  return 'active';
}

export function isBatchActive(status: string): boolean {
  return !['draft', 'completed', 'done', 'cancelled', 'failed', 'finished'].includes(status);
}
