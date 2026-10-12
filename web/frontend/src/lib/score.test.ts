import { describe, expect, it } from 'vitest';
import { scoreTone, suggestionScore } from './score';

const base = { validation_result: 'pass' as const, length: 29, match_ratio: 0.71, reasons: [] };

describe('suggestionScore', () => {
  it('통과·적정 길이·높은 일치율은 높은 점수', () => expect(suggestionScore(base)).toBeGreaterThanOrEqual(90));
  it('차단 판정은 30점을 넘지 않는다', () =>
    expect(suggestionScore({ ...base, validation_result: 'block', match_ratio: 0.22 })).toBeLessThanOrEqual(30));
  it('일치율이 낮을수록 점수가 낮다', () =>
    expect(suggestionScore({ ...base, match_ratio: 0.3 })).toBeLessThan(suggestionScore(base)));
  it('권장 길이(40자)를 넘으면 감점', () => expect(suggestionScore({ ...base, length: 71 })).toBeLessThan(suggestionScore(base)));
  it('주의 사유가 있으면 감점', () =>
    expect(suggestionScore({ ...base, reasons: [{ code: 'EXCLAMATION', severity: 'warn', message: 'x' }] })).toBeLessThan(suggestionScore(base)));
  it('0~100 범위', () => {
    const lo = suggestionScore({ validation_result: 'block', length: 0, match_ratio: 0, reasons: [] });
    expect(lo).toBeGreaterThanOrEqual(0);
    expect(suggestionScore(base)).toBeLessThanOrEqual(100);
  });
  it('색 구간', () => {
    expect([scoreTone(90), scoreTone(60), scoreTone(10)]).toEqual(['success', 'warning', 'danger']);
  });
});
