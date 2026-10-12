import type { Suggestion } from '../api/types';

type ScoreInput = Pick<Suggestion, 'validation_result' | 'length' | 'match_ratio' | 'reasons'>;

// 일치율·길이·핵심어 위치처럼 따로 점수를 주는 항목의 코드는 "기타 주의 사유" 감점에서 뺀다
const SCORED_CODES = new Set(['LEN_REC', 'MATCH_WEAK', 'MATCH_LOW', 'KEY_LATE']);

/**
 * 제안 점검 점수(0~100). 클릭률 예측이 아니라, 프로그램이 이미 계산한 값(영상 내용 일치율·길이·핵심어 위치·주의 사유)을
 * 같은 기준으로 한 숫자로 합친 것이라 후보를 비교할 때만 쓴다. 차단 판정은 30점을 넘지 않는다.
 */
export function suggestionScore(s: ScoreInput): number {
  const ratio = s.match_ratio ?? 0.5;
  const match = 40 * Math.min(1, Math.max(0, ratio) / 0.75);
  const n = s.length;
  const len = n > 40 ? Math.max(0, 20 - (n - 40)) : n >= 15 ? 20 : (20 * Math.max(0, n)) / 15;
  const keyLate = s.reasons.some((r) => r.code === 'KEY_LATE') ? 0 : 15;
  const otherWarns = s.reasons.filter((r) => r.severity === 'warn' && !SCORED_CODES.has(r.code)).length;
  const other = Math.max(0, 25 - 10 * otherWarns);
  const total = Math.round(match + len + keyLate + other);
  return s.validation_result === 'block' ? Math.min(total, 30) : total;
}

export const scoreTone = (score: number): 'success' | 'warning' | 'danger' =>
  score >= 80 ? 'success' : score >= 50 ? 'warning' : 'danger';
