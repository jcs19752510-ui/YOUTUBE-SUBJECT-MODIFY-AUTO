// 06단계 독립 검증(TC-VF) — 제목 비교(diff) 유틸, 검증 배지 매핑, 서식 함수
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TitleDiff } from '../src/components/TitleDiff';
import { ValidationBadge } from '../src/components/ValidationBadge';
import { diffTitles, type DiffPart } from '../src/lib/diff';
import { charCount, fmtDate, fmtDateTime, fmtDuration, fmtNum, fmtPct } from '../src/lib/format';
import { isBatchActive, jobPhase } from '../src/lib/labels';

const TOK = /\s+|\S+/g;
const before = (p: DiffPart[]) =>
  p
    .filter((x) => x.type !== 'ins')
    .map((x) => x.text)
    .join('');
const after = (p: DiffPart[]) =>
  p
    .filter((x) => x.type !== 'del')
    .map((x) => x.text)
    .join('');
/** 참조 구현: 같은 토큰 분할 위에서 최장 공통 부분열 길이(토큰 수) */
function lcsLen(a: string[], b: string[]): number {
  const dp = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      dp[i]![j] =
        a[i - 1] === b[j - 1] ? dp[i - 1]![j - 1]! + 1 : Math.max(dp[i - 1]![j]!, dp[i]![j - 1]!);
  return dp[a.length]![b.length]!;
}
const sameTokenCount = (p: DiffPart[]) =>
  p.filter((x) => x.type === 'same').reduce((n, x) => n + (x.text.match(TOK)?.length ?? 0), 0);
function rng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

describe('제목 비교 diffTitles (W-006)', () => {
  it('TC-VF-107 빈 문자열 경계: 둘 다 비면 빈 결과, 한쪽만 비면 전부 추가/삭제', () => {
    expect(diffTitles('', '')).toEqual([]);
    expect(diffTitles('', '새 제목')).toEqual([{ type: 'ins', text: '새 제목' }]);
    expect(diffTitles('옛 제목', '')).toEqual([{ type: 'del', text: '옛 제목' }]);
  });

  it('TC-VF-108 같은 제목은 변경 없음(same 한 덩어리)이고, 공백만 다른 제목은 공백 조각으로 구분된다', () => {
    expect(diffTitles('같은 제목 입니다', '같은 제목 입니다')).toEqual([
      { type: 'same', text: '같은 제목 입니다' },
    ]);
    const p = diffTitles('가 나', '가  나');
    expect(before(p)).toBe('가 나');
    expect(after(p)).toBe('가  나');
    expect(p.some((x) => x.type !== 'same')).toBe(true);
  });

  it('TC-VF-109 공백뿐인 입력도 잃어버리지 않는다', () => {
    const p = diffTitles('   ', ' \t ');
    expect(before(p)).toBe('   ');
    expect(after(p)).toBe(' \t ');
  });

  it.each([
    ['이모지', '오늘의 😀 영상', '오늘의 😎 영상'],
    ['ZWJ 가족 이모지', '가족 👨‍👩‍👧 여행', '가족 👨‍👩‍👦 여행'],
    ['결합 문자(e + 악센트)', 'café 맛집', 'café 맛집'],
    ['한글 자모 분해(NFD)', '한글'.normalize('NFD') + ' 제목', '한글 제목'],
    ['국기 이모지', '🇰🇷 한국 소개', '🇯🇵 한국 소개'],
    ['제로폭 공백', '제목​추가', '제목추가'],
    ['HTML 모양', '<b>굵게</b> 제목', '<i>기울임</i> 제목'],
  ])('TC-VF-110 특수 문자(%s)를 쪼개지 않고, 전/후 제목을 정확히 복원한다', (_n, a, b) => {
    const p = diffTitles(a, b);
    expect(before(p)).toBe(a);
    expect(after(p)).toBe(b);
    for (const part of p)
      expect((part.text as string & { isWellFormed(): boolean }).isWellFormed()).toBe(true); // 서로게이트 쌍이 깨지지 않음
  });

  it('TC-VF-111 무작위 400쌍(시드 고정)에서 복원 가능·빈 조각 없음·인접 같은 종류 없음·최적(LCS 길이 일치)을 만족한다', () => {
    const r = rng(20261010);
    const alpha = [
      '가',
      '나',
      '다',
      'a',
      'bc',
      ' ',
      '  ',
      '\t',
      '😀',
      '👨‍👩‍👧',
      'é',
      '​',
      '한글',
      '<b>',
      '100%',
    ];
    const mk = () =>
      Array.from(
        { length: Math.floor(r() * 14) },
        () => alpha[Math.floor(r() * alpha.length)]!,
      ).join('');
    for (let i = 0; i < 400; i++) {
      const a = mk();
      const b = mk();
      const p = diffTitles(a, b);
      expect(before(p), `before#${i}`).toBe(a);
      expect(after(p), `after#${i}`).toBe(b);
      expect(p.every((x) => x.text.length > 0)).toBe(true);
      for (let k = 1; k < p.length; k++) expect(p[k]!.type).not.toBe(p[k - 1]!.type);
      expect(sameTokenCount(p), `lcs#${i} "${a}" -> "${b}"`).toBe(
        lcsLen(a.match(TOK) ?? [], b.match(TOK) ?? []),
      );
    }
  });

  it('TC-VF-112 긴 제목(2000 단어 대 2000 단어)도 3초 안에 끝나고 복원이 정확하다', () => {
    const a = Array.from({ length: 2000 }, (_, i) => `단어${i % 97}`).join(' ');
    const b = Array.from({ length: 2000 }, (_, i) => `단어${(i * 7) % 89}`).join(' ');
    const t0 = performance.now();
    const p = diffTitles(a, b);
    const ms = performance.now() - t0;
    expect(before(p)).toBe(a);
    expect(after(p)).toBe(b);
    expect(ms).toBeLessThan(3000);
  });

  it('TC-VF-113 단어 하나가 아주 긴 제목(10만 자, 공백 없음)도 즉시 처리된다', () => {
    const a = '가'.repeat(100_000);
    const b = '나'.repeat(100_000);
    const p = diffTitles(a, b);
    expect(p).toEqual([
      { type: 'del', text: a },
      { type: 'ins', text: b },
    ]);
  });
});

describe('TitleDiff 컴포넌트', () => {
  it('TC-VF-114 글자 수는 코드포인트 기준이고 서버 문자열의 HTML 은 요소가 되지 않는다', () => {
    const { container } = render(
      <TitleDiff before="<b>옛</b> 😀😀" after="<script>alert(1)</script> 😀" />,
    );
    expect(container.querySelector('script,b')).toBeNull();
    expect(container.textContent).toContain('<script>alert(1)</script>');
    expect(charCount('😀😀')).toBe(2);
    expect(charCount('')).toBe(0);
    expect(charCount('é')).toBe(2); // 코드포인트 기준(서버 len() 과 같은 방식)
  });

  it('TC-VF-115 삭제는 "전" 쪽에만, 추가는 "후" 쪽에만 나오고 각각 스크린리더용 문구가 붙는다', () => {
    const { container } = render(<TitleDiff before="가 나 다" after="가 라 다" />);
    const texts = container.querySelectorAll('.diff__text');
    expect(texts[0]!.querySelector('del')?.textContent).toContain('나');
    expect(texts[0]!.querySelector('ins')).toBeNull();
    expect(texts[1]!.querySelector('ins')?.textContent).toContain('라');
    expect(texts[1]!.querySelector('del')).toBeNull();
    expect(container.querySelectorAll('.sr-only').length).toBeGreaterThanOrEqual(2);
  });

  it('TC-VF-116 빈 제목끼리도 오류 없이 그려진다', () => {
    const { container } = render(<TitleDiff before="" after="" />);
    expect(container.querySelector('.diff')).not.toBeNull();
  });
});

describe('검증 배지 매핑 (W-005)', () => {
  it.each([
    ['pass', '통과', '✓', 'success'],
    ['warn', '경고', '▲', 'warning'],
    ['block', '차단', '✕', 'danger'],
  ] as const)(
    'TC-VF-117 %s 는 "%s" 글자와 기호 %s, 색 계열 %s 로 표시된다',
    (r, label, icon, tone) => {
      const { container } = render(<ValidationBadge result={r} />);
      const el = container.querySelector('.badge')!;
      expect(el.textContent).toContain(label);
      expect(el.textContent).toContain(icon);
      expect(el.className).toContain(tone);
    },
  );

  it('TC-VF-118 세 판정은 서로 다른 글자·기호·색 계열을 가진다(색만으로 구분하지 않음)', () => {
    const got = (['pass', 'warn', 'block'] as const).map((r) => {
      const { container, unmount } = render(<ValidationBadge result={r} />);
      const el = container.querySelector('.badge')!;
      const v = { text: el.textContent, cls: el.className };
      unmount();
      return v;
    });
    expect(new Set(got.map((g) => g.text)).size).toBe(3);
    expect(new Set(got.map((g) => g.cls)).size).toBe(3);
  });

  it.each([[null], [undefined], ['PASS'], ['unknown'], ['']])(
    'TC-VF-119 판정이 %s 이면 "검증 전" 같은 중립 표시로 바뀌고 통과로 오인되지 않는다',
    (r) => {
      const { container } = render(<ValidationBadge result={r as never} />);
      const el = container.querySelector('.badge')!;
      expect(el.textContent).not.toMatch(/통과|✓/);
      expect(el.textContent).not.toMatch(/차단|경고/);
      expect(el.textContent!.length).toBeGreaterThan(0);
    },
  );
});

describe('서식·상태 판별 유틸', () => {
  it('TC-VF-120 시각은 한국 시간으로 보이고 자정 경계(UTC 15:00 → KST 다음 날 00:00)를 정확히 넘긴다', () => {
    expect(fmtDateTime('2026-10-09T15:00:00Z')).toBe('2026-10-10 00:00');
    expect(fmtDateTime('2026-10-09T14:59:59Z')).toBe('2026-10-09 23:59');
    expect(fmtDateTime('2026-12-31T15:00:00Z')).toBe('2027-01-01 00:00');
    expect(fmtDateTime(null)).toBe('-');
    expect(fmtDateTime('')).toBe('-');
    expect(fmtDateTime('날짜아님')).toBe('-');
  });

  it('TC-VF-121 날짜만 있는 값(YYYY-MM-DD)은 시간대 변환 없이 그대로, 시각이 있는 값은 한국 날짜로', () => {
    expect(fmtDate('2026-10-10')).toBe('2026-10-10');
    expect(fmtDate('2026-10-09T15:00:00Z')).toBe('2026-10-10');
    expect(fmtDate('2026-13-45')).toBe('2026-13-45'); // 형식만 보고 통과시킴(서버 값 그대로) — 관찰
    expect(fmtDate(undefined)).toBe('-');
    expect(fmtDate('abc')).toBe('-');
  });

  it('TC-VF-122 길이·숫자·퍼센트 경계값', () => {
    expect(fmtDuration(0)).toBe('0:00');
    expect(fmtDuration(59)).toBe('0:59');
    expect(fmtDuration(60)).toBe('1:00');
    expect(fmtDuration(3599)).toBe('59:59');
    expect(fmtDuration(null)).toBe('-');
    expect(fmtNum(0)).toBe('0');
    expect(fmtNum(1234567)).toBe('1,234,567');
    expect(fmtNum(null)).toBe('-');
    expect(fmtPct(0)).toBe('0.0%');
    expect(fmtPct(12.345, 2)).toBe('12.35%');
    expect(fmtPct(undefined)).toBe('-');
  });

  it('TC-VF-123 배치/작업 상태 판별: 끝난 상태에서는 폴링 대상이 아니고 모르는 상태는 진행 중으로 본다', () => {
    for (const s of ['draft', 'completed', 'done', 'cancelled', 'failed', 'finished'])
      expect(isBatchActive(s), s).toBe(false);
    for (const s of ['running', 'queued', 'pending', 'executing', 'weird'])
      expect(isBatchActive(s), s).toBe(true);
    expect(jobPhase({ status: 'succeeded' })).toBe('success');
    expect(jobPhase({ status: 'failed' })).toBe('failed');
    expect(jobPhase({ status: 'queued' })).toBe('active');
    expect(jobPhase({ status: 'running' })).toBe('active');
    expect(jobPhase({ status: 'SUCCEEDED' as never })).toBe('active'); // 대소문자 다르면 진행 중으로 본다 — 관찰
  });

  it('TC-VF-124 렌더 확인: ValidationBadge 가 화면 접근성 트리에 글자로 잡힌다', () => {
    render(<ValidationBadge result="block" />);
    expect(screen.getByText(/차단/)).toBeInTheDocument();
  });
});
