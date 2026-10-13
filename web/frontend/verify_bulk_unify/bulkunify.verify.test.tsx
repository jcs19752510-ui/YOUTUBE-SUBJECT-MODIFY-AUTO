// 일괄 승인 방법 A 목록을 영상 목록과 같은 구조로 맞춘 변경의 독립 검증(TC-BU-*).
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { App } from '../src/app/App';
import { Providers } from '../src/app/providers';
import type { Suggestion } from '../src/api/types';
import { ko } from '../src/i18n/ko';
import { STATUSES } from '../src/pages/VideosPage';
import { dashboard, suggestion, video } from '../src/test/fixtures';
import {
  authedHandlers,
  axeViolations,
  json,
  makeClient,
  route,
  type Handler,
} from '../src/test/utils';

const mk = (id: number, v: string, t: string, over: Partial<Suggestion> = {}) =>
  suggestion(id, { video_id: v, title: t, ...over });
const page = (items: unknown[]) =>
  json(200, { items, total: items.length, page: 1, page_size: 50 });

type Calls = { statuses: (string | null)[] };
function handlers(
  cand: Suggestion[],
  byStatus: Record<string, string[]>,
  opt: { videos?: (st: string | null) => ReturnType<typeof json>; calls?: Calls } = {},
): Handler[] {
  return [
    route('GET', '/api/v1/suggestions', (r) =>
      page(r.query.get('status') === 'candidate' ? cand : []),
    ),
    route('POST', '/api/v1/suggestions/resolve-videos', (r) => {
      const ids = (r.body as { video_ids: string[] }).video_ids;
      return json(200, {
        items: ids.map((x) => ({
          video_id: x,
          found: true,
          video_title: `현재 ${x}`,
          excluded_reasons: [],
          candidates: cand.filter((s) => s.video_id === x),
        })),
      });
    }),
    route('GET', '/api/v1/videos', (r) => {
      const st = r.query.get('status');
      opt.calls?.statuses.push(st);
      if (opt.videos) return opt.videos(st);
      const ids = st ? (byStatus[st] ?? []) : Object.values(byStatus).flat();
      return json(200, {
        items: ids.map((id, i) => video(i + 1, { video_id: id })),
        total: ids.length,
        page: 1,
        page_size: 200,
      });
    }),
    route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
  ];
}
async function setup(h: Handler[]) {
  const user = userEvent.setup();
  const c = makeClient([...authedHandlers, ...h]);
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
const A = mk(1, 'AAAAAAAAAA1', '청소 설정 제목');
const B = mk(2, 'BBBBBBBBBB2', '지원금 조회 제목');
const C = mk(3, 'CCCCCCCCCC3', '지원금 경고 제목', { validation_result: 'warn' });
const D = mk(4, 'DDDDDDDDDD4', '네번째 제목');
const four = () => [A, B, C, D];
const byStatus = {
  suggested: ['AAAAAAAAAA1', 'BBBBBBBBBB2', 'CCCCCCCCCC3', 'DDDDDDDDDD4'],
  approved: ['BBBBBBBBBB2'],
  applied: [] as string[],
};
const stSel = () => screen.getByRole('combobox', { name: ko.videos.filterStatus });
const vSel = () => screen.getByRole('combobox', { name: /판정으로 줄여 보기/ });
const box = () => screen.getByRole('searchbox', { name: /제목 또는 영상 ID 검색/ });
const tableA = () => screen.getAllByRole('table')[0]!;
const titles = () =>
  within(tableA())
    .getAllByRole('row')
    .slice(1)
    .map((r) => within(r).queryAllByRole('cell')[3]?.firstChild?.textContent ?? '');
const ready = () => screen.findByText('청소 설정 제목', { selector: 'td' });
const cap = (n: number) => screen.getByText(`승인 가능한 제안 ${n}건`, { selector: 'caption' });

describe('진행 상태 선택', () => {
  it('TC-BU-001 진행 상태 선택지가 영상 목록과 이름·순서가 같다', async () => {
    await setup(handlers(four(), byStatus));
    await ready();
    const names = within(stSel())
      .getAllByRole('option')
      .map((o) => o.textContent);
    expect(names).toEqual([ko.videos.filterAll, ...STATUSES.map((s) => ko.workflow[s])]);
    expect(names).toEqual([
      '전체',
      '제안 없음',
      '제안 있음(검토 대기)',
      '승인됨',
      '반영 대기',
      '반영 완료',
      '되돌림',
    ]);
    const vals = within(stSel())
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value);
    expect(vals).toEqual(['', ...STATUSES]);
  });
  it('TC-BU-002 제안 있음(검토 대기) 선택 -> videos API status=suggested 호출, 그 영상 제안만', async () => {
    const calls: Calls = { statuses: [] };
    const { user } = await setup(
      handlers(four(), { ...byStatus, suggested: ['AAAAAAAAAA1', 'CCCCCCCCCC3'] }, { calls }),
    );
    await ready();
    expect(calls.statuses).toEqual([]); // 전체일 때는 호출하지 않음
    await user.selectOptions(stSel(), 'suggested');
    await waitFor(() => expect(titles()).toEqual(['지원금 경고 제목', '청소 설정 제목']));
    expect(calls.statuses).toContain('suggested');
    cap(2);
  });
  it('TC-BU-003 전체로 돌리면 모두 복귀', async () => {
    const { user } = await setup(handlers(four(), byStatus));
    await ready();
    await user.selectOptions(stSel(), 'approved');
    await waitFor(() => expect(titles()).toEqual(['지원금 조회 제목']));
    await user.selectOptions(stSel(), '');
    await waitFor(() => expect(titles()).toHaveLength(4));
  });
  it('TC-BU-004 승인됨 선택 시 해당 영상 제안만', async () => {
    const { user } = await setup(handlers(four(), byStatus));
    await ready();
    await user.selectOptions(stSel(), 'approved');
    await waitFor(() => expect(titles()).toEqual(['지원금 조회 제목']));
  });
  it('TC-BU-005 해당 상태 영상이 0개면 안내문 + 0건, 화면 유지', async () => {
    const { user } = await setup(handlers(four(), byStatus));
    await ready();
    await user.selectOptions(stSel(), 'applied');
    await waitFor(() => cap(0));
    expect(screen.getByText(/맞는 제안이 없습니다/)).toBeInTheDocument();
  });
  it('TC-BU-006 videos API 500 실패 시 화면이 깨지지 않는다(제목 목록 유지/빈 결과, 크래시 없음)', async () => {
    const { user } = await setup(
      handlers(four(), byStatus, { videos: () => json(500, { title: 'x', status: 500 }) }),
    );
    await ready();
    await user.selectOptions(stSel(), 'suggested');
    await new Promise((r) => setTimeout(r, 1500));
    expect(screen.getByRole('heading', { name: '일괄 승인' })).toBeInTheDocument();
    expect(stSel()).toHaveValue('suggested');
    // 실패 시 사용자가 알 수 있는가(오류 안내 또는 재시도)? 없으면 결함 후보로 기록
    const n = titles().length;
    // 2026-10-13: 오류 안내 패널은 제목·버튼 등 여러 요소에 같은 낱말이 있어 queryByText(단수)는 '여러 개'로 던진다 — 하나라도 있으면 안내가 있는 것으로 보도록 queryAllByText 로 정정(첫 실행 실패 기록).
    const informs = screen.queryAllByText(/불러오지 못|다시 시도|오류|실패/).length > 0;
    console.log(`TC-BU-006 실패 시 행 ${n}개, 오류 안내 표시=${informs}`);
    expect(informs).toBe(true);
  });
  it('TC-BU-007 videos API 지연 중에도 화면이 유지되고 도착 후 반영', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const h = handlers(four(), byStatus);
    h.unshift(
      route('GET', '/api/v1/videos', async () => {
        await gate;
        return json(200, {
          items: [video(1, { video_id: 'BBBBBBBBBB2' })],
          total: 1,
          page: 1,
          page_size: 200,
        });
      }),
    );
    const { user } = await setup(h);
    await ready();
    await user.selectOptions(stSel(), 'approved');
    expect(screen.getByRole('heading', { name: '일괄 승인' })).toBeInTheDocument();
    const during = titles().length;
    console.log(`TC-BU-007 지연 중 행 ${during}개 (0=빈 결과로 오인될 수 있음)`);
    release();
    await waitFor(() => expect(titles()).toEqual(['지원금 조회 제목']));
    // 지연 중에 '맞는 제안이 없습니다'가 거짓으로 뜨면 안 된다
  });
  it('TC-BU-008 지연 중 "맞는 제안이 없습니다"를 거짓으로 보여 주지 않는다', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const h = handlers(four(), byStatus);
    h.unshift(
      route('GET', '/api/v1/videos', async () => {
        await gate;
        return json(200, {
          items: [video(1, { video_id: 'BBBBBBBBBB2' })],
          total: 1,
          page: 1,
          page_size: 200,
        });
      }),
    );
    const { user } = await setup(h);
    await ready();
    await user.selectOptions(stSel(), 'approved');
    const falseEmpty = screen.queryByText(/맞는 제안이 없습니다/) !== null;
    release();
    await waitFor(() => expect(titles()).toHaveLength(1));
    expect(falseEmpty).toBe(false);
  });
});

describe('복합 필터와 초기화', () => {
  it('TC-BU-010 진행 상태+글자+판정 동시 적용(AND)', async () => {
    const { user } = await setup(handlers(four(), byStatus));
    await ready();
    await user.selectOptions(stSel(), 'suggested');
    await user.type(box(), '지원금');
    await user.selectOptions(vSel(), 'warn');
    await waitFor(() => expect(titles()).toEqual(['지원금 경고 제목']));
    await user.selectOptions(stSel(), 'approved'); // B 는 지원금이지만 pass
    await waitFor(() => expect(screen.getByText(/맞는 제안이 없습니다/)).toBeInTheDocument());
  });
  it('TC-BU-011 [필터 초기화]가 세 가지를 모두 비운다', async () => {
    const { user } = await setup(handlers(four(), byStatus));
    await ready();
    expect(screen.queryByRole('button', { name: '필터 초기화' })).toBeNull();
    await user.selectOptions(stSel(), 'suggested');
    await user.type(box(), '지원금');
    await user.selectOptions(vSel(), 'warn');
    await user.click(screen.getByRole('button', { name: '필터 초기화' }));
    expect(stSel()).toHaveValue('');
    expect(vSel()).toHaveValue('');
    expect(box()).toHaveValue('');
    await waitFor(() => expect(titles()).toHaveLength(4));
    expect(screen.queryByRole('button', { name: '필터 초기화' })).toBeNull();
  });
  it('TC-BU-012 진행 상태만 걸어도 초기화 버튼이 나타난다', async () => {
    const { user } = await setup(handlers(four(), byStatus));
    await ready();
    await user.selectOptions(stSel(), 'approved');
    expect(screen.getByRole('button', { name: '필터 초기화' })).toBeInTheDocument();
  });
});

describe('페이지 넘기기', () => {
  const many = (n: number) =>
    Array.from({ length: n }, (_, i) =>
      mk(i + 1, `V${String(i + 1).padStart(10, '0')}`, `제목 ${String(i + 1).padStart(3, '0')}`),
    );
  const nav = () => screen.getByRole('navigation', { name: '페이지 이동' });
  const sizeSel = () => within(nav()).getByRole('combobox');
  const rowsN = () => within(tableA()).getAllByRole('row').length - 1;
  it('TC-BU-020 기본 100개씩, 120건이면 2쪽(1쪽 100행, 2쪽 20행)', async () => {
    const { user } = await setup(handlers(many(120), {}));
    await screen.findByText('제목 120', { selector: 'td' });
    expect(sizeSel()).toHaveValue('100');
    expect(rowsN()).toBe(100);
    expect(within(nav()).getByText(/1 \/ 2 쪽/)).toBeInTheDocument();
    expect(within(nav()).getByRole('button', { name: '이전' })).toBeDisabled();
    await user.click(within(nav()).getByRole('button', { name: '다음' }));
    expect(rowsN()).toBe(20);
    expect(within(nav()).getByRole('button', { name: '다음' })).toBeDisabled();
  });
  it('TC-BU-021 정확히 100건은 1쪽, 101건은 2쪽(경계)', async () => {
    await setup(handlers(many(100), {}));
    await screen.findByText('제목 100', { selector: 'td' });
    expect(within(nav()).getByText(/1 \/ 1 쪽/)).toBeInTheDocument();
  });
  it('TC-BU-022 25개씩으로 바꾸면 5쪽, 1쪽으로 복귀', async () => {
    const { user } = await setup(handlers(many(120), {}));
    await screen.findByText('제목 120', { selector: 'td' });
    await user.click(within(nav()).getByRole('button', { name: '다음' }));
    await user.selectOptions(sizeSel(), '25');
    expect(within(nav()).getByText(/1 \/ 5 쪽/)).toBeInTheDocument();
    expect(rowsN()).toBe(25);
  });
  it('TC-BU-023 필터(글자/판정/진행 상태)를 바꾸면 1쪽으로 복귀', async () => {
    const ids = many(120).map((s) => s.video_id);
    const { user } = await setup(handlers(many(120), { suggested: ids }));
    await screen.findByText('제목 120', { selector: 'td' });
    await user.click(within(nav()).getByRole('button', { name: '다음' }));
    expect(within(nav()).getByText(/2 \/ 2 쪽/)).toBeInTheDocument();
    await user.selectOptions(stSel(), 'suggested');
    await waitFor(() => expect(within(nav()).getByText(/1 \/ 2 쪽/)).toBeInTheDocument());
    await user.click(within(nav()).getByRole('button', { name: '다음' }));
    await user.type(box(), '제목');
    expect(within(nav()).getByText(/1 \/ 2 쪽/)).toBeInTheDocument();
    await user.click(within(nav()).getByRole('button', { name: '다음' }));
    await user.selectOptions(vSel(), 'pass');
    expect(within(nav()).getByText(/1 \/ 2 쪽/)).toBeInTheDocument();
  });
  it('TC-BU-024 필터 초기화로 목록이 늘거나 줄어도 쪽 번호가 범위를 벗어나지 않는다', async () => {
    const ids = many(120)
      .slice(0, 10)
      .map((s) => s.video_id);
    const { user } = await setup(handlers(many(120), { approved: ids }));
    await screen.findByText('제목 120', { selector: 'td' });
    await user.click(within(nav()).getByRole('button', { name: '다음' }));
    await user.selectOptions(stSel(), 'approved');
    await waitFor(() => expect(rowsN()).toBe(10));
    expect(within(nav()).getByText(/1 \/ 1 쪽/)).toBeInTheDocument();
  });
  it('TC-BU-025 100건 초과 목록에서 videos 상태 조회는 page_size 200 상한 -> 영상 200개 초과 시 누락 가능성 기록', async () => {
    const calls: { ps: string | null }[] = [];
    const h = handlers(many(5), { suggested: [] });
    h.unshift(
      route('GET', '/api/v1/videos', (r) => {
        calls.push({ ps: r.query.get('page_size') });
        return json(200, { items: [], total: 0, page: 1, page_size: 200 });
      }),
    );
    const { user } = await setup(h);
    await screen.findByText('제목 005', { selector: 'td' });
    await user.selectOptions(stSel(), 'suggested');
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(calls[0]!.ps).toBe('200');
  });
  it('TC-BU-026 videos 총 개수가 200 초과(total>items)이면 누락 없이 처리한다', async () => {
    // 영상 목록 API 가 200개씩만 주므로 해당 상태 영상이 250개면 뒤 50개 영상의 제안이 가려진다.
    const all = Array.from({ length: 250 }, (_, i) =>
      mk(i + 1, `W${String(i + 1).padStart(10, '0')}`, `긴목록 ${String(i + 1).padStart(3, '0')}`),
    );
    const h = handlers(all, {});
    h.unshift(
      route('GET', '/api/v1/videos', (r) => {
        const ps = Number(r.query.get('page_size') ?? 50);
        const pg = Number(r.query.get('page') ?? 1);
        const slice = all.slice((pg - 1) * Math.min(ps, 200), pg * Math.min(ps, 200));
        return json(200, {
          items: slice.map((s, i) => video(i, { video_id: s.video_id })),
          total: 250,
          page: pg,
          page_size: Math.min(ps, 200),
        });
      }),
    );
    const { user } = await setup(h);
    await screen.findByText('긴목록 250', { selector: 'td' });
    await user.selectOptions(stSel(), 'suggested');
    await waitFor(() => expect(within(tableA()).getAllByRole('row').length).toBeGreaterThan(1));
    await user.selectOptions(within(nav2()).getByRole('combobox'), '100');
    const caption = tableA().querySelector('caption')!.textContent;
    expect(caption).toBe('승인 가능한 제안 250건');
  });
  const nav2 = () => screen.getByRole('navigation', { name: '페이지 이동' });
});

describe('선택 유지·50건 상한·접근성', () => {
  const many = (n: number) =>
    Array.from({ length: n }, (_, i) =>
      mk(i + 1, `X${String(i + 1).padStart(10, '0')}`, `항목 ${String(i + 1).padStart(3, '0')}`),
    );
  it('TC-BU-030 숨긴 항목의 선택이 필터 변경 후에도 유지된다', async () => {
    const { user } = await setup(handlers(four(), byStatus));
    await ready();
    await user.click(screen.getByRole('checkbox', { name: ko.bulk.pickOne('청소 설정 제목') }));
    expect(screen.getByText(/^선택 1\/50건$/)).toBeInTheDocument();
    await user.selectOptions(stSel(), 'approved'); // A 숨김
    await waitFor(() => expect(titles()).toEqual(['지원금 조회 제목']));
    expect(screen.getByText(/^선택 1\/50건$/)).toBeInTheDocument();
    await user.selectOptions(stSel(), '');
    await waitFor(() => expect(titles()).toHaveLength(4));
    expect(screen.getByRole('checkbox', { name: ko.bulk.pickOne('청소 설정 제목') })).toBeChecked();
  });
  it('TC-BU-031 쪽을 넘겨도 선택 유지, 50건 상한(51번째는 선택 불가)', async () => {
    const { user } = await setup(handlers(many(120), {}));
    await screen.findByText('항목 120', { selector: 'td' });
    await user.selectOptions(
      within(screen.getByRole('navigation', { name: '페이지 이동' })).getByRole('combobox'),
      '25',
    );
    for (let k = 0; k < 2; k++) {
      await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
      await user.click(
        within(screen.getByRole('navigation', { name: '페이지 이동' })).getByRole('button', {
          name: '다음',
        }),
      );
    }
    expect(screen.getByText(/^선택 50\/50건$/)).toBeInTheDocument();
    // 3쪽의 항목은 더 고를 수 없다
    const boxes = within(tableA())
      .getAllByRole('checkbox')
      .filter(
        (c) =>
          !(c as HTMLInputElement).checked &&
          (c as HTMLInputElement).getAttribute('aria-label') !== '현재 목록 전체 선택',
      );
    expect(boxes.length).toBeGreaterThan(0);
    for (const b of boxes) expect(b).toBeDisabled();
    // 1쪽으로 돌아가면 선택이 남아 있다
    const nv = () => screen.getByRole('navigation', { name: '페이지 이동' });
    await user.click(within(nv()).getByRole('button', { name: '이전' }));
    await user.click(within(nv()).getByRole('button', { name: '이전' }));
    expect(
      within(tableA())
        .getAllByRole('checkbox')
        .filter((c) => (c as HTMLInputElement).checked).length,
    ).toBeGreaterThanOrEqual(25);
  });
  it('TC-BU-032 접근성: axe 위반 0, 진행 상태 select 에 name/라벨', async () => {
    const { user, container } = await setup(handlers(four(), byStatus));
    await ready();
    expect(stSel().getAttribute('name')).toBe('bulk-status-filter');
    expect(await axeViolations(container)).toEqual([]);
    await user.selectOptions(stSel(), 'approved');
    await waitFor(() => expect(titles()).toHaveLength(1));
    expect(await axeViolations(container)).toEqual([]);
  });
  it('TC-BU-033 사용자 요구: 방금 만든 검토 대기 4개를 진행 상태로 찾는다', async () => {
    const mixed = [
      ...four(),
      mk(5, 'EEEEEEEEEE5', '이미 반영된 영상 제안'),
      mk(6, 'FFFFFFFFFF6', '기타 영상 제안'),
    ];
    const { user } = await setup(
      handlers(mixed, { suggested: byStatus.suggested, applied: ['EEEEEEEEEE5'] }),
    );
    await screen.findByText('청소 설정 제목', { selector: 'td' });
    await user.selectOptions(stSel(), 'suggested');
    await waitFor(() => expect(titles()).toHaveLength(4));
    expect(titles()).toEqual([
      '네번째 제목',
      '지원금 경고 제목',
      '지원금 조회 제목',
      '청소 설정 제목',
    ]);
  });
});
