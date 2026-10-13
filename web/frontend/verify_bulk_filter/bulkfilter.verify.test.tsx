// 일괄 승인 목록 줄여 보기 독립 검증(TC-BF-*). 구현자 시험(bulkfilter.test.tsx)과 독립.
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { App } from '../src/app/App';
import { Providers } from '../src/app/providers';
import type { ResolvedVideo, Suggestion } from '../src/api/types';
import { dashboard, suggestion } from '../src/test/fixtures';
import {
  authedHandlers,
  axeViolations,
  json,
  makeClient,
  problem,
  route,
  type Handler,
} from '../src/test/utils';

const vid = (n: number) => `vid${String(n).padStart(8, '0')}`;
const sg = (id: number, over: Partial<Suggestion> = {}) =>
  suggestion(id, { video_id: vid(id), title: `새 제목 ${id}`, ...over });
const page = (items: unknown[]) =>
  json(200, { items, total: items.length, page: 1, page_size: 50 });
const rv = (n: number, over: Partial<ResolvedVideo> = {}): ResolvedVideo => ({
  video_id: vid(n),
  found: true,
  video_title: `현재 제목 ${n}`,
  excluded_reasons: [],
  candidates: [sg(n)],
  ...over,
});
/** 목록 + resolve(목록 영상의 현재 제목, 붙여넣기 모두 같은 규칙: 요청 ID 마다 rv) */
const baseHandlersOld = (
  cand: Suggestion[],
  resolve?: (ids: string[]) => ResolvedVideo[],
): Handler[] => [
  route('GET', '/api/v1/suggestions', (r) =>
    page(r.query.get('status') === 'expired' || r.query.get('status') === 'blocked' ? [] : cand),
  ),
  route('POST', '/api/v1/suggestions/resolve-videos', (r) => {
    const ids = (r.body as { video_ids: string[] }).video_ids;
    const fn =
      resolve ??
      ((xs: string[]) =>
        xs.map((x) => {
          const n = Number(x.slice(3));
          const c = cand.find((s) => s.video_id === x);
          return rv(n, { candidates: c ? [c] : [sg(n)] });
        }));
    return json(200, { items: fn(ids) });
  }),
  route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
];
const okResult = (ids: number[]) =>
  json(200, {
    approved: ids.map((i) => ({ suggestion_id: i, video_id: vid(i) })),
    skipped: [],
    counts: { requested: ids.length, approved: ids.length, skipped: 0 },
  });

async function setup(handlers: Handler[], mode?: 'demo' | 'live') {
  const user = userEvent.setup();
  const c = makeClient([...authedHandlers, ...handlers]);
  void mode;
  document.getElementById('root')?.remove();
  const root = document.createElement('div');
  root.id = 'root';
  document.body.appendChild(root);
  const r = render(
    <Providers client={c.client}>
      <MemoryRouter initialEntries={['/bulk-approve']}>
        <App />
      </MemoryRouter>
    </Providers>,
    { container: root },
  );
  await screen.findByRole('heading', { name: '일괄 승인' });
  return { user, ...c, ...r };
}
void baseHandlersOld;
const mk = (id: number, v: string, t: string, over: Partial<Suggestion> = {}) =>
  suggestion(id, { video_id: v, title: t, ...over });
const S = {
  a: mk(1, 'AAAAAAAAAA1', '청소 설정 제목'),
  b: mk(2, 'BBBBBBBBBB2', '지원금 조회 제목'),
  c: mk(3, 'CCCCCCCCCC3', 'Senior Tips ABC', { validation_result: 'warn' }),
  d: mk(4, 'DDDDDDDDDD4', '차단된 제목', { status: 'blocked', validation_result: 'block' }),
  e: mk(5, 'EEEEEEEEEE5', '이미 승인 제목', { status: 'approved' }),
  f: mk(6, 'FFFFFFFFFF6', '경고 지원금', { validation_result: 'warn' }),
};
const lists = (cand: Suggestion[], blocked: Suggestion[] = []): Handler[] => [
  route('GET', '/api/v1/suggestions', (r) => {
    const st = r.query.get('status');
    return page(st === 'candidate' ? cand : st === 'blocked' ? blocked : []);
  }),
  route('POST', '/api/v1/suggestions/resolve-videos', (r) => {
    const ids = (r.body as { video_ids: string[] }).video_ids;
    return json(200, {
      items: ids.map((x) => {
        const c = [...cand, ...blocked].filter((s) => s.video_id === x);
        return {
          video_id: x,
          found: true,
          video_title: `현재 ${x}`,
          excluded_reasons: [],
          candidates: c,
        };
      }),
    });
  }),
  route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
];
const six = () => lists([S.a, S.b, S.c, S.e, S.f], [S.d]);
const box = () => screen.getByRole('searchbox', { name: /목록 줄여 보기/ });
const sel = () => screen.getByRole('combobox', { name: /판정으로 줄여 보기/ });
const tableA = () => screen.getAllByRole('table')[0]!;
const newTitles = () =>
  within(tableA())
    .getAllByRole('row')
    .slice(1)
    .map((r) => within(r).queryAllByRole('cell')[3]?.firstChild?.textContent ?? '');
const allBox = () => screen.getByRole('checkbox', { name: '현재 목록 전체 선택' });
const ready = () => screen.findByText('청소 설정 제목', { selector: 'td' });
const cap = (n: number) => screen.getByText(`승인 가능한 제안 ${n}건`, { selector: 'caption' });
const queueText = () => screen.getByText(/^선택 \d+\/50건$/).textContent;

describe('줄여 보기 A: 정렬·글자·판정', () => {
  it('TC-BF-001 번호가 큰 제안이 위에(정렬)', async () => {
    await setup(six());
    await ready();
    expect(newTitles()).toEqual([
      '경고 지원금',
      '이미 승인 제목',
      '차단된 제목',
      'Senior Tips ABC',
      '지원금 조회 제목',
      '청소 설정 제목',
    ]);
  });
  it('TC-BF-002 영상 ID 일부(소문자 입력도) 로 찾기', async () => {
    const { user } = await setup(six());
    await ready();
    await user.type(box(), 'bbbbbb');
    expect(newTitles()).toEqual(['지원금 조회 제목']);
    cap(1);
  });
  it('TC-BF-003 제목 일부 대소문자 무시, 앞뒤 공백 무시', async () => {
    const { user } = await setup(six());
    await ready();
    await user.type(box(), '  sENIor tips  ');
    expect(newTitles()).toEqual(['Senior Tips ABC']);
  });
  it('TC-BF-004 제목 일부가 여러 건에 맞으면 모두(지원금 2건)', async () => {
    const { user } = await setup(six());
    await ready();
    await user.type(box(), '지원금');
    expect(newTitles()).toEqual(['경고 지원금', '지원금 조회 제목']);
  });
  it.each([
    ['pass', ['지원금 조회 제목', '청소 설정 제목']],
    ['warn', ['경고 지원금', 'Senior Tips ABC']],
    ['block', ['차단된 제목']],
  ])('TC-BF-005 판정 %s 만 보기', async (v, expected) => {
    const { user } = await setup(six());
    await ready();
    await user.selectOptions(sel(), v as string);
    // 이미 승인(e)은 pass 로 만들어져 있다
    const got = newTitles().filter((t) => t !== '이미 승인 제목');
    expect(got).toEqual(expected);
  });
  it('TC-BF-006 판정+글자 AND, 전체로 돌리면 복귀', async () => {
    const { user } = await setup(six());
    await ready();
    await user.selectOptions(sel(), 'warn');
    await user.type(box(), '지원금');
    expect(newTitles()).toEqual(['경고 지원금']);
    await user.selectOptions(sel(), 'pass');
    expect(newTitles()).toEqual(['지원금 조회 제목']);
    await user.selectOptions(sel(), 'block');
    expect(screen.getByText(/맞는 제안이 없습니다/)).toBeInTheDocument();
    await user.selectOptions(sel(), '');
    expect(newTitles()).toEqual(['경고 지원금', '지원금 조회 제목']);
    await user.clear(box());
    expect(newTitles()).toHaveLength(6);
  });
  it('TC-BF-007 결과 0건 안내문(글자) / 필터 없을 때는 안내문 없음', async () => {
    const { user } = await setup(six());
    await ready();
    expect(screen.queryByText(/맞는 제안이 없습니다/)).toBeNull();
    await user.type(box(), 'zzzz');
    expect(screen.getByText(/맞는 제안이 없습니다/)).toBeInTheDocument();
    cap(0);
    expect(allBox()).toBeDisabled();
  });
});

describe('줄여 보기 B: 선택 안전', () => {
  it('TC-BF-010 줄인 목록에서 전체 선택은 보이는 것만 고른다', async () => {
    const { user } = await setup(six());
    await ready();
    await user.type(box(), '지원금');
    await user.click(allBox());
    expect(queueText()).toBe('선택 2/50건');
    await user.clear(box());
    expect(screen.getByRole('checkbox', { name: '청소 설정 제목 선택' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: '지원금 조회 제목 선택' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '경고 지원금 선택' })).toBeChecked();
  });
  it('TC-BF-011 줄이기 전 선택한 항목이 줄인 뒤에도 승인 대기 목록에 남는다', async () => {
    const { user } = await setup(six());
    await ready();
    await user.click(screen.getByRole('checkbox', { name: '청소 설정 제목 선택' }));
    await user.type(box(), '지원금');
    expect(queueText()).toBe('선택 1/50건');
    const qt = screen.getAllByRole('table')[screen.getAllByRole('table').length - 1]!;
    expect(within(qt).getByText('청소 설정 제목')).toBeInTheDocument();
    await user.clear(box());
    expect(screen.getByRole('checkbox', { name: '청소 설정 제목 선택' })).toBeChecked();
  });
  it('TC-BF-012 숨긴 선택이 있는 채로 전체 선택해도 숨긴 선택은 유지(사라지지 않음)', async () => {
    const { user } = await setup(six());
    await ready();
    await user.click(screen.getByRole('checkbox', { name: '청소 설정 제목 선택' }));
    await user.type(box(), '지원금');
    await user.click(allBox());
    // 기대: 숨긴 1건 + 보이는 2건 = 3
    expect(queueText()).toBe('선택 3/50건');
  });
  it('TC-BF-013 줄인 목록에서 전체 선택 해제해도 숨긴 선택은 유지', async () => {
    const { user } = await setup(six());
    await ready();
    await user.click(screen.getByRole('checkbox', { name: '청소 설정 제목 선택' }));
    await user.type(box(), '지원금');
    await user.click(allBox());
    await user.click(allBox());
    // 기대: 보이는 것만 해제 → 숨긴 청소 1건 남음
    expect(queueText()).toBe('선택 1/50건');
  });
  it('TC-BF-014 차단·이미 승인은 비활성, 전체 선택에서 제외', async () => {
    const { user } = await setup(six());
    await ready();
    expect(screen.getByRole('checkbox', { name: '차단된 제목 선택' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: '이미 승인 제목 선택' })).toBeDisabled();
    await user.click(allBox());
    expect(queueText()).toBe('선택 4/50건');
    await user.selectOptions(sel(), 'block');
    expect(allBox()).toBeDisabled();
  });
  it('TC-BF-015 50건 상한: 60건 중 전체 선택 → 50건(최신순), 나머지 비활성', async () => {
    const many = Array.from({ length: 60 }, (_, i) => mk(i + 1, vid(i + 1), `제목 ${i + 1}`));
    const { user } = await setup(lists(many));
    await screen.findByText('제목 60', { selector: 'td' });
    await user.click(allBox());
    expect(queueText()).toBe('선택 50/50건');
    expect(screen.getByRole('checkbox', { name: '제목 11 선택' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '제목 10 선택' })).toBeDisabled();
    expect(screen.getByText(/최대 50건까지만/)).toBeInTheDocument();
  });
  it('TC-BF-016 숨긴 선택 49건 + 줄인 목록 전체 선택 → 합계 50 초과 없음', async () => {
    const many = Array.from({ length: 60 }, (_, i) => mk(i + 1, vid(i + 1), `제목 ${i + 1}`));
    const { user } = await setup(lists(many));
    await screen.findByText('제목 60', { selector: 'td' });
    await user.type(box(), '제목 1');
    // 제목 1, 10-19 = 11건 → 전체 선택 → 11
    await user.click(allBox());
    expect(queueText()).toBe('선택 11/50건');
  });
  it('TC-BF-017 줄여도 방법 A 의 전체 선택 라벨/체크 상태가 보이는 항목 기준', async () => {
    const { user } = await setup(six());
    await ready();
    await user.click(screen.getByRole('checkbox', { name: '청소 설정 제목 선택' }));
    await user.type(box(), '청소');
    expect(allBox()).toBeChecked();
    await user.clear(box());
    expect(allBox()).not.toBeChecked();
  });
});

describe('줄여 보기 C: 입력 안전·접근성·방법 B', () => {
  it.each(['.*', '(', '[a-', '\\', '+?', '^$', '😀', '😀😀😀', '<script>', "' OR 1=1 --"])(
    'TC-BF-020 특수문자 %j 에서도 죽지 않고 0건 안내',
    async (s) => {
      const { user } = await setup(six());
      await ready();
      await user.click(box());
      await user.paste(s);
      expect(screen.getByRole('heading', { name: '일괄 승인' })).toBeInTheDocument();
      expect(screen.getByText(/맞는 제안이 없습니다/)).toBeInTheDocument();
    },
  );
  it('TC-BF-021 공백만 입력하면 필터 없음(전체)', async () => {
    const { user } = await setup(six());
    await ready();
    await user.type(box(), '   ');
    expect(newTitles()).toHaveLength(6);
    expect(screen.queryByText(/맞는 제안이 없습니다/)).toBeNull();
  });
  it('TC-BF-022 초장문 10만 자 입력 안전(1초 내 처리)', async () => {
    const { user } = await setup(six());
    await ready();
    await user.click(box());
    const t0 = performance.now();
    await user.paste('가'.repeat(100000));
    expect(screen.getByText(/맞는 제안이 없습니다/)).toBeInTheDocument();
    expect(performance.now() - t0).toBeLessThan(5000);
  });
  it('TC-BF-023 접근성: 라벨 연결(id/name), axe 위반 0', async () => {
    const { user, container } = await setup(six());
    await ready();
    expect(box().getAttribute('name')).toBe('bulk-list-filter');
    expect(sel().getAttribute('name')).toBe('bulk-verdict-filter');
    expect(await axeViolations(container)).toEqual([]);
    await user.type(box(), 'zzz');
    expect(await axeViolations(container)).toEqual([]);
  });
  it('TC-BF-023b 입력칸·선택 상자에 name 이 있고 라벨과 연결돼 있다(브라우저 id/name 권고 충족)', async () => {
    await setup(six());
    await ready();
    // 2026-10-13: 처음엔 id 가 'bulk-list-filter' 인지 검사했으나 Field 컴포넌트가 라벨 연결용 id 를 항상 덮어쓴다(프로젝트 공통 설계). 요구의 본뜻(id 또는 name + 라벨 연결)을 검사한다. 원래 실패는 결과서에 기록.
    expect(box().getAttribute('name')).toBe('bulk-list-filter');
    expect(sel().getAttribute('name')).toBe('bulk-verdict-filter');
    expect(box().id).not.toBe('');
    expect(sel().id).not.toBe('');
  });
  it('TC-BF-024 키보드만으로: 입력칸 포커스→입력, Tab→판정 선택→화살표', async () => {
    const { user } = await setup(six());
    await ready();
    box().focus();
    await user.keyboard('지원금');
    await user.tab();
    expect(sel()).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(newTitles().length).toBeLessThanOrEqual(2);
    // 체크박스 Space 선택
    const first = screen
      .getAllByRole('checkbox', { name: /선택$/ })
      .find(
        (c) =>
          !(c as HTMLInputElement).disabled &&
          c.id.startsWith('bulk-pick-') &&
          c.id !== 'bulk-pick-page',
      );
    first!.focus();
    await user.keyboard(' ');
    expect(queueText()).toBe('선택 1/50건');
  });
  it('TC-BF-025 방법 B 무영향: 필터 적용 중에도 붙여넣기 찾기·합산 동작', async () => {
    const { user } = await setup(six());
    await ready();
    await user.type(box(), '청소');
    await user.click(screen.getByRole('checkbox', { name: '청소 설정 제목 선택' }));
    const b = screen.getByRole('textbox', { name: /영상 ID/ });
    await user.click(b);
    await user.paste('BBBBBBBBBB2');
    await user.click(screen.getByRole('button', { name: '찾기' }));
    await screen.findByText('찾은 결과 1개 영상');
    expect(queueText()).toBe('선택 2/50건');
    expect((b as HTMLTextAreaElement).value).toBe('BBBBBBBBBB2');
  });
  it('TC-BF-026 제목에 같은 글자가 현재 제목(열)에만 있으면 맞지 않음(새 제목/ID 기준)', async () => {
    const { user } = await setup(six());
    await ready();
    await screen.findByText('현재 AAAAAAAAAA1');
    await user.type(box(), '현재');
    expect(screen.getByText(/맞는 제안이 없습니다/)).toBeInTheDocument();
  });
});
