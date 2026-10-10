// 06단계 독립 검증(TC-VF) — 화면별 인수 조건 보강: 영상 목록 서버측 질의, 홈, 배치 만들기, 리포트 CSV, 이력 필터, 데모 배지, 미리보기 문구
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/app/App';
import { Providers } from '../src/app/providers';
import { ko } from '../src/i18n/ko';
import { dashboard, detail, draftBatch, suggestion, video } from '../src/test/fixtures';
import {
  authedHandlers,
  json,
  makeClient,
  problem,
  route,
  type Handler,
  type Req,
} from '../src/test/utils';

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

const page = <T,>(items: T[], total = items.length, p = 1, size = 50) => ({
  items,
  total,
  page: p,
  page_size: size,
});

function LocationProbe() {
  const l = useLocation();
  return <output data-testid="loc">{l.pathname + l.search}</output>;
}
function mountApp(handlers: Handler[], entry = '/') {
  const c = makeClient([...authedHandlers, ...handlers]);
  document.getElementById('root')?.remove();
  const root = document.createElement('div');
  root.id = 'root';
  document.body.appendChild(root);
  render(
    <Providers client={c.client}>
      <MemoryRouter initialEntries={[entry]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </Providers>,
    { container: root },
  );
  return c;
}
const lastGet = (calls: Req[], path: string) => [...calls].reverse().find((c) => c.path === path);

// ---------- 영상 목록: 서버측 필터·정렬·페이지 (F-03, W-003) ----------
describe('영상 목록: 서버측 질의 (F-03)', () => {
  const server = (rows = [video(1), video(2)], total = 7) =>
    route('GET', '/api/v1/videos', (req) =>
      json(
        200,
        page(
          rows,
          total,
          Number(req.query.get('page') ?? 1),
          Number(req.query.get('page_size') ?? 50),
        ),
      ),
    );

  it('TC-VF-151 화면은 서버가 준 행만 그린다(클라이언트가 자르거나 다시 정렬하지 않음) — 총 7건 중 2건이 와도 2행, 총계는 서버 값', async () => {
    mountApp([server()], '/videos?page_size=2');
    const table = await screen.findByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 2);
    expect(screen.getByText(/7/, { selector: 'caption' })).toBeInTheDocument();
  });

  it('TC-VF-152 정렬 머리글 클릭은 서버에 sort/order 를 보내고(제목 오름 → 내림), 다른 키는 오름으로 시작하며 page 는 1로 돌아간다', async () => {
    const user = userEvent.setup();
    const c = mountApp([server()], '/videos?page=3&page_size=2');
    await screen.findByRole('table');
    await user.click(screen.getByRole('button', { name: /제목/ }));
    await waitFor(() =>
      expect(lastGet(c.calls, '/api/v1/videos')?.query.get('sort')).toBe('title'),
    );
    let q = lastGet(c.calls, '/api/v1/videos')!.query;
    expect(q.get('order')).toBe('asc');
    expect(q.get('page')).toBe('1');
    await user.click(screen.getByRole('button', { name: /제목/ }));
    await waitFor(() =>
      expect(lastGet(c.calls, '/api/v1/videos')?.query.get('order')).toBe('desc'),
    );
    await user.click(screen.getByRole('button', { name: /조회수/ }));
    await waitFor(() =>
      expect(lastGet(c.calls, '/api/v1/videos')?.query.get('sort')).toBe('views'),
    );
    q = lastGet(c.calls, '/api/v1/videos')!.query;
    expect(q.get('order')).toBe('asc');
  });

  it('TC-VF-153 진행 상태·제외 필터·검색어는 서버 질의로 가고 URL 에 남으며, 필터 변경은 1쪽으로 돌린다', async () => {
    const user = userEvent.setup();
    const c = mountApp([server()], '/videos?page=2&page_size=2');
    await screen.findByRole('table');
    await user.selectOptions(screen.getByLabelText(ko.videos.filterStatus), 'approved');
    await waitFor(() =>
      expect(lastGet(c.calls, '/api/v1/videos')?.query.get('status')).toBe('approved'),
    );
    expect(lastGet(c.calls, '/api/v1/videos')!.query.get('page')).toBe('1');
    await user.selectOptions(screen.getByLabelText(ko.videos.filterExcluded), 'false');
    await waitFor(() =>
      expect(lastGet(c.calls, '/api/v1/videos')?.query.get('excluded')).toBe('false'),
    );
    await user.type(screen.getByLabelText(ko.videos.search), '  여행  {Enter}');
    await waitFor(() => expect(lastGet(c.calls, '/api/v1/videos')?.query.get('q')).toBe('여행'));
    const loc = screen.getByTestId('loc').textContent!;
    expect(loc).toContain('status=approved');
    expect(loc).toContain('excluded=false');
    expect(loc).toContain('q=');
  });

  it('TC-VF-154 쪽 이동은 page 를 서버에 보내고, 첫 쪽에서는 이전 버튼이, 마지막 쪽에서는 다음 버튼이 꺼진다(경계)', async () => {
    const user = userEvent.setup();
    const c = mountApp([server()], '/videos?page_size=2');
    await screen.findByRole('table');
    const prev = screen.getByRole('button', { name: ko.pagination.prev });
    const next = screen.getByRole('button', { name: ko.pagination.next });
    expect(prev).toBeDisabled();
    expect(next).toBeEnabled();
    await user.click(next);
    await waitFor(() => expect(lastGet(c.calls, '/api/v1/videos')?.query.get('page')).toBe('2'));
    // 총 7건, 2건씩 → 마지막 쪽은 4
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toContain('page=2'));
    for (let i = 0; i < 2; i++) {
      await user.click(screen.getByRole('button', { name: ko.pagination.next }));
    }
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toContain('page=4'));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: ko.pagination.next })).toBeDisabled(),
    );
  });

  it('TC-VF-155 쪽 크기를 바꾸면 page_size 가 서버로 가고 page 는 1로 돌아간다', async () => {
    const user = userEvent.setup();
    const c = mountApp([server()], '/videos?page=2&page_size=25');
    await screen.findByRole('table');
    await user.selectOptions(screen.getByLabelText(ko.pagination.size), '100');
    await waitFor(() =>
      expect(lastGet(c.calls, '/api/v1/videos')?.query.get('page_size')).toBe('100'),
    );
    expect(lastGet(c.calls, '/api/v1/videos')!.query.get('page')).toBe('1');
  });

  // 결함 DEF-6-007(Low): 구현 노트·URL 파서는 쪽 크기 200 까지 허용하지만 선택 목록에는 25/50/100 뿐이라, ?page_size=200 이면 200건을 받으면서 화면에는 "25개"로 보인다. 고쳐지면 .fails 를 제거할 것.
  it.fails(
    'TC-VF-156 쪽 크기 200(노트가 지원한다고 적은 값)이 선택 목록에서 실제 값으로 보인다 [DEF-6-007]',
    async () => {
      mountApp([server()], '/videos?page_size=200');
      await screen.findByRole('table');
      const sel = screen.getByLabelText(ko.pagination.size) as HTMLSelectElement;
      expect(sel.value).toBe('200');
    },
  );

  it('TC-VF-157 제외된 영상은 체크박스가 꺼져 있고 사유가 보이며, 전체 선택으로도 선택되지 않는다', async () => {
    const user = userEvent.setup();
    mountApp(
      [server([video(1), video(2, { excluded: true, exclusion_reasons: ['쇼츠 영상'] })], 2)],
      '/videos',
    );
    await screen.findByRole('table');
    expect(screen.getByRole('checkbox', { name: '테스트 영상 2 선택' })).toBeDisabled();
    expect(screen.getByText('쇼츠 영상')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: ko.videos.selectPage }));
    expect(screen.getByRole('checkbox', { name: '테스트 영상 1 선택' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '테스트 영상 2 선택' })).not.toBeChecked();
    expect(screen.getAllByText('1개 선택됨').length).toBeGreaterThan(0);
  });

  it('TC-VF-158 필터 결과가 0건이면 "필터 지우기" 안내가, 필터 없이 0건이면 첫 사용 안내가 나온다(빈 상태 구분)', async () => {
    const empty = route('GET', '/api/v1/videos', () => json(200, page([], 0)));
    mountApp([empty], '/videos?q=없는영상');
    expect(await screen.findByText(ko.videos.emptyTitle)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: ko.videos.reset }).length).toBeGreaterThan(0);
  });

  it('TC-VF-180 필터 없이 0건이면 "첫 사용" 안내(홈으로 가기)가 나오고 필터 지우기는 없다', async () => {
    const empty = route('GET', '/api/v1/videos', () => json(200, page([], 0)));
    mountApp([empty], '/videos');
    expect(await screen.findByText(ko.videos.emptyFirstTitle)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: ko.videos.reset })).toBeNull();
    expect(
      within(screen.getByRole('main')).getByRole('link', { name: ko.nav.home }),
    ).toBeInTheDocument();
  });

  it('TC-VF-159 제안 생성: 선택한 ID 로 POST suggestions/generate 를 한 번 보내고, 연타해도 한 번이다', async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const c = mountApp(
      [
        server([video(1), video(2)], 2),
        route('POST', '/api/v1/suggestions/generate', async () => {
          await gate;
          return json(202, {
            id: 'job-1',
            type: 'suggest',
            status: 'queued',
            progress: 0,
            total: 2,
            error: null,
            result: null,
          });
        }),
        route('GET', '/api/v1/jobs/job-1', () =>
          json(200, {
            id: 'job-1',
            type: 'suggest',
            status: 'succeeded',
            progress: 2,
            total: 2,
            error: null,
            result: null,
          }),
        ),
      ],
      '/videos',
    );
    await screen.findByRole('table');
    await user.click(screen.getByRole('checkbox', { name: ko.videos.selectPage }));
    const btn = screen.getByRole('button', { name: ko.videos.generate });
    await user.dblClick(btn);
    release();
    await waitFor(() =>
      expect(c.calls.filter((x) => x.path === '/api/v1/suggestions/generate')).toHaveLength(1),
    );
    const post = c.calls.find((x) => x.path === '/api/v1/suggestions/generate')!;
    expect(post.body).toEqual({ video_ids: ['vid00000001', 'vid00000002'] });
    expect(post.headers['x-csrf-token']).toBe('csrf-1');
  });
});

// ---------- 홈 (W-003 진입, F-07) ----------
describe('홈 화면', () => {
  const home = (d = dashboard()) => route('GET', '/api/v1/dashboard', () => json(200, d));

  const syncJob = (status: string, progress = 0) => ({
    id: 'j9',
    type: 'sync',
    status,
    progress,
    total: 2,
    error: null,
    result: null,
  });
  const emptyHome = () =>
    home(
      dashboard({
        counts: { videos: 0, excluded: 0, suggested: 0, approved: 0, queued: 0, applied: 0 },
      }),
    );

  it('TC-VF-160 영상 0개면 "데모 영상 불러오기" 가 할 일이고, 누르면 CSRF 와 함께 POST videos/sync 를 한 번 보낸다(응답 대기 중 연타 포함)', async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const c = mountApp(
      [
        emptyHome(),
        route('POST', '/api/v1/videos/sync', async () => {
          await gate;
          return json(202, syncJob('queued'));
        }),
        route('GET', '/api/v1/jobs/j9', () => json(200, syncJob('running', 1))),
      ],
      '/',
    );
    expect(await screen.findByText(ko.home.todoNoVideos)).toBeInTheDocument();
    await user.dblClick(await screen.findByRole('button', { name: ko.home.syncDemo }));
    release();
    await waitFor(() =>
      expect(c.calls.filter((x) => x.path === '/api/v1/videos/sync')).toHaveLength(1),
    );
    expect(c.calls.find((x) => x.path === '/api/v1/videos/sync')!.headers['x-csrf-token']).toBe(
      'csrf-1',
    );
  });

  // 결함 DEF-6-008(Low): 불러오기 작업이 진행 중인데도 "데모 영상 불러오기" 버튼이 다시 켜져 같은 작업을 또 시작할 수 있다(서버가 막아 주지 않으면 중복 작업). 고쳐지면 .fails 를 제거할 것.
  it.fails(
    'TC-VF-179 불러오기 작업이 진행 중이면 같은 버튼으로 작업을 또 시작할 수 없다 [DEF-6-008]',
    async () => {
      const user = userEvent.setup();
      const c = mountApp(
        [
          emptyHome(),
          route('POST', '/api/v1/videos/sync', () => json(202, syncJob('queued'))),
          route('GET', '/api/v1/jobs/j9', () => json(200, syncJob('running', 1))),
        ],
        '/',
      );
      await user.click(await screen.findByRole('button', { name: ko.home.syncDemo }));
      await screen.findByRole('progressbar');
      await user.click(screen.getByRole('button', { name: new RegExp(ko.home.syncDemo) }));
      await new Promise((r) => setTimeout(r, 50));
      expect(c.calls.filter((x) => x.path === '/api/v1/videos/sync')).toHaveLength(1);
    },
  );

  it.each([
    ['79%(경고 없음)', 4740, 6000, false],
    ['정확히 80%(경고)', 4800, 6000, true],
    ['100%(경고)', 6000, 6000, true],
    ['한도 0(0으로 나누기 방지, 경고 없음)', 0, 0, false],
  ])('TC-VF-161 남은 사용량 경계: %s', async (_n, used, limit, warn) => {
    mountApp([
      home(
        dashboard({
          quota: { used, limit, remaining: Math.max(0, limit - used), pt_date: '2026-10-10' },
        }),
      ),
    ]);
    await screen.findByText(ko.home.quotaTitle);
    expect(!!screen.queryByText(ko.home.quotaWarn)).toBe(warn);
  });

  it('TC-VF-162 영상 현황 숫자는 해당 필터가 걸린 영상 목록 링크이고, 할 일은 건수에 맞게 나온다', async () => {
    mountApp([home()]);
    await screen.findByText(ko.home.countsTitle);
    const link = screen.getByRole('link', { name: ko.home.counts.approved });
    expect(link).toHaveAttribute('href', '/videos?status=approved');
    expect(screen.getByRole('link', { name: ko.home.counts.excluded })).toHaveAttribute(
      'href',
      '/videos?excluded=true',
    );
    expect(screen.getByText(ko.home.todoReview(3))).toBeInTheDocument();
    expect(screen.getByText(ko.home.todoBatch(2))).toBeInTheDocument();
  });

  it('TC-VF-163 진행 중 작업이 있으면 안내가 나오고 2초마다 대시보드를 다시 읽는다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const c = mountApp([
      home(
        dashboard({
          active_job: { id: 'j1', type: 'suggest', status: 'running', progress: 1, total: 4 },
        }),
      ),
    ]);
    await screen.findByText(ko.home.todoTitle);
    const n0 = c.calls.filter((x) => x.path === '/api/v1/dashboard').length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4500);
    });
    expect(c.calls.filter((x) => x.path === '/api/v1/dashboard').length).toBeGreaterThanOrEqual(
      n0 + 2,
    );
  });
});

// ---------- 데모 배지·미리보기 문구 (F-08, M1 DEC-038) ----------
describe('데모 모드 표시와 용어', () => {
  const rich: Handler[] = [
    route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
    route('GET', '/api/v1/videos', () => json(200, page([video(1)]))),
    route('GET', '/api/v1/videos/vid00000001', () => json(200, detail([suggestion(1)]))),
    route('GET', '/api/v1/suggestions', () => json(200, page([]))),
    route('GET', '/api/v1/batches', () => json(200, page([]))),
    route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
    route('GET', '/api/v1/changes', () => json(200, page([]))),
    route('GET', '/api/v1/reports/changes', () => json(200, { items: [], notes: [] })),
    route('GET', '/api/v1/settings', () =>
      json(200, {
        daily_apply_cap: 10,
        suggestions_per_video: 3,
        tone: [],
        pin_enabled: false,
        mode: 'demo',
        read_only: { enable_live: false, live_allowlist: [], note: '' },
      }),
    ),
  ];
  it.each([
    '/',
    '/videos',
    '/videos/vid00000001',
    '/batches',
    '/batches/7',
    '/history',
    '/reports',
    '/settings',
    '/없는-주소',
  ])(
    'TC-VF-164 %s 상단에 "데모 모드" 배지가 항상 보이고, 화면 어디에도 dry-run 영문 용어가 없다',
    async (entry) => {
      mountApp(rich, entry);
      expect(
        await screen.findByText(new RegExp(ko.app.demoBadge.split(' ')[0]!)),
      ).toBeInTheDocument();
      expect(screen.getByText(/유튜브에 아무것도 전송되지 않습니다/)).toBeInTheDocument();
      expect(document.body.textContent ?? '').not.toMatch(/dry[- ]?run/i);
    },
  );

  it('TC-VF-165 배치 초안의 사전 점검 제목은 "미리보기" 로 표기되고 "아직 아무것도 반영되지 않았습니다" 안내가 있다', async () => {
    mountApp(rich, '/batches/7');
    expect(await screen.findByText(/사전 점검\(미리보기\)/)).toBeInTheDocument();
    expect(screen.getByText(/아직 아무것도 반영되지 않았습니다/)).toBeInTheDocument();
  });

  it('TC-VF-166 문구 한곳 관리: 소스의 화면 문구에 dry-run 영문이 없다(ko.ts 전체)', () => {
    expect(JSON.stringify(ko)).not.toMatch(/dry[- ]?run/i);
  });
});

// ---------- 배치 만들기 (W-008) ----------
describe('배치 만들기 화면', () => {
  const approvedRows = (n: number) =>
    Array.from({ length: n }, (_, i) =>
      suggestion(i + 1, {
        video_id: `vid${String(i + 1).padStart(8, '0')}`,
        title: `승인 제목 ${i + 1}`,
        status: 'approved',
        approval: {
          approver: '나',
          approved_at: '2026-10-10T00:00:00Z',
          expires_at: '2026-10-11T00:00:00Z',
        },
      }),
    );
  const base = (n: number, extra: Handler[] = []): Handler[] => [
    ...extra,
    route('GET', '/api/v1/suggestions', () => json(200, page(approvedRows(n), n, 1, 200))),
    route('GET', '/api/v1/batches', () => json(200, page([]))),
    route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
  ];

  it.each([
    [49, false],
    [50, false],
    [51, true],
  ])(
    'TC-VF-167 승인 항목 %i건을 전체 선택하면 초안 만들기 비활성=%s (상한 50 경계), 51건이면 하나 빼면 켜진다',
    async (n, blocked) => {
      const user = userEvent.setup();
      mountApp(base(n), '/batches');
      await user.click(await screen.findByRole('checkbox', { name: ko.batches.selectAll }));
      const create = screen.getByRole('button', { name: ko.batches.createDraft });
      expect(create.hasAttribute('disabled')).toBe(blocked);
      expect(!!screen.queryByText(ko.batches.overMax(50))).toBe(blocked);
      if (blocked) {
        await user.click(
          screen.getByRole('checkbox', { name: ko.batches.selectOne('승인 제목 51') }),
        );
        expect(create).toBeEnabled();
        expect(screen.queryByText(ko.batches.overMax(50))).toBeNull();
      }
    },
    30_000,
  );

  it('TC-VF-168 아무것도 고르지 않으면 초안 만들기가 꺼져 있다', async () => {
    mountApp(base(2), '/batches');
    await screen.findByRole('checkbox', { name: ko.batches.selectAll });
    expect(screen.getByRole('button', { name: ko.batches.createDraft })).toBeDisabled();
  });

  it('TC-VF-181 승인된 제안이 없으면 빈 상태 안내(영상 목록으로 가는 다음 행동)가 나온다', async () => {
    mountApp(base(0), '/batches');
    expect(await screen.findByText(ko.batches.approvedEmpty)).toBeInTheDocument();
    expect(
      within(screen.getByRole('main')).getByRole('link', { name: ko.nav.videos }),
    ).toBeInTheDocument();
  });

  it('TC-VF-169 초안 만들기: 정렬된 suggestion_ids·메모를 CSRF+Idempotency-Key 와 함께 한 번만 보내고 초안 화면으로 이동한다(더블클릭 포함)', async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const c = mountApp(
      base(3, [
        route('POST', '/api/v1/batches', async () => {
          await gate;
          return json(201, { batch: draftBatch(), precheck: draftBatch().precheck });
        }),
      ]),
      '/batches',
    );
    await screen.findByRole('checkbox', { name: ko.batches.selectAll });
    await user.click(screen.getByRole('checkbox', { name: ko.batches.selectOne('승인 제목 3') }));
    await user.click(screen.getByRole('checkbox', { name: ko.batches.selectOne('승인 제목 1') }));
    await user.type(screen.getByLabelText(ko.batches.noteLabel), '  가을 정리  ');
    await user.dblClick(screen.getByRole('button', { name: ko.batches.createDraft }));
    release();
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/batches/7'));
    const posts = c.calls.filter((x) => x.method === 'POST' && x.path === '/api/v1/batches');
    expect(posts).toHaveLength(1);
    expect(posts[0]!.body).toEqual({ suggestion_ids: [1, 3], note: '가을 정리' });
    expect(posts[0]!.headers['idempotency-key']).toMatch(/^[0-9a-f-]{32,36}$/);
    expect(posts[0]!.headers['x-csrf-token']).toBe('csrf-1');
  });

  it('TC-VF-170 초안 만들기가 거절되면(422) 오류를 보여 주고, 같은 선택으로 다시 눌러도 같은 Idempotency-Key 를 쓴다', async () => {
    const user = userEvent.setup();
    let n = 0;
    const c = mountApp(
      base(2, [
        route('POST', '/api/v1/batches', () =>
          ++n === 1
            ? problem(422, 'suggestion_not_approved', '승인되지 않은 제안이 있습니다')
            : json(201, { batch: draftBatch(), precheck: draftBatch().precheck }),
        ),
      ]),
      '/batches',
    );
    await screen.findByRole('checkbox', { name: ko.batches.selectAll });
    await user.click(screen.getByRole('checkbox', { name: ko.batches.selectOne('승인 제목 1') }));
    await user.click(screen.getByRole('button', { name: ko.batches.createDraft }));
    expect(await screen.findByText('승인되지 않은 제안이 있습니다')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: ko.batches.createDraft }));
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/batches/7'));
    const keys = c.calls
      .filter((x) => x.method === 'POST')
      .map((x) => x.headers['idempotency-key']);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });
});

// ---------- 배치 진행·중지 (W-010) ----------
describe('배치 진행 화면', () => {
  it('TC-VF-171 실행 중인 배치는 서버 상태를 2초마다 읽어 진행률을 갱신하고, 끝나면 폴링을 멈추고 이력 링크를 보인다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    const mk = (done: number, status: string) =>
      draftBatch({
        status,
        counts: {
          pending: 2 - done,
          running: 0,
          success: done,
          failed: 0,
          skipped: 0,
          cancelled: 0,
        },
      });
    const c = mountApp(
      [
        route('GET', '/api/v1/batches/7', () => {
          n++;
          return json(200, n === 1 ? mk(0, 'running') : n === 2 ? mk(1, 'running') : mk(2, 'done'));
        }),
      ],
      '/batches/7',
    );
    await screen.findByText(ko.batches.pollingHint);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    await screen.findByText(ko.batches.finished);
    const calls = c.calls.filter((x) => x.path === '/api/v1/batches/7').length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000);
    });
    expect(c.calls.filter((x) => x.path === '/api/v1/batches/7').length).toBe(calls);
    expect(screen.getByRole('link', { name: ko.batches.finishedHistory })).toBeInTheDocument();
  });

  it('TC-VF-172 중지는 확인 대화상자를 거치고, 확인해야만 CSRF 와 함께 POST cancel 이 한 번 간다(더블클릭 포함)', async () => {
    const user = userEvent.setup();
    const running = draftBatch({ status: 'running' });
    let cancelled = false;
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const c = mountApp(
      [
        route('GET', '/api/v1/batches/7', () =>
          json(200, cancelled ? { ...running, status: 'cancelled' } : running),
        ),
        route('POST', '/api/v1/batches/7/cancel', async () => {
          await gate;
          cancelled = true;
          return json(200, { ...running, status: 'cancelled' });
        }),
      ],
      '/batches/7',
    );
    await user.click(await screen.findByRole('button', { name: ko.batches.stop }));
    expect(c.calls.filter((x) => x.path.endsWith('/cancel'))).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: ko.batches.stopConfirm }));
    await user.click(screen.getByRole('button', { name: ko.batches.stopConfirm }));
    release();
    await waitFor(() => expect(c.calls.filter((x) => x.path.endsWith('/cancel'))).toHaveLength(1));
    expect(c.calls.find((x) => x.path.endsWith('/cancel'))!.headers['x-csrf-token']).toBe('csrf-1');
    expect(await screen.findByText(ko.batches.finished)).toBeInTheDocument();
  });

  it('TC-VF-173 사전 점검 표: 항목 수·예상 사용량·하루 상한·남은 한도·날짜별 일정·경고·제외 항목을 모두 보여 준다', async () => {
    const pc = {
      ...draftBatch().precheck!,
      item_count: 3,
      estimated_units: 150,
      daily_cap: 5,
      quota_remaining_units: 4850,
      schedule: [
        { date: '2026-10-10', count: 2 },
        { date: '2026-10-11', count: 1 },
      ],
      warnings: ['하루 상한 때문에 2일에 나눠 반영됩니다'],
      blocked: [{ suggestion_id: 9, reason: '72시간 안에 이미 변경됨' }],
      confirm_text: '실행 3건',
    };
    mountApp(
      [route('GET', '/api/v1/batches/7', () => json(200, draftBatch({ precheck: pc })))],
      '/batches/7',
    );
    await screen.findByText(ko.batches.precheckTitle);
    const t = ko.batches.pc;
    expect(screen.getByText(t.itemsVal(3))).toBeInTheDocument();
    expect(screen.getByText(t.unitsVal(150))).toBeInTheDocument();
    expect(screen.getByText(t.capVal(5))).toBeInTheDocument();
    expect(screen.getByText(t.unitsVal(4850))).toBeInTheDocument();
    expect(screen.getByText('하루 상한 때문에 2일에 나눠 반영됩니다')).toBeInTheDocument();
    expect(screen.getByText(t.blockedLine(9, '72시간 안에 이미 변경됨'))).toBeInTheDocument();
    expect(screen.getAllByText(t.itemsVal(2)).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('table').length).toBeGreaterThanOrEqual(2);
  });
});

// ---------- 서버 계약의 상태 값 표기 (WEB_DESIGN §3: Batch.status = draft|queued|running|paused|done|cancelled, Job.type = videos.sync|suggestions.generate|batch.execute) ----------
describe('서버 상태 값의 한국어 표기', () => {
  const asciiOnly = (t: string) => /^[a-z._]+$/.test(t.trim());

  for (const st of ['queued', 'paused'])
    it.fails(
      `TC-VF-182 배치 상태 "${st}" 가 영문 원문이 아닌 한국어로 표시된다 [DEF-6-010]`,
      async () => {
        // 결함 DEF-6-010(Low): ko.batchStatus 에 queued(실행 직후 실제 서버가 쓰는 값)·paused 가 없어 영문 원문이 그대로 보인다.
        const run = draftBatch({ status: st });
        mountApp([route('GET', '/api/v1/batches/7', () => json(200, run))], '/batches/7');
        await screen.findByText(ko.batches.progressTitle);
        const badge = document.querySelector('main .card .badge, main .badge');
        expect(badge).not.toBeNull();
        expect(asciiOnly(badge!.textContent ?? '')).toBe(false);
      },
    );

  it.fails(
    'TC-VF-183 홈의 "진행 중인 작업" 이 서버 작업 종류 코드(videos.sync 등)를 한국어로 바꿔 보여 준다 [DEF-6-011]',
    async () => {
      // 결함 DEF-6-011(Low): ko.home.activeJob 에 type 원문을 그대로 넣는다.
      mountApp(
        [
          route('GET', '/api/v1/dashboard', () =>
            json(
              200,
              dashboard({
                active_job: {
                  id: 'j1',
                  type: 'videos.sync',
                  status: 'running',
                  progress: 1,
                  total: 4,
                },
              }),
            ),
          ),
        ],
        '/',
      );
      const line = await screen.findByText(/진행 중인 작업/);
      expect(line.textContent).not.toMatch(/videos\.sync/);
    },
  );
});

// ---------- 이력 필터 (W-011) ----------
describe('이력 화면', () => {
  it('TC-VF-174 영상 ID·결과 필터는 서버 질의로 가며(앞뒤 공백 제거), 필터를 걸면 1쪽으로 돌아간다', async () => {
    const user = userEvent.setup();
    const c = mountApp([route('GET', '/api/v1/changes', () => json(200, page([], 0)))], '/history');
    await screen.findByText(ko.history.emptyTitle);
    await user.type(screen.getByLabelText(ko.history.filterVideo), '  vid00000001  {Enter}');
    await waitFor(() =>
      expect(lastGet(c.calls, '/api/v1/changes')?.query.get('video_id')).toBe('vid00000001'),
    );
    await user.selectOptions(screen.getByLabelText(ko.history.filterResult), 'failed');
    await waitFor(() =>
      expect(lastGet(c.calls, '/api/v1/changes')?.query.get('result')).toBe('failed'),
    );
    expect(lastGet(c.calls, '/api/v1/changes')!.query.get('page')).toBe('1');
    expect(await screen.findByText(ko.videos.emptyTitle)).toBeInTheDocument();
  });
});

// ---------- 리포트 CSV (W-012) ----------
describe('성과 리포트 CSV 내보내기', () => {
  const rep = route('GET', '/api/v1/reports/changes', () => json(200, { items: [], notes: [] }));
  function stubBlobUrl() {
    const created: Blob[] = [];
    const revoked: string[] = [];
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: (b: Blob) => {
        created.push(b);
        return 'blob:test/1';
      },
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: (u: string) => revoked.push(u),
    });
    const clicks: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicks.push(this);
    });
    return { created, revoked, clicks };
  }

  it('TC-VF-175 CSV 내보내기는 GET export.csv(토큰·멱등키 없음)를 부르고 blob 앵커 다운로드로 저장한다', async () => {
    const user = userEvent.setup();
    const s = stubBlobUrl();
    const c = mountApp(
      [
        rep,
        route(
          'GET',
          '/api/v1/reports/export.csv',
          () =>
            new Response('video_id,title\nvid1,"=SUM(A1)"\n', {
              status: 200,
              headers: { 'Content-Type': 'text/csv' },
            }),
        ),
      ],
      '/reports',
    );
    await user.click(await screen.findByRole('button', { name: ko.reports.export }));
    await waitFor(() => expect(s.clicks).toHaveLength(1));
    expect(s.clicks[0]!.getAttribute('href')).toBe('blob:test/1');
    expect(s.clicks[0]!.getAttribute('download')).toBe('ytitle-report.csv');
    expect(s.created).toHaveLength(1);
    expect(await s.created[0]!.text()).toContain('vid1');
    const get = c.calls.find((x) => x.path === '/api/v1/reports/export.csv')!;
    expect(get.method).toBe('GET');
    expect(get.headers['x-csrf-token']).toBeUndefined();
    expect(await screen.findByText(ko.reports.exported)).toBeInTheDocument();
    expect(document.querySelector('a[download]')).toBeNull(); // 임시 앵커는 DOM 에 남지 않음
  });

  it('TC-VF-176 CSV 내보내기가 실패하면(500) 오류 안내가 나오고 다운로드는 일어나지 않는다', async () => {
    const user = userEvent.setup();
    const s = stubBlobUrl();
    mountApp(
      [
        rep,
        route('GET', '/api/v1/reports/export.csv', () =>
          problem(500, 'export_failed', '내보내기에 실패했습니다'),
        ),
      ],
      '/reports',
    );
    await user.click(await screen.findByRole('button', { name: ko.reports.export }));
    expect(await screen.findByText('내보내기에 실패했습니다')).toBeInTheDocument();
    expect(s.clicks).toHaveLength(0);
  });

  it('TC-VF-177 내보내기 중에는 버튼이 비활성이라 연타해도 요청이 한 번이다', async () => {
    const user = userEvent.setup();
    stubBlobUrl();
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const c = mountApp(
      [
        rep,
        route('GET', '/api/v1/reports/export.csv', async () => {
          await gate;
          return new Response('a', { status: 200, headers: { 'Content-Type': 'text/csv' } });
        }),
      ],
      '/reports',
    );
    const btn = await screen.findByRole('button', { name: ko.reports.export });
    await user.dblClick(btn);
    release();
    await waitFor(() => expect(screen.getByText(ko.reports.exported)).toBeInTheDocument());
    expect(c.calls.filter((x) => x.path === '/api/v1/reports/export.csv')).toHaveLength(1);
  });

  it('TC-VF-178 리포트 영상 필터는 video_id 질의로 가고, 서버 notes 가 비면 기본 안내가 맨 위에 나온다', async () => {
    const user = userEvent.setup();
    const c = mountApp([rep], '/reports');
    expect(await screen.findByText(ko.reports.fallbackNote)).toBeInTheDocument();
    await user.type(screen.getByLabelText(ko.reports.filterVideo), ' vid00000009 {Enter}');
    await waitFor(() =>
      expect(lastGet(c.calls, '/api/v1/reports/changes')?.query.get('video_id')).toBe(
        'vid00000009',
      ),
    );
  });
});

void problem;
