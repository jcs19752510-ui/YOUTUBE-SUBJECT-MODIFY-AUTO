import { describe, expect, it } from 'vitest';

const files = import.meta.glob(
  [
    '../**/*.ts',
    '../**/*.tsx',
    '../**/*.css',
    '!../**/*.test.ts',
    '!../**/*.test.tsx',
    '!../test/**',
  ],
  {
    query: '?raw',
    import: 'default',
    eager: true,
  },
) as Record<string, string>;

describe('보안·정책 소스 규칙(정적 점검)', () => {
  const entries = Object.entries(files);
  it('TC-WF-080 점검 대상 소스를 찾았다(빈 점검 방지)', () => {
    expect(entries.length).toBeGreaterThan(30);
  });

  it('TC-WF-081 dangerouslySetInnerHTML·innerHTML·인라인 style 속성을 쓰지 않는다', () => {
    const bad = entries
      .filter(([, s]) => /dangerouslySetInnerHTML|\.innerHTML|\sstyle=\{/.test(s))
      .map(([f]) => f);
    expect(bad).toEqual([]);
  });

  it('TC-WF-082 localStorage/sessionStorage 를 쓰지 않는다(CSRF 토큰은 메모리에만)', () => {
    const bad = entries.filter(([, s]) => /localStorage|sessionStorage/.test(s)).map(([f]) => f);
    expect(bad).toEqual([]);
  });

  it('TC-WF-083 외부 주소(CDN·원격 폰트·분석)를 참조하지 않는다', () => {
    const bad = entries
      .filter(([, s]) => /https?:\/\/(?!localhost|127\.0\.0\.1)/.test(s.replace(/\/\/.*$/gm, '')))
      .map(([f]) => f);
    expect(bad).toEqual([]);
  });

  it('TC-WF-084 화면에 "dry-run" 용어를 그대로 쓰지 않는다(미리보기로 표기)', () => {
    const bad = entries
      .filter(([f, s]) => f.includes('i18n') && /dry-?run/i.test(s.replace(/\/\/.*$/gm, '')))
      .map(([f]) => f);
    expect(bad).toEqual([]);
  });

  it('TC-WF-085 글자 크기를 16px(1rem) 미만으로 지정하지 않는다', () => {
    const small = entries
      .filter(
        ([f, s]) => f.endsWith('.css') && /font-size:\s*(0?\.\d+rem|1[0-5]px|\d{1}px)/.test(s),
      )
      .map(([f]) => f);
    expect(small).toEqual([]);
  });
});
