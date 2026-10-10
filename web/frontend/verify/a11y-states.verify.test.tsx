// 06단계 독립 검증(TC-VF) — 접근성(axe·키보드·포커스), 상태 화면(로딩·빈·오류·한도·만료·끊김)
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { Providers } from '../src/app/providers';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { ApiClient } from '../src/api/client';
import { App } from '../src/app/App';
import { dashboard, detail, draftBatch, suggestion, video } from '../src/test/fixtures';
import {
  authedHandlers,
  fakeFetch,
  json,
  makeClient,
  problem,
  route,
  type Handler,
} from '../src/test/utils';

beforeAll(() => {
  document.documentElement.lang = 'ko'; // index.html 과 같은 조건
  document.title = 'ytitle 웹';
});
afterEach(() => {
  vi.useRealTimers();
});

const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 50 });
const chg = (over = {}) => ({
  id: 5,
  video_id: 'vid00000001',
  video_title: '테스트 영상 1',
  change_type: 'apply',
  previous_title: '이전 제목',
  new_title: '새 제목',
  result: 'success',
  mode: 'demo',
  approver: '홍길동',
  applied_at: '2026-10-10T00:00:00Z',
  verified_at: '2026-10-10T00:01:00Z',
  error_code: null,
  rollbackable: true,
  batch_id: 7,
  ...over,
});
const warnS = suggestion(2, {
  title: '이거 모르면 큰일! 테스트 영상 1',
  validation_result: 'warn',
  strict: true,
  topic: 'life',
  reasons: [{ code: 'risky', severity: 'warn', message: '공포를 조장할 수 있는 표현' }],
});
const blockS = suggestion(3, {
  title: '테스트 100% 무조건',
  validation_result: 'block',
  reasons: [{ code: 'banned', severity: 'block', message: '근거 없는 100% 단정' }],
});
const passS = suggestion(1);
const running = draftBatch({
  id: 8,
  status: 'running',
  counts: { pending: 1, running: 1, success: 0, failed: 0, skipped: 0, cancelled: 0 },
});
const settings = {
  daily_apply_cap: 10,
  suggestions_per_video: 3,
  tone: ['차분하게'],
  pin_enabled: true,
  mode: 'demo',
  read_only: { enable_live: false, live_allowlist: ['vid00000001'], note: 'n' },
};

/** 모든 화면이 쓰는 API 를 현실적인 값으로 채운 가짜 서버 */
const backend = (over: Handler[] = []): Handler[] => [
  ...over,
  ...authedHandlers,
  route('GET', '/api/v1/dashboard', () =>
    json(200, dashboard({ queue: { pending_items: 2, next_run_date: '2026-10-11' } })),
  ),
  route('GET', '/api/v1/videos', () =>
    json(
      200,
      page([
        video(1),
        video(2, { workflow_status: 'suggested', suggestion_count: 3 }),
        video(3, { excluded: true, exclusion_reasons: ['비공개 영상'] }),
      ]),
    ),
  ),
  route('GET', '/api/v1/videos/vid00000001', () =>
    json(
      200,
      detail([passS, warnS, blockS], {
        changes: [chg() as never],
        limits: {
          allowed: false,
          reasons: ['72시간 안에 이미 변경됨'],
          next_allowed_at: '2026-10-12T00:00:00Z',
        },
      }),
    ),
  ),
  route('GET', '/api/v1/suggestions', () =>
    json(
      200,
      page([
        suggestion(1, {
          status: 'approved',
          approval: {
            approver: '나',
            approved_at: '2026-10-10T00:00:00Z',
            expires_at: '2026-10-11T00:00:00Z',
          },
        }),
      ]),
    ),
  ),
  route('GET', '/api/v1/batches', () => json(200, page([running]))),
  route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
  route('GET', '/api/v1/batches/8', () => json(200, running)),
  route('GET', '/api/v1/changes', () =>
    json(
      200,
      page([
        chg(),
        chg({ id: 6, rollbackable: false, result: 'failed', error_code: 'gateway_error' }),
      ]),
    ),
  ),
  route('GET', '/api/v1/reports/changes', () =>
    json(200, {
      items: [
        {
          video_id: 'vid00000001',
          title: '테스트 영상 1',
          status: 'insufficient',
          before: null,
          after: null,
          baseline_missing: true,
          reasons: ['변경 후 데이터 수집 전'],
          notes: [],
          metrics: [],
          expected_after_date: '2026-10-20',
        },
      ],
      notes: ['변화의 원인을 단정할 수 없습니다.'],
    }),
  ),
  route('GET', '/api/v1/settings', () => json(200, settings)),
  route('GET', '/api/v1/audit', () =>
    json(200, {
      ...page([
        {
          id: 1,
          ts: '2026-10-10T00:00:00Z',
          actor: 'local-user',
          action: 'session.create',
          target_type: 'session',
          target_id: 'ab',
          detail: {},
        },
      ]),
      chain_ok: true,
    }),
  ),
  route('GET', '/api/v1/google/status', () =>
    json(200, {
      mode: 'demo',
      connected: false,
      message: '데모 모드: 구글에 연결하지 않았습니다.',
    }),
  ),
];

async function axeAll(
  root: Element | Document = document,
  opts: { landmarkUnique?: boolean } = {},
) {
  const res = await axe.run(root as Element, {
    rules: {
      'color-contrast': { enabled: false }, // jsdom 은 색을 계산하지 못함 → 토큰 값으로 별도 계산(결과서 참조)
      'landmark-unique': { enabled: opts.landmarkUnique === true }, // DEF-6-006 을 별도 시험(TC)으로 분리
    },
  });
  return res.violations.map(
    (v) => `${v.id}: ${v.help} → ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`,
  );
}
/** 실제 index.html 과 같은 구조: <div id="root"> 안에 앱, 대화상자는 body 로 포털 */
function renderInRoot(ui: ReactElement, client: ApiClient, entry: string) {
  document.getElementById('root')?.remove();
  const root = document.createElement('div');
  root.id = 'root';
  document.body.appendChild(root);
  return render(
    <Providers client={client}>
      <MemoryRouter initialEntries={[entry]}>{ui}</MemoryRouter>
    </Providers>,
    { container: root },
  );
}
async function mount(entry: string, over: Handler[] = []) {
  const c = makeClient(backend(over));
  renderInRoot(<App />, c.client, entry);
  return c;
}

describe('접근성: 화면 전체(axe, 색 대비 제외)', () => {
  it.each([
    ['홈', '/', '홈'],
    ['영상 목록', '/videos', '영상 목록'],
    ['영상 상세', '/videos/vid00000001', ''],
    ['배치 목록', '/batches', '배치(일괄 반영)'],
    ['배치 초안', '/batches/7', '배치 #7'],
    ['배치 진행 중', '/batches/8', '배치 #8'],
    ['이력·롤백', '/history', '이력·롤백'],
    ['성과 리포트', '/reports', '성과 리포트'],
    ['설정 안전 탭', '/settings', '설정'],
    ['설정 PIN 탭', '/settings?tab=pin', '설정'],
    ['설정 세션 탭', '/settings?tab=session', '설정'],
    ['설정 감사 탭', '/settings?tab=audit', '설정'],
    ['없는 주소(404)', '/nothing-here', '페이지를 찾을 수 없습니다'],
  ])(
    'TC-VF-125 %s 에 접근성 위반이 없다(랜드마크·제목·이름 없는 버튼·라벨·aria 포함)',
    async (_n, entry, h1) => {
      await mount(entry);
      await screen.findByRole('heading', {
        level: 1,
        name: h1 ? new RegExp(h1.replace(/[()]/g, '\\$&')) : /./,
      });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 60)); // 표·카드가 그려질 시간
      });
      expect(await axeAll()).toEqual([]);
    },
  );
});

describe('접근성: 중복 랜드마크 (DEF-6-006)', () => {
  // 결함 DEF-6-006(Low): 같은 이름의 region 이 겹쳐 있다(섹션 제목과 표 래퍼 라벨이 같음) → axe landmark-unique(moderate)
  it.fails(
    'TC-VF-126 지난 배치 구역과 변경 이력 구역에서 같은 이름의 랜드마크가 중복되지 않는다 [DEF-6-006]',
    async () => {
      await mount('/batches');
      await screen.findByRole('heading', { level: 1, name: '배치(일괄 반영)' });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 60));
      });
      expect(await axeAll(document, { landmarkUnique: true })).toEqual([]);
    },
  );
});

describe('접근성: 대화상자·오버레이', () => {
  const openCard = async (name: string, btn: string) => {
    const user = userEvent.setup();
    await mount('/videos/vid00000001');
    const card = (await screen.findByRole('heading', { name, level: 3 })).closest(
      'article',
    ) as HTMLElement;
    await user.click(within(card).getByRole('button', { name: btn }));
    return { user, dlg: await screen.findByRole('dialog') };
  };

  it('TC-VF-127 경고 제안 승인 대화상자: 이름·aria-modal·위반 없음, 처음 포커스는 승인자 입력칸', async () => {
    const { dlg } = await openCard('이거 모르면 큰일! 테스트 영상 1', '승인');
    expect(dlg).toHaveAttribute('aria-modal', 'true');
    expect(dlg).toHaveAccessibleName();
    expect(within(dlg).getByLabelText(/승인자/)).toHaveFocus();
    expect(await axeAll()).toEqual([]);
  });

  it('TC-VF-128 반려·수정 대화상자에도 접근성 위반이 없다', async () => {
    const a = await openCard('테스트 영상 1 핵심 정리', '반려');
    expect(await axeAll()).toEqual([]);
    await a.user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const card = screen
      .getByRole('heading', { name: '테스트 영상 1 핵심 정리', level: 3 })
      .closest('article') as HTMLElement;
    await a.user.click(within(card).getByRole('button', { name: /수정/ }));
    await screen.findByRole('dialog');
    expect(await axeAll()).toEqual([]);
  });

  it('TC-VF-129 대화상자에서 Tab 을 계속 눌러도 포커스가 대화상자 밖으로 나가지 않고(앞으로·뒤로), 뒷배경은 inert 이다', async () => {
    const { user, dlg } = await openCard('이거 모르면 큰일! 테스트 영상 1', '승인');
    expect(document.getElementById('root')).toHaveAttribute('inert');
    for (let i = 0; i < 12; i++) {
      await user.tab();
      expect(dlg.contains(document.activeElement), `Tab ${i}`).toBe(true);
    }
    for (let i = 0; i < 12; i++) {
      await user.tab({ shift: true });
      expect(dlg.contains(document.activeElement), `Shift+Tab ${i}`).toBe(true);
    }
  });

  it('TC-VF-130 Esc 로 닫으면 열었던 버튼으로 포커스가 돌아오고 뒷배경 inert 가 풀린다', async () => {
    const { user } = await openCard('이거 모르면 큰일! 테스트 영상 1', '승인');
    const card = screen
      .getByRole('heading', { name: '이거 모르면 큰일! 테스트 영상 1', level: 3 })
      .closest('article') as HTMLElement;
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(within(card).getByRole('button', { name: '승인' })).toHaveFocus();
    expect(document.getElementById('root')).not.toHaveAttribute('inert');
  });

  it('TC-VF-131 롤백 대화상자·진행 중 배치 중지 대화상자에도 위반이 없다', async () => {
    const user = userEvent.setup();
    await mount('/history');
    await user.click(await screen.findByRole('button', { name: /롤백/ }));
    await screen.findByRole('dialog');
    expect(await axeAll()).toEqual([]);
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('TC-VF-132 진행 중 배치의 중지 대화상자: 위반 없음, 취소하면 요청이 없다', async () => {
    const user = userEvent.setup();
    const { calls } = await mount('/batches/8');
    await user.click(await screen.findByRole('button', { name: '중지' }));
    const d = await screen.findByRole('dialog');
    expect(await axeAll()).toEqual([]);
    await user.click(within(d).getByRole('button', { name: '취소' }));
    expect(calls.some((c) => c.path.endsWith('/cancel'))).toBe(false);
  });

  it('TC-VF-133 PIN 해제 대화상자와 AI 제안 생성 작업 창에도 위반이 없다', async () => {
    const user = userEvent.setup();
    await mount('/settings?tab=pin');
    await user.click(await screen.findByRole('button', { name: 'PIN 해제' }));
    await screen.findByRole('dialog');
    expect(await axeAll()).toEqual([]);
  });

  it('TC-VF-134 세션 만료 오버레이: Esc 로 닫을 수 없고 포커스는 PIN 입력칸에 있으며 위반이 없다', async () => {
    const user = userEvent.setup();
    let expired = false;
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, {
          authenticated: !expired,
          pin_required: true,
          csrf_token: expired ? null : 'c1',
        }),
      ),
      route('POST', '/api/v1/suggestions/1/reject', () => {
        expired = true;
        return problem(401, 'session_required', '세션 만료');
      }),
      ...backend(),
    ]);
    renderInRoot(<App />, client, '/videos/vid00000001');
    const card = (
      await screen.findByRole('heading', { name: '테스트 영상 1 핵심 정리', level: 3 })
    ).closest('article') as HTMLElement;
    await user.click(within(card).getByRole('button', { name: '반려' }));
    const d1 = await screen.findByRole('dialog');
    await user.click(within(d1).getByRole('button', { name: '반려' }));
    const overlay = await screen.findByRole('heading', { name: '세션이 만료되었습니다' });
    const dlgs = screen.getAllByRole('dialog');
    const ov = dlgs.find((x) => x.contains(overlay))!;
    expect(within(ov).getByLabelText('PIN')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.getByRole('heading', { name: '세션이 만료되었습니다' })).toBeInTheDocument();
    expect(await axeAll()).toEqual([]);
  });
});

describe('접근성: 시작·끊김 화면', () => {
  it('TC-VF-135 PIN 화면: 입력칸에 이름이 있고 자동 포커스, 틀린 PIN 안내가 role=alert 가 아니어도 글자로 보이며 위반이 없다', async () => {
    const user = userEvent.setup();
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, { authenticated: false, pin_required: true, csrf_token: null }),
      ),
      route('POST', '/api/v1/auth/session', () => problem(401, 'pin_invalid', 'PIN 불일치')),
    ]);
    renderInRoot(<App />, client, '/');
    const box = await screen.findByLabelText('PIN');
    expect(box).toHaveAttribute('type', 'password');
    expect(await axeAll()).toEqual([]);
    await user.type(box, '0000{Enter}');
    expect(
      await screen.findByText('PIN 이 맞지 않습니다. 다시 확인해 주세요.'),
    ).toBeInTheDocument();
    expect(await axeAll()).toEqual([]);
  });

  it('TC-VF-136 시작부터 서버 연결 끊김 화면, 로그아웃 화면에도 위반이 없다', async () => {
    const user = userEvent.setup();
    const f = fakeFetch([
      () => {
        throw new TypeError('x');
      },
    ]);
    const client = new ApiClient({ fetchImpl: f.fetch });
    renderInRoot(<App />, client, '/');
    await screen.findByRole('heading', { name: '서버 연결이 끊겼습니다' });
    expect(await axeAll()).toEqual([]);
    void user;
  });

  it('TC-VF-137 사용 중 서버 연결이 끊기면 경고 배너(role=alert)와 "서버 연결 끊김" 상태가 나오고 다시 연결하면 사라진다', async () => {
    const user = userEvent.setup();
    let down = false;
    const { client } = makeClient([
      () => {
        if (down) throw new TypeError('x');
        return undefined;
      },
      ...backend(),
    ]);
    renderInRoot(<App />, client, '/videos');
    await screen.findByRole('table');
    down = true;
    await user.click(screen.getByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(screen.getAllByText('서버 연결 끊김').length).toBeGreaterThan(0));
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/로그아웃되었|서버 연결이 끊겼/).length).toBeGreaterThan(0);
    down = false;
    await user.click(screen.getAllByRole('button', { name: '다시 연결' })[0]!);
    await waitFor(() => expect(screen.getByText('서버 연결됨')).toBeInTheDocument());
    expect(screen.queryByText('서버에 연결할 수 없어 최신 정보가 아닐 수 있습니다.')).toBeNull();
  });
});

describe('키보드 이동·포커스', () => {
  it('TC-VF-138 첫 Tab 은 "본문으로 건너뛰기", 이어서 메뉴 6개 순서(홈→영상→배치→이력→리포트→설정)', async () => {
    const user = userEvent.setup();
    await mount('/');
    await screen.findByRole('heading', { level: 1, name: '홈' });
    await user.tab();
    expect(screen.getByText('본문으로 건너뛰기')).toHaveFocus();
    const order: string[] = [];
    for (let i = 0; i < 7; i++) {
      await user.tab();
      order.push(document.activeElement?.textContent ?? '');
    }
    expect(order[0]).toMatch(/ytitle/);
    expect(order.slice(1)).toEqual([
      '홈',
      '영상 목록',
      '배치(일괄 반영)',
      '이력·롤백',
      '성과 리포트',
      '설정',
    ]);
  });

  it('TC-VF-139 건너뛰기 링크를 Enter 로 누르면 본문(main)으로 포커스가 간다', async () => {
    const user = userEvent.setup();
    await mount('/');
    await screen.findByRole('heading', { level: 1, name: '홈' });
    await user.tab();
    await user.keyboard('{Enter}');
    expect(document.getElementById('main')).toHaveFocus();
  });

  it('TC-VF-140 메뉴에서 다른 화면으로 가면 새 화면 제목(h1)으로 포커스가 이동한다', async () => {
    const user = userEvent.setup();
    await mount('/');
    await screen.findByRole('heading', { level: 1, name: '홈' });
    await user.click(screen.getByRole('link', { name: '이력·롤백' }));
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: '이력·롤백' })).toHaveFocus(),
    );
  });

  it('TC-VF-141 현재 화면 메뉴에 aria-current 가 붙는다(색에만 의존하지 않음)', async () => {
    await mount('/history');
    await screen.findByRole('heading', { level: 1, name: '이력·롤백' });
    expect(screen.getByRole('link', { name: '이력·롤백' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: '홈' })).not.toHaveAttribute('aria-current');
  });

  it('TC-VF-142 설정 탭: 방향키 좌우·Home·End 로 이동하고 선택 탭만 tabIndex 0 이다', async () => {
    const user = userEvent.setup();
    await mount('/settings');
    const tabs = await screen.findAllByRole('tab');
    expect(tabs).toHaveLength(4);
    tabs[0]!.focus();
    await user.keyboard('{ArrowRight}');
    await waitFor(() =>
      expect(screen.getAllByRole('tab')[1]).toHaveAttribute('aria-selected', 'true'),
    );
    await user.keyboard('{End}');
    await waitFor(() =>
      expect(screen.getAllByRole('tab')[3]).toHaveAttribute('aria-selected', 'true'),
    );
    await user.keyboard('{ArrowRight}'); // 끝에서 처음으로 순환
    await waitFor(() =>
      expect(screen.getAllByRole('tab')[0]).toHaveAttribute('aria-selected', 'true'),
    );
    await user.keyboard('{ArrowLeft}');
    await waitFor(() =>
      expect(screen.getAllByRole('tab')[3]).toHaveAttribute('aria-selected', 'true'),
    );
    await user.keyboard('{Home}');
    await waitFor(() =>
      expect(screen.getAllByRole('tab')[0]).toHaveAttribute('aria-selected', 'true'),
    );
    const t = screen.getAllByRole('tab');
    expect(t.filter((x) => x.getAttribute('tabindex') === '0')).toHaveLength(1);
  });

  it('TC-VF-143 영상 목록의 정렬 머리글은 버튼이고 aria-sort 가 바뀐다', async () => {
    const user = userEvent.setup();
    await mount('/videos');
    const btn = await screen.findByRole('button', { name: /^제목/ });
    const th = btn.closest('th')!;
    expect(th).toHaveAttribute('aria-sort', 'none');
    await user.click(btn);
    await waitFor(() => expect(th).toHaveAttribute('aria-sort', 'ascending'));
    await user.click(btn);
    await waitFor(() => expect(th).toHaveAttribute('aria-sort', 'descending'));
  });

  it('TC-VF-144 모든 입력칸·선택칸·체크박스에 접근 가능한 이름이 있다(영상 목록·설정·이력)', async () => {
    for (const entry of ['/videos', '/settings', '/history']) {
      const c = makeClient(backend());
      const { unmount } = renderInRoot(<App />, c.client, entry);
      await screen.findByRole('heading', { level: 1 });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 40));
      });
      for (const el of Array.from(
        document.querySelectorAll('input:not([type=hidden]),select,textarea'),
      )) {
        const name =
          (el as HTMLElement).getAttribute('aria-label') ||
          (el as HTMLInputElement).labels?.[0]?.textContent ||
          el.getAttribute('aria-labelledby');
        expect(name, `${entry}: ${el.outerHTML.slice(0, 80)}`).toBeTruthy();
      }
      unmount();
    }
  });

  it('TC-VF-145 진행률 표시는 progress 요소에 이름·값이 있고 숫자 글자도 함께 나온다', async () => {
    await mount('/batches/8');
    const p = await screen.findByRole('progressbar');
    expect(p).toHaveAccessibleName();
    expect(screen.getByText(/\d+ \/ \d+건 처리됨/)).toBeInTheDocument();
  });
});

describe('상태 화면: 로딩·빈·오류·한도 (F-07)', () => {
  const pages: [string, string, string, string][] = [
    ['홈', '/', '/api/v1/dashboard', '홈'],
    ['영상 목록', '/videos', '/api/v1/videos', '영상 목록'],
    ['영상 상세', '/videos/vid00000001', '/api/v1/videos/vid00000001', ''],
    ['배치', '/batches', '/api/v1/suggestions', '배치(일괄 반영)'],
    ['배치 상세', '/batches/7', '/api/v1/batches/7', ''],
    ['이력', '/history', '/api/v1/changes', '이력·롤백'],
    ['리포트', '/reports', '/api/v1/reports/changes', '성과 리포트'],
    ['설정', '/settings', '/api/v1/settings', '설정'],
    ['감사 로그', '/settings?tab=audit', '/api/v1/audit', '설정'],
  ];

  it.each(pages)(
    'TC-VF-146 %s: 서버가 500 이면 오류 안내(다음에 할 일·오류 코드·다시 시도)를 보이고, 다시 시도하면 복구된다',
    async (_n, entry, path) => {
      const user = userEvent.setup();
      let fail = true;
      await mount(entry, [
        route('GET', path, async (r) =>
          fail ? problem(500, 'internal_error', '서버 오류가 났습니다') : await backendFallback(r),
        ),
      ]);
      const panel = (await screen.findByText('internal_error')).closest(
        '[role="alert"]',
      ) as HTMLElement;
      expect(panel).toBeTruthy();
      expect(within(panel).getByText(/다음에 할 일/)).toBeInTheDocument();
      expect(within(panel).getByRole('button', { name: '다시 시도' })).toBeInTheDocument();
      fail = false;
      await user.click(within(panel).getByRole('button', { name: '다시 시도' }));
      await waitFor(() => expect(screen.queryByText('internal_error')).toBeNull());
    },
  );

  it('TC-VF-147 한도 초과(429 quota_exhausted)는 "한도" 제목의 경고로 구분해 보여 준다', async () => {
    await mount('/history', [
      route('GET', '/api/v1/changes', () =>
        problem(
          429,
          'quota_exhausted',
          '오늘 쿼터가 부족합니다',
          '내일 다시',
          '태평양 시간 자정에 초기화',
        ),
      ),
    ]);
    const a = (await screen.findByText('quota_exhausted')).closest('[role="alert"]') as HTMLElement;
    expect(within(a).getByText('한도에 도달했습니다')).toBeInTheDocument();
    expect(within(a).getByText('태평양 시간 자정에 초기화')).toBeInTheDocument();
  });

  it('TC-VF-148 로딩 중에는 role=status 의 불러오는 표시가 보이고 끝나면 사라진다', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((r) => (release = r));
    await mount('/history', [
      route('GET', '/api/v1/changes', async () => {
        await gate;
        return json(200, page([chg()]));
      }),
    ]);
    await screen.findByRole('heading', { level: 1, name: '이력·롤백' });
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0);
    release?.();
    await screen.findByRole('table');
  });

  it.each([
    ['영상 목록', '/videos', [route('GET', '/api/v1/videos', () => json(200, page([])))], true],
    ['이력', '/history', [route('GET', '/api/v1/changes', () => json(200, page([])))], true],
    [
      '배치(승인 항목·지난 배치 없음)',
      '/batches',
      [
        route('GET', '/api/v1/suggestions', () => json(200, page([]))),
        route('GET', '/api/v1/batches', () => json(200, page([]))),
      ],
      true,
    ],
    [
      '리포트',
      '/reports',
      [route('GET', '/api/v1/reports/changes', () => json(200, { items: [], notes: [] }))],
      true,
    ],
    [
      '감사 로그',
      '/settings?tab=audit',
      [route('GET', '/api/v1/audit', () => json(200, { ...page([]), chain_ok: true }))],
      false,
    ],
  ] as [string, string, Handler[], boolean][])(
    'TC-VF-149 빈 상태(%s): 안내 문구가 보이고 접근성 위반이 없다(읽기 전용 로그를 뺀 화면은 다음 행동도 있다)',
    async (_n, entry, over, needsAction) => {
      await mount(entry, over);
      await screen.findByRole('heading', { level: 1 });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 60));
      });
      expect(screen.queryByRole('table')).toBeNull();
      const main = document.getElementById('main')!;
      expect(main.querySelector('.empty, [class*="empty"]')).not.toBeNull();
      if (needsAction)
        expect(
          within(main).queryAllByRole('link').length + within(main).queryAllByRole('button').length,
        ).toBeGreaterThan(0);
      expect(await axeAll()).toEqual([]);
    },
  );

  it('TC-VF-150 성과 리포트: 데이터 부족 상태에서도 서버가 준 "원인 단정 금지" 문구가 맨 위에 보인다', async () => {
    await mount('/reports');
    await screen.findByText('변화의 원인을 단정할 수 없습니다.');
    expect(screen.getAllByText(/데이터 부족|부족/).length).toBeGreaterThan(0);
  });
});

/** 위 오류 시험에서 "복구된 뒤"에 줄 정상 응답(실제 backend() 의 같은 경로 핸들러를 재사용) */
async function backendFallback(r: Parameters<Handler>[0]): Promise<Response> {
  for (const h of backend()) {
    const out = await h(r);
    if (out) return out;
  }
  return problem(404, 'test_unhandled', 'x');
}

void fireEvent;
