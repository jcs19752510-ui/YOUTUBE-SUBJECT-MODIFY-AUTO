import { ko } from '../i18n/ko';
import type { Tone } from '../components/Badge';
import type { Job, LimitReason } from '../api/types';

// 서버가 준 값이 'constructor' 같은 객체 기본 속성 이름이어도 라벨로 오인하지 않도록 자기 속성만 본다
const lookup = (map: Record<string, string>, key: string | null | undefined): string =>
  (key && Object.hasOwn(map, key) && map[key]) || key || '-';

export const workflowLabel = (s: string) => lookup(ko.workflow, s);
export const suggestionStatusLabel = (s: string) => lookup(ko.suggestionStatus, s);
export const batchStatusLabel = (s: string) => lookup(ko.batchStatus, s);
/** 실행한 적 없는 채로 중지된 배치는 "버려진 초안"으로 보여 준다(실행 중 중지와 구분) */
export const batchStatusText = (b: { status: string; executed_at: string | null }) =>
  b.status === 'cancelled' && !b.executed_at
    ? ko.batches.discardedLabel
    : batchStatusLabel(b.status);
export const auditActorLabel = (s: string) => lookup(ko.settings.actors, s);
export const auditActionLabel = (s: string) =>
  Object.hasOwn(ko.settings.actions, s)
    ? ko.settings.actions[s]!
    : s.startsWith('batch.item.')
      ? '배치 항목 처리'
      : s;
export const auditTargetLabel = (s: string | null) => lookup(ko.settings.targets, s);
export const itemStatusLabel = (s: string) => lookup(ko.itemStatus, s);
export const changeTypeLabel = (s: string) => lookup(ko.changeType, s);
export const changeResultLabel = (s: string) => lookup(ko.changeResult, s);
export const jobTypeLabel = (s: string) => lookup(ko.jobType, s);
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
