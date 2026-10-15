// 06단계 독립 검증(TC-VF-190~) — 2차 심사에서 발견·수정한 결함의 회귀 시험과 경계값 보강
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError, REQUEST_TIMEOUT_MS } from '../src/api/client';
import { App } from '../src/app/App';
import { Providers } from '../src/app/providers';
import { Pagination } from '../src/components';
import { ko } from '../src/i18n/ko';
import { fmtDateTime } from '../src/lib/format';
import { batchStatusLabel, jobTypeLabel, workflowLabel } from '../src/lib/labels';
import { SettingsPage } from '../src/pages/SettingsPage';
import { dashboard, detail, suggestion, video } from '../src/test/fixtures';
import {
  authedHandlers,
  connectedClient,
  json,
  makeClient,
  problem,
  renderWithApp,
  route,
  type Handler,
} from '../src/test/utils';

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

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
      </MemoryRouter>
    </Providers>,
    { container: root },
  );
  return c;
}
const page = <T,>(items: T[], total = items.length) => ({ items, total, page: 1, page_size: 50 });

// ---------- 승인 규칙: 서버와 같은 차단 판정 (엄격 모드의 경고는 차단) ----------
describe('승인 규칙: 엄격 모드(strict) — 서버 is_blocked 와 동일', () => {
  const open = async (s: ReturnType<typeof suggestion>) => {
    mountApp(
      [
        route('GET', '/api/v1/videos/vid00000001', () => json(200, detail([s]))),
        route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
      ],
      '/videos/vid00000001',
    );
    const h = await screen.findByRole('heading', { level: 3, name: s.title });
    return h.closest('article') as HTMLElement;
  };

  it('TC-VF-190 엄격 모드 + 경고: 승인 버튼이 꺼져 있고 "차단" 으로 표시되며 사유 문구가 연결된다 [DEF-VF-001]', async () => {
    const card = await open(
      suggestion(5, {
        title: '민감 주제 제목',
        strict: true,
        validation_result: 'warn',
        reasons: [{ code: 'health', severity: 'warn', message: '건강 단정 표현' }],
      }),
    );
    const btn = within(card).getByRole('button', { name: '승인' });
    expect(btn).toBeDisabled();
    expect(within(card).getByText(ko.validation.block)).toBeInTheDocument();
    expect(within(card).queryByText(ko.validation.warn)).toBeNull();
    expect(within(card).getByText(ko.suggestion.approveBlocked)).toBeInTheDocument();
    expect(btn).toHaveAttribute('aria-describedby');
  });

  it('TC-VF-191 엄격 모드 + 통과: 승인할 수 있다(과차단 방지)', async () => {
    const card = await open(
      suggestion(6, { title: '민감 주제 통과', strict: true, validation_result: 'pass' }),
    );
    expect(within(card).getByRole('button', { name: '승인' })).toBeEnabled();
  });

  it('TC-VF-192 엄격 모드 + 검증 전(null): 통과가 아니므로 승인할 수 없다(fail-closed)', async () => {
    const card = await open(
      suggestion(7, { title: '검증 전 민감', strict: true, validation_result: null }),
    );
    expect(within(card).getByRole('button', { name: '승인' })).toBeDisabled();
  });

  it('TC-VF-193 비엄격 + 경고: 기존대로 승인할 수 있고 경고 확인 체크가 있어야 대화상자의 승인이 켜진다', async () => {
    const user = userEvent.setup();
    const card = await open(
      suggestion(8, {
        title: '경고만 있는 제목',
        strict: false,
        validation_result: 'warn',
        reasons: [{ code: 'x', severity: 'warn', message: '주의 표현' }],
      }),
    );
    await user.click(within(card).getByRole('button', { name: '승인' }));
    const dlg = await screen.findByRole('dialog');
    await user.type(within(dlg).getByLabelText(/승인자/), '홍길동');
    const ok = within(dlg).getByRole('button', { name: '승인' });
    expect(ok).toBeDisabled();
    await user.click(within(dlg).getByRole('checkbox'));
    expect(ok).toBeEnabled();
  });
});

// ---------- 요청 시간 제한 ----------
describe('API 클라이언트: 시간 제한', () => {
  it('TC-VF-194 제한 시간 직전(29.999초)에는 기다리고 정확히 30초에 연결 끊김 오류로 끝나며 요청 신호를 중단한다 [DEF-6-001]', async () => {
    vi.useFakeTimers();
    let sig: AbortSignal | undefined;
    const client = new ApiClient({
      fetchImpl: ((_u: string, init?: RequestInit) => {
        sig = init?.signal ?? undefined;
        return new Promise<Response>(() => undefined);
      }) as unknown as typeof fetch,
    });
    expect(REQUEST_TIMEOUT_MS).toBe(30_000);
    let err: unknown = null;
    const p = client.request('GET', '/api/v1/dashboard').catch((e: unknown) => (err = e));
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS - 1);
    expect(err).toBeNull();
    expect(sig?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await p;
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe('network_error');
    expect(sig?.aborted).toBe(true);
    expect(client.getSnapshot().state).toBe('offline');
  });

  it('TC-VF-195 정상 응답이 오면 제한 시간 타이머를 남기지 않는다(누수 없음)', async () => {
    vi.useFakeTimers();
    const client = new ApiClient({
      fetchImpl: (async () => new Response('{"ok":1}', { status: 200 })) as unknown as typeof fetch,
    });
    await client.request('GET', '/api/v1/dashboard');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('TC-VF-196 오류 응답(500)에서도 타이머를 남기지 않고, 호출자가 낸 중단 신호는 그대로 AbortError 로 전달된다', async () => {
    vi.useFakeTimers();
    const client = new ApiClient({
      fetchImpl: (async () => new Response('{}', { status: 500 })) as unknown as typeof fetch,
    });
    await expect(client.request('GET', '/api/v1/x')).rejects.toBeInstanceOf(ApiError);
    expect(vi.getTimerCount()).toBe(0);

    const ctl = new AbortController();
    const c2 = new ApiClient({
      fetchImpl: ((_u: string, init?: RequestInit) =>
        new Promise<Response>((_res, rej) => {
          init?.signal?.addEventListener('abort', () =>
            rej(new DOMException('aborted', 'AbortError')),
          );
        })) as unknown as typeof fetch,
    });
    const p = c2.request('GET', '/api/v1/x', { signal: ctl.signal }).catch((e: unknown) => e);
    ctl.abort();
    const e = (await p) as { name?: string };
    expect(e.name).toBe('AbortError');
    expect(c2.getSnapshot().state).not.toBe('offline');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('TC-VF-197 이미 중단된 신호를 넘기면 요청 신호도 곧바로 중단 상태로 전달된다', async () => {
    let seen: boolean | undefined;
    const client = new ApiClient({
      fetchImpl: ((_u: string, init?: RequestInit) => {
        seen = init?.signal?.aborted;
        return Promise.reject(new DOMException('aborted', 'AbortError'));
      }) as unknown as typeof fetch,
    });
    const ctl = new AbortController();
    ctl.abort();
    await expect(client.request('GET', '/api/v1/x', { signal: ctl.signal })).rejects.toMatchObject({
      name: 'AbortError',
    });
    expect(seen).toBe(true);
  });
});

describe('API 클라이언트: 한도 계열 판별(isLimit) 경계', () => {
  const lim = (code: string, status = 400) => new ApiError({ status, code, title: 't' }).isLimit;
  it.each(['rate_limited', 'rate', 'limit', 'limit_reached', 'daily_cap_exceeded', 'cap_reached'])(
    'TC-VF-198 한도 계열: %s → true',
    (c) => expect(lim(c)).toBe(true),
  );
  it.each([
    'generate_failed',
    'delimiter_error',
    'capacity_error',
    'accurate',
    'scaffold',
    'migrate',
    'quotation',
  ])('TC-VF-199 한도와 무관: %s → false', (c) => expect(lim(c, 500)).toBe(false));
  it('TC-VF-200 상태 429 는 코드와 무관하게 한도 계열이다', () =>
    expect(lim('anything', 429)).toBe(true));
});

// ---------- 라벨 안전 ----------
describe('라벨 조회: 서버 값이 객체 기본 속성 이름이어도 안전', () => {
  it.each(['constructor', '__proto__', 'toString', 'hasOwnProperty'])(
    'TC-VF-201 "%s" 는 라벨로 오인되지 않고 원문 그대로 보인다',
    (k) => {
      expect(batchStatusLabel(k)).toBe(k);
      expect(workflowLabel(k)).toBe(k);
      expect(jobTypeLabel(k)).toBe(k);
    },
  );
  it('TC-VF-202 알려진 값은 한국어로, 빈 값은 "-" 로 보인다', () => {
    expect(jobTypeLabel('videos.sync')).toBe('영상 불러오기');
    expect(jobTypeLabel('suggestions.generate')).toBe('AI 제안 생성');
    expect(jobTypeLabel('batch.execute')).toBe('배치 실행');
    expect(batchStatusLabel('queued')).toBe('실행 대기');
    expect(batchStatusLabel('paused')).toBe('일시 중지');
    expect(batchStatusLabel('')).toBe('-');
  });
});

// ---------- 시각 ----------
describe('시각 표시: 24시 표기 금지', () => {
  it.each([
    ['2026-10-10T15:00:00Z', '2026-10-11 00:00'],
    ['2026-10-10T15:05:00Z', '2026-10-11 00:05'],
    ['2026-10-10T14:59:00Z', '2026-10-10 23:59'],
    ['2026-12-31T15:00:00Z', '2027-01-01 00:00'],
  ])('TC-VF-203 %s → %s', (iso, want) => expect(fmtDateTime(iso)).toBe(want));
});

// ---------- 쪽 크기 ----------
describe('쪽 크기 선택', () => {
  it('TC-VF-204 목록에 없는 값(30, 200)도 실제 값으로 보이고 정렬되어 들어간다 [DEF-6-007]', () => {
    render(
      <Pagination
        page={1}
        pageSize={30}
        total={100}
        onPage={() => undefined}
        onPageSize={() => undefined}
      />,
    );
    const sel = screen.getByLabelText(ko.pagination.size) as HTMLSelectElement;
    expect(sel.value).toBe('30');
    expect(Array.from(sel.options).map((o) => o.value)).toEqual(['25', '30', '50', '100']);
  });
  it('TC-VF-205 목록에 있는 값이면 항목이 늘지 않는다', () => {
    render(
      <Pagination
        page={1}
        pageSize={50}
        total={100}
        onPage={() => undefined}
        onPageSize={() => undefined}
      />,
    );
    expect(
      Array.from((screen.getByLabelText(ko.pagination.size) as HTMLSelectElement).options),
    ).toHaveLength(3);
  });
});

// ---------- 오류 경계 ----------
describe('화면 오류 경계', () => {
  it('TC-VF-206 한 화면이 깨져도 메뉴는 남고, 다른 메뉴로 이동하면 정상 화면이 다시 그려진다 [DEF-6-005]', async () => {
    const swallow = (e: ErrorEvent) => e.preventDefault();
    window.addEventListener('error', swallow);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const user = userEvent.setup();
    const { suggestions: _x, ...broken } = detail([]);
    void _x;
    try {
      mountApp(
        [
          route('GET', '/api/v1/videos/vid00000001', () => json(200, broken)),
          route('GET', '/api/v1/videos', () => json(200, page([video(1)]))),
          route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
        ],
        '/videos/vid00000001',
      );
      const alert = (await screen.findByText(ko.app.crashTitle)).closest(
        '[role="alert"]',
      ) as HTMLElement;
      expect(alert).not.toBeNull();
      expect(alert.textContent).not.toMatch(/TypeError|at |undefined|\.tsx/);
      await user.click(
        within(screen.getByRole('navigation', { name: '주 메뉴' })).getByRole('link', {
          name: '영상 목록',
        }),
      );
      expect(await screen.findByRole('table')).toBeInTheDocument();
      expect(screen.queryByText(ko.app.crashTitle)).toBeNull();
    } finally {
      window.removeEventListener('error', swallow);
    }
  });
});

// ---------- 작업 창/홈 동기화 ----------
describe('작업 상태를 읽지 못할 때', () => {
  it('TC-VF-207 홈: 불러오기 작업 조회가 404 면 오류가 보이고 "데모 영상 불러오기" 가 다시 켜진다(영구 잠금 방지) [DEF-6-008]', async () => {
    const user = userEvent.setup();
    mountApp(
      [
        route('GET', '/api/v1/dashboard', () =>
          json(
            200,
            dashboard({
              counts: { videos: 0, excluded: 0, suggested: 0, approved: 0, queued: 0, applied: 0 },
            }),
          ),
        ),
        route('POST', '/api/v1/videos/sync', () =>
          json(202, {
            id: 'jx',
            type: 'videos.sync',
            status: 'queued',
            progress: 0,
            total: 0,
            error: null,
            result: null,
          }),
        ),
        route('GET', '/api/v1/jobs/jx', () =>
          problem(404, 'job_not_found', '작업을 찾을 수 없습니다'),
        ),
      ],
      '/',
    );
    await user.click(await screen.findByRole('button', { name: ko.home.syncDemo }));
    await screen.findAllByText('작업을 찾을 수 없습니다', undefined, { timeout: 6000 });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: ko.home.syncDemo })).toBeEnabled(),
    );
  });

  it('TC-VF-208 홈: 작업이 실패(failed)로 끝나도 버튼이 다시 켜진다', async () => {
    const user = userEvent.setup();
    mountApp(
      [
        route('GET', '/api/v1/dashboard', () =>
          json(
            200,
            dashboard({
              counts: { videos: 0, excluded: 0, suggested: 0, approved: 0, queued: 0, applied: 0 },
            }),
          ),
        ),
        route('POST', '/api/v1/videos/sync', () =>
          json(202, {
            id: 'jy',
            type: 'videos.sync',
            status: 'queued',
            progress: 0,
            total: 0,
            error: null,
            result: null,
          }),
        ),
        route('GET', '/api/v1/jobs/jy', () =>
          json(200, {
            id: 'jy',
            type: 'videos.sync',
            status: 'failed',
            progress: 0,
            total: 0,
            error: '실패',
            result: null,
          }),
        ),
      ],
      '/',
    );
    await user.click(await screen.findByRole('button', { name: ko.home.syncDemo }));
    await screen.findByText('실패');
    await waitFor(() =>
      expect(screen.getByRole('button', { name: ko.home.syncDemo })).toBeEnabled(),
    );
  });
});

// ---------- 설정: 말투 입력 경계 ----------
describe('설정: 말투 5개 × 20자 경계', () => {
  const base = {
    daily_apply_cap: 10,
    suggestions_per_video: 3,
    tone: ['차분하게'],
    pin_enabled: false,
    mode: 'demo',
    read_only: { enable_live: false, live_allowlist: [], note: 'n' },
  };
  const go = async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/settings', () => json(200, base)),
      route('PATCH', '/api/v1/settings', (r) => json(200, { ...base, ...(r.body as object) })),
    ]);
    renderWithApp(<SettingsPage />, c.client, '/settings');
    await screen.findByLabelText(/하루/);
    return c;
  };
  const tone = () => screen.getByLabelText(/말투/) as HTMLInputElement;
  const word = (n: number, ch = '가') => ch.repeat(n);

  it('TC-VF-209 5개 × 20자(쉼표 포함 108자)를 붙여 넣어도 잘리지 않고 저장 요청이 그대로 나간다 [DEF-6-003]', async () => {
    const user = userEvent.setup();
    const { calls } = await go();
    const five = ['가', '나', '다', '라', '마'].map((c) => word(20, c));
    await user.clear(tone());
    await user.click(tone());
    await user.paste(five.join(', '));
    expect(tone().value).toBe(five.join(', '));
    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect((calls.find((c) => c.method === 'PATCH')!.body as { tone: string[] }).tone).toEqual(
      five,
    );
  });

  it('TC-VF-210 21자 말투와 6번째 말투는 저장할 수 없다', async () => {
    const user = userEvent.setup();
    await go();
    await user.clear(tone());
    await user.click(tone());
    await user.paste(word(21));
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
    fireEvent.change(tone(), { target: { value: 'a,b,c,d,e,f' } });
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
    fireEvent.change(tone(), { target: { value: 'a,b,c,d,e' } });
    expect(screen.getByRole('button', { name: '저장' })).toBeEnabled();
  });
});

// ---------- 배치 만들기: 사라진 항목은 보내지 않는다 ----------
describe('배치 만들기: 목록에서 사라진 선택 항목', () => {
  it('TC-VF-211 고른 뒤 한 항목이 승인 목록에서 사라지면(만료 등) 남은 항목만 요청하고 선택 수도 맞다', async () => {
    const user = userEvent.setup();
    let phase = 0;
    const s1 = suggestion(1, {
      status: 'approved',
      title: '제목 일',
      approval: {
        approver: 'a',
        approved_at: '2026-10-10T00:00:00Z',
        expires_at: '2026-10-11T00:00:00Z',
      },
    });
    const s2 = suggestion(2, {
      status: 'approved',
      title: '제목 이',
      video_id: 'vid00000002',
      approval: s1.approval,
    });
    const c = mountApp(
      [
        route('GET', '/api/v1/suggestions', () => json(200, page(phase === 0 ? [s1, s2] : [s2]))),
        route('GET', '/api/v1/batches', () => json(200, page([]))),
        route('POST', '/api/v1/batches', () => problem(409, 'stop_here', '중단')),
      ],
      '/batches',
    );
    await user.click(
      await screen.findByRole('checkbox', { name: ko.batches.selectOne('제목 일') }),
    );
    await user.click(screen.getByRole('checkbox', { name: ko.batches.selectOne('제목 이') }));
    phase = 1;
    await new Promise((r) => setTimeout(r, 5200)); // staleTime(5초) 경과
    await act(async () => {
      window.dispatchEvent(new Event('visibilitychange'));
    });
    await waitFor(() => expect(screen.queryByText('제목 일')).toBeNull());
    expect(screen.getByText(ko.videos.selectedCount(1), { exact: false })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: ko.batches.createDraft }));
    await waitFor(() =>
      expect(c.calls.some((x) => x.method === 'POST' && x.path === '/api/v1/batches')).toBe(true),
    );
    const body = c.calls.find((x) => x.method === 'POST' && x.path === '/api/v1/batches')!.body as {
      suggestion_ids: number[];
    };
    expect(body.suggestion_ids).toEqual([2]);
  }, 20000);
});

// ---------- 한 번에 만들 수 있는 영상 수 (API.md: 1~200) ----------
describe('AI 제안 생성: 선택 상한 200', () => {
  const rows = (from: number, n: number) => Array.from({ length: n }, (_, i) => video(from + i));
  const setup = async (twoPages: boolean) => {
    const user = userEvent.setup();
    const c = mountApp(
      [
        route('GET', '/api/v1/videos', (req) => {
          const p = Number(req.query.get('page') ?? 1);
          return json(200, {
            items: p === 1 ? rows(1, 200) : rows(201, 1),
            total: twoPages ? 201 : 200,
            page: p,
            page_size: 200,
          });
        }),
        route('POST', '/api/v1/suggestions/generate', () =>
          json(202, {
            id: 'jg',
            type: 'suggestions.generate',
            status: 'queued',
            progress: 0,
            total: 1,
            error: null,
            result: null,
          }),
        ),
        route('GET', '/api/v1/jobs/jg', () =>
          json(200, {
            id: 'jg',
            type: 'suggestions.generate',
            status: 'running',
            progress: 0,
            total: 1,
            error: null,
            result: null,
          }),
        ),
      ],
      '/videos?page_size=200',
    );
    await screen.findByRole('table');
    await user.click(screen.getByRole('checkbox', { name: ko.videos.selectPage }));
    return { user, c };
  };

  it('TC-VF-212 정확히 200개까지는 생성 버튼이 켜져 있고, 201개가 되면 꺼지며 안내가 보이고 요청이 나가지 않는다', async () => {
    const { user, c } = await setup(true);
    const btn = () => screen.getByRole('button', { name: ko.videos.generate });
    expect(screen.getByText(ko.videos.selectedCount(200))).toBeInTheDocument();
    expect(btn()).toBeEnabled();
    expect(screen.queryByText(ko.videos.generateOver(200))).toBeNull();
    await user.click(screen.getByRole('button', { name: ko.pagination.next }));
    await user.click(await screen.findByRole('checkbox', { name: '테스트 영상 201 선택' }));
    expect(screen.getByText(ko.videos.selectedCount(201))).toBeInTheDocument();
    expect(screen.getByText(ko.videos.generateOver(200))).toBeInTheDocument();
    expect(btn()).toBeDisabled();
    await user.click(btn());
    expect(c.calls.some((x) => x.path === '/api/v1/suggestions/generate')).toBe(false);
  }, 30000);

  it('TC-VF-213 200개 선택 후 생성하면 영상 ID 200개가 CSRF 와 함께 한 번 전송된다', async () => {
    const { user, c } = await setup(false);
    await user.click(screen.getByRole('button', { name: ko.videos.generate }));
    await waitFor(() =>
      expect(c.calls.some((x) => x.path === '/api/v1/suggestions/generate')).toBe(true),
    );
    const call = c.calls.find((x) => x.path === '/api/v1/suggestions/generate')!;
    expect((call.body as { video_ids: string[] }).video_ids).toHaveLength(200);
    expect(new Set((call.body as { video_ids: string[] }).video_ids).size).toBe(200);
    expect(call.headers['x-csrf-token']).toBe('csrf-1');
  }, 30000);
});

// ---------- 로그아웃 실패 알림 / 홈 대기 안내 / 오류 경계 새로고침 ----------
describe('기타 상태 화면', () => {
  it('TC-VF-214 설정 > 세션 탭: 로그아웃이 서버에 닿지 못하면 오류 토스트가 보이고 화면은 그대로다', async () => {
    const user = userEvent.setup();
    let down = false;
    mountApp(
      [
        (r) => {
          if (down && r.method === 'DELETE') throw new TypeError('Failed to fetch');
          return undefined;
        },
        route('GET', '/api/v1/settings', () =>
          json(200, {
            daily_apply_cap: 10,
            suggestions_per_video: 3,
            tone: [],
            pin_enabled: false,
            mode: 'demo',
            read_only: { enable_live: false, live_allowlist: [], note: 'n' },
          }),
        ),
        route('GET', '/api/v1/google/status', () => json(200, { mode: 'demo', connected: false })),
      ],
      '/settings?tab=session',
    );
    const out = (await screen.findAllByRole('button', { name: ko.conn.logout })).at(-1)!;
    down = true;
    await user.click(out);
    await screen.findAllByText(/연결/);
    expect(screen.queryByText(ko.conn.loggedOutTitle)).toBeNull();
  });

  it('TC-VF-215 홈: 반영 대기(queued) 건수가 있으면 배치 화면으로 가는 안내가 보인다', async () => {
    mountApp([
      route('GET', '/api/v1/dashboard', () =>
        json(
          200,
          dashboard({
            counts: { videos: 5, excluded: 0, suggested: 0, approved: 0, queued: 3, applied: 0 },
          }),
        ),
      ),
    ]);
    expect(await screen.findByText(ko.home.todoQueued(3))).toBeInTheDocument();
    expect(screen.getByRole('link', { name: ko.home.gotoQueue })).toHaveAttribute(
      'href',
      '/batches',
    );
  });

  it('TC-VF-216 오류 경계 화면에는 "다음에 할 일" 과 새로고침 버튼이 있다', async () => {
    const swallow = (e: ErrorEvent) => e.preventDefault();
    window.addEventListener('error', swallow);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { suggestions: _x, ...broken } = detail([]);
    void _x;
    try {
      mountApp(
        [
          route('GET', '/api/v1/videos/vid00000001', () => json(200, broken)),
          route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
        ],
        '/videos/vid00000001',
      );
      const title = await screen.findByText(ko.app.crashTitle);
      const box = title.closest('[role="alert"]') as HTMLElement;
      expect(within(box).getByText(ko.state.nextStep, { exact: false })).toBeInTheDocument();
      expect(within(box).getByRole('button', { name: ko.app.reload })).toBeEnabled();
    } finally {
      window.removeEventListener('error', swallow);
    }
  });
});

// ---------- 방금 만든 작업이 잠깐 404 로 보이는 경우 (실서버 시험에서 관찰, DEF-VF-B01 의 프런트 쪽 완화) ----------
describe('작업 조회 404 재확인', () => {
  const jobBody = (status: string, progress = 0) => ({
    id: 'jq',
    type: 'videos.sync',
    status,
    progress,
    total: 2,
    error: null,
    result: null,
  });
  const emptyHome = () =>
    route('GET', '/api/v1/dashboard', () =>
      json(
        200,
        dashboard({
          counts: { videos: 0, excluded: 0, suggested: 0, approved: 0, queued: 0, applied: 0 },
        }),
      ),
    );

  it('TC-VF-217 처음 두 번은 404, 세 번째에 200 이면 오류 화면 없이 진행률이 보인다', async () => {
    const user = userEvent.setup();
    let n = 0;
    const c = mountApp([
      emptyHome(),
      route('POST', '/api/v1/videos/sync', () => json(202, jobBody('queued'))),
      route('GET', '/api/v1/jobs/jq', () => {
        n++;
        return n <= 2
          ? problem(404, 'job_not_found', '작업을 찾을 수 없습니다')
          : json(200, jobBody('running', 1));
      }),
    ]);
    await user.click(await screen.findByRole('button', { name: ko.home.syncDemo }));
    await screen.findByRole('progressbar', { name: ko.home.syncDemo }, { timeout: 6000 });
    expect(screen.queryByText('작업을 찾을 수 없습니다')).toBeNull();
    expect(c.calls.filter((x) => x.path === '/api/v1/jobs/jq').length).toBeGreaterThanOrEqual(3);
  }, 15000);

  it('TC-VF-218 계속 404 면 첫 요청 포함 정확히 4번(재확인 3번) 뒤에 오류가 보이고 더는 재확인하지 않는다', async () => {
    const user = userEvent.setup();
    const c = mountApp([
      emptyHome(),
      route('POST', '/api/v1/videos/sync', () => json(202, jobBody('queued'))),
      route('GET', '/api/v1/jobs/jq', () =>
        problem(404, 'job_not_found', '작업을 찾을 수 없습니다'),
      ),
    ]);
    await user.click(await screen.findByRole('button', { name: ko.home.syncDemo }));
    await screen.findAllByText('작업을 찾을 수 없습니다', undefined, { timeout: 6000 });
    expect(c.calls.filter((x) => x.path === '/api/v1/jobs/jq')).toHaveLength(4);
  }, 15000);

  it('TC-VF-219 404 가 아닌 오류(500)는 재확인 없이 바로 보인다', async () => {
    const user = userEvent.setup();
    const c = mountApp([
      emptyHome(),
      route('POST', '/api/v1/videos/sync', () => json(202, jobBody('queued'))),
      route('GET', '/api/v1/jobs/jq', () => problem(500, 'internal', '서버 오류')),
    ]);
    await user.click(await screen.findByRole('button', { name: ko.home.syncDemo }));
    await screen.findAllByText('서버 오류', undefined, { timeout: 2000 });
    expect(c.calls.filter((x) => x.path === '/api/v1/jobs/jq')).toHaveLength(1);
  });
});

// ---------- 세션/승인 보강 ----------
describe('세션 시작: 인증됐다는데 CSRF 토큰이 없는 응답', () => {
  it('TC-VF-220 auth/me 가 authenticated=true 인데 csrf_token=null 이면 세션을 새로 발급받아 토큰을 얻는다 (fail-safe)', async () => {
    const { client, calls } = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, { authenticated: true, pin_required: false, csrf_token: null }),
      ),
      route('POST', '/api/v1/auth/session', () => json(200, { csrf_token: 'fresh-token' })),
      route('PATCH', '/api/v1/settings', () => json(200, {})),
    ]);
    await client.bootstrap();
    expect(calls.some((c) => c.method === 'POST' && c.path === '/api/v1/auth/session')).toBe(true);
    await client.request('PATCH', '/api/v1/settings', { body: { daily_apply_cap: 5 } });
    expect(calls.find((c) => c.method === 'PATCH')!.headers['x-csrf-token']).toBe('fresh-token');
  });
});

describe('경고 제안 승인: 키보드(엔터) 우회 금지', () => {
  it('TC-VF-221 경고 확인 체크 없이 승인자 입력칸에서 엔터를 눌러도 승인 요청이 나가지 않는다', async () => {
    const user = userEvent.setup();
    const s = suggestion(9, {
      title: '엔터 우회 시험',
      validation_result: 'warn',
      reasons: [{ code: 'w', severity: 'warn', message: '주의' }],
    });
    const c = mountApp(
      [
        route('GET', '/api/v1/videos/vid00000001', () => json(200, detail([s]))),
        route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
        route('POST', '/api/v1/suggestions/9/approve', () =>
          json(200, { ...s, status: 'approved' }),
        ),
      ],
      '/videos/vid00000001',
    );
    const card = (await screen.findByRole('heading', { level: 3, name: s.title })).closest(
      'article',
    ) as HTMLElement;
    await user.click(within(card).getByRole('button', { name: '승인' }));
    const dlg = await screen.findByRole('dialog');
    await user.type(within(dlg).getByLabelText(/승인자/), '홍길동');
    const form = dlg.querySelector('form') as HTMLFormElement;
    // 엔터(암묵적 제출)는 브라우저에서 form 제출 이벤트가 된다. jsdom 은 암묵적 제출을 하지 않으므로 제출 이벤트를 직접 보낸다.
    fireEvent.submit(form);
    await new Promise((r) => setTimeout(r, 100));
    expect(c.calls.some((x) => x.path === '/api/v1/suggestions/9/approve')).toBe(false);
    await user.click(within(dlg).getByRole('checkbox'));
    fireEvent.submit(form);
    await waitFor(() =>
      expect(c.calls.some((x) => x.path === '/api/v1/suggestions/9/approve')).toBe(true),
    );
  });
});

// ---------- 서버 오류 코드(API.md·백엔드가 실제로 내는 코드) → 화면 안내 ----------
import { ErrorPanel } from '../src/components';

describe('오류 코드별 한국어 안내와 "다음에 할 일"', () => {
  // [상태, 코드, 서버 제목(한국어), 서버 hint]
  const withHint: [number, string, string, string][] = [
    [403, 'csrf_invalid', '요청 확인 토큰이 올바르지 않습니다.', '화면을 새로고침해 주세요.'],
    [403, 'origin_not_allowed', '허용되지 않은 출처입니다.', '127.0.0.1:8080 주소로 접속하세요.'],
    [
      403,
      'cross_site_request',
      '다른 사이트에서 온 요청입니다.',
      '주소창에 직접 입력해 접속하세요.',
    ],
    [
      401,
      'session_required',
      '세션이 없거나 만료되었습니다.',
      '화면을 새로고침해 다시 시작하세요.',
    ],
    [
      409,
      'idempotency_in_progress',
      '같은 요청을 처리 중입니다.',
      '잠시 뒤 같은 요청을 다시 보내세요.',
    ],
    [
      422,
      'idempotency_key_reuse',
      '같은 키로 다른 요청을 보냈습니다.',
      '화면을 새로고침해 주세요.',
    ],
    [409, 'video_excluded', '제외 대상 영상입니다.', '제외 사유를 확인하세요.'],
    [409, 'suggestion_blocked', '차단된 제안은 승인할 수 없습니다.', '다른 제목을 만들어 주세요.'],
    [
      409,
      'suggestion_state',
      '지금 상태에서는 할 수 없습니다.',
      '화면을 새로고침해 상태를 확인하세요.',
    ],
    [409, 'same_as_current', '현재 제목과 같습니다.', '다른 제목을 고르세요.'],
    [409, 'already_in_batch', '이미 다른 배치에 담겼습니다.', '배치 목록을 확인하세요.'],
    [
      409,
      'precheck_stale',
      '사전 점검 뒤에 상태가 바뀌었습니다.',
      '배치를 취소하고 새로 만드세요.',
    ],
    [
      409,
      'batch_not_draft',
      '이미 실행했거나 취소한 배치입니다.',
      '배치 목록에서 상태를 확인하세요.',
    ],
    [
      409,
      'later_change_exists',
      '이후 변경이 있어 되돌릴 수 없습니다.',
      '최신 변경부터 되돌려 주세요.',
    ],
    [409, 'pending_change_exists', '진행 중인 변경이 있습니다.', '끝난 뒤 다시 시도하세요.'],
    [
      422,
      'confirm_text_mismatch',
      '확인 문구가 일치하지 않습니다.',
      '화면에 표시된 문구를 그대로 입력하세요.',
    ],
    [
      422,
      'typed_video_id_mismatch',
      '영상 ID가 일치하지 않습니다.',
      '영상 ID를 그대로 입력하세요.',
    ],
    [502, 'gateway_error', '유튜브 응답을 확인하지 못했습니다.', '잠시 뒤 다시 시도하세요.'],
    [429, 'rate_limited', '요청이 너무 많습니다.', '잠시 뒤 다시 시도하세요.'],
    [
      429,
      'quota_exhausted',
      '오늘 사용량을 모두 썼습니다.',
      '태평양 시간 자정 이후 다시 시도하세요.',
    ],
    [429, 'pin_locked', 'PIN 입력이 잠겼습니다.', '잠금이 풀린 뒤 다시 입력하세요.'],
    [404, 'video_not_found', '영상을 찾을 수 없습니다.', '영상 목록에서 다시 선택하세요.'],
  ];
  it.each(withHint)(
    'TC-VF-222 %i %s: 서버 한국어 제목·hint 를 "다음에 할 일" 로 보이고 코드를 함께 표시한다',
    (status, code, title, hint) => {
      render(<ErrorPanel error={new ApiError({ status, code, title, hint })} />);
      const box = screen.getByRole('alert');
      expect(box).toHaveTextContent(hint);
      expect(box).toHaveTextContent(ko.state.nextStep);
      expect(within(box).getByText(code)).toBeInTheDocument();
      if (status !== 429) expect(box).toHaveTextContent(title);
      expect(box.textContent).toMatch(/[가-힣]/);
    },
  );

  it.each([
    [422, 'validation_error'],
    [422, 'title_invalid'],
    [409, 'pin_not_set'],
    [500, 'no_handler'],
    [401, 'pin_invalid'],
    [500, 'http_500'],
  ])(
    'TC-VF-223 %i %s: 서버가 hint 를 비워도 "다음에 할 일" 은 항상 한국어 문구로 채워진다',
    (status, code) => {
      render(
        <ErrorPanel error={new ApiError({ status, code, title: '요청을 처리하지 못했습니다' })} />,
      );
      const box = screen.getByRole('alert');
      const next = within(box).getByText(ko.state.nextStep, { exact: false }).closest('p')!;
      expect(
        next.textContent!.replace(ko.state.nextStep, '').replace(':', '').trim().length,
      ).toBeGreaterThan(5);
      expect(next.textContent).toMatch(/[가-힣]/);
    },
  );

  it('TC-VF-224 429 + Retry-After 는 "N초 뒤에 다시 시도" 안내가 hint 에 붙고, 한도 계열은 경고 톤 제목을 쓴다', () => {
    render(
      <ErrorPanel
        error={
          new ApiError({
            status: 429,
            code: 'rate_limited',
            title: 't',
            hint: '30초 뒤에 다시 시도해 주세요.',
          })
        }
      />,
    );
    const box = screen.getByRole('alert');
    expect(box).toHaveTextContent(ko.state.limitTitle);
    expect(box).toHaveTextContent('30초 뒤에');
  });

  it('TC-VF-225 서버 문구가 영어여도(예: 프록시 502) 화면의 고정 문구(제목·다음에 할 일·코드 라벨)는 한국어다', () => {
    render(
      <ErrorPanel
        error={new ApiError({ status: 502, code: 'http_502', title: '요청을 처리하지 못했습니다' })}
      />,
    );
    const box = screen.getByRole('alert');
    expect(box).toHaveTextContent(ko.state.nextStep);
    expect(box).toHaveTextContent(ko.state.codeLabel);
    expect(box).toHaveTextContent(ko.errors.http_502!);
  });

  it('TC-VF-226 일반 Error(코드 없음)도 크래시 없이 한국어 기본 안내와 unknown 코드를 보인다', () => {
    render(<ErrorPanel error={new Error('boom TypeError at /app/x.js')} />);
    const box = screen.getByRole('alert');
    expect(box).toHaveTextContent(ko.state.errorTitle);
    expect(box.textContent).not.toMatch(/boom|TypeError|\/app\//);
  });
});

describe('API 클라이언트: 호출자 중단 신호 정리', () => {
  it('TC-VF-227 요청이 끝나면(성공·실패 모두) 호출자 신호에 걸어 둔 리스너를 제거한다(반복 호출해도 쌓이지 않음)', async () => {
    const ctl = new AbortController();
    const add = vi.spyOn(ctl.signal, 'addEventListener');
    const remove = vi.spyOn(ctl.signal, 'removeEventListener');
    const okClient = new ApiClient({
      fetchImpl: (async () => new Response('{}', { status: 200 })) as unknown as typeof fetch,
    });
    for (let i = 0; i < 5; i++) await okClient.request('GET', '/api/v1/x', { signal: ctl.signal });
    const badClient = new ApiClient({
      fetchImpl: (async () => new Response('{}', { status: 500 })) as unknown as typeof fetch,
    });
    for (let i = 0; i < 5; i++)
      await badClient.request('GET', '/api/v1/x', { signal: ctl.signal }).catch(() => undefined);
    expect(add).toHaveBeenCalledTimes(10);
    expect(remove).toHaveBeenCalledTimes(10);
  });
});

// ---------- 작업 패널 폴링 / 오류 안내 우선순위 ----------
import { JobPanel } from '../src/pages/JobPanel';

describe('작업 패널(JobPanel) 폴링', () => {
  it('TC-VF-228 진행 중이면 1초마다 다시 읽어 진행률을 갱신하고, 끝나면 onDone 을 한 번만 부르고 폴링을 멈춘다', async () => {
    let n = 0;
    const done = vi.fn();
    const c = await connectedClient([
      route('GET', '/api/v1/jobs/jz', () => {
        n++;
        const status = n >= 3 ? 'succeeded' : 'running';
        return json(200, {
          id: 'jz',
          type: 'videos.sync',
          status,
          progress: Math.min(n - 1, 2),
          total: 2,
          error: null,
          result: null,
        });
      }),
    ]);
    renderWithApp(<JobPanel jobId="jz" label="시험 작업" onDone={done} />, c.client);
    await waitFor(
      () =>
        expect(
          (screen.getByRole('progressbar', { name: '시험 작업' }) as HTMLProgressElement).value,
        ).toBe(2),
      { timeout: 6000 },
    );
    await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
    const after = c.calls.filter((x) => x.path === '/api/v1/jobs/jz').length;
    expect(after).toBe(3);
    await new Promise((r) => setTimeout(r, 2300));
    expect(c.calls.filter((x) => x.path === '/api/v1/jobs/jz')).toHaveLength(after);
    expect(done).toHaveBeenCalledTimes(1);
  }, 20000);

  it('TC-VF-230 취소(cancelled)로 끝난 작업도 폴링을 멈추고 onDone 을 부른다', async () => {
    const done = vi.fn();
    const c = await connectedClient([
      route('GET', '/api/v1/jobs/jc', () =>
        json(200, {
          id: 'jc',
          type: 'batch.execute',
          status: 'cancelled',
          progress: 0,
          total: 1,
          error: null,
          result: null,
        }),
      ),
    ]);
    renderWithApp(<JobPanel jobId="jc" label="취소 작업" onDone={done} />, c.client);
    await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
    await new Promise((r) => setTimeout(r, 1500));
    expect(c.calls.filter((x) => x.path === '/api/v1/jobs/jc')).toHaveLength(1);
  }, 10000);
});

describe('오류 안내 우선순위', () => {
  it('TC-VF-229 서버가 hint 를 주면 화면 기본 안내(errorHints)보다 서버 hint 를 "다음에 할 일" 로 쓴다', () => {
    render(
      <ErrorPanel
        error={
          new ApiError({
            status: 401,
            code: 'pin_invalid',
            title: 't',
            hint: '서버가 준 안내 문장',
          })
        }
      />,
    );
    const box = screen.getByRole('alert');
    expect(box).toHaveTextContent('서버가 준 안내 문장');
    expect(box).not.toHaveTextContent(ko.errorHints.pin_invalid!);
  });
});

// ---------- 확인 문구 안내 표시도 실행 조건과 같은 기준 ----------
import { draftBatch } from '../src/test/fixtures';

describe('확인 문구 일치 안내', () => {
  it.each([
    ['뒤 공백', '실행 2건 '],
    ['앞 공백', ' 실행 2건'],
    ['일부', '실행 2'],
  ])('TC-VF-231 %s 가 있으면 안내는 ✕(불일치)이고 ✓ 가 아니다', async (_n, typed) => {
    const user = userEvent.setup();
    mountApp([route('GET', '/api/v1/batches/7', () => json(200, draftBatch()))], '/batches/7');
    const box = await screen.findByLabelText(/확인 문구 입력/);
    await user.type(box, typed);
    const status = box.parentElement!.querySelector('[aria-live="polite"]') as HTMLElement;
    expect(status.textContent).toContain('✕');
    expect(status.textContent).not.toContain('✓');
    await user.clear(box);
    await user.type(box, '실행 2건');
    expect(status.textContent).toContain('✓');
    await user.click(screen.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ }));
    expect(screen.getByRole('button', { name: '실행' })).toBeEnabled();
  });
});

// ---------- PIN 화면: 틀린 PIN 과 다른 거절을 구분 ----------
describe('PIN 화면 오류 구분', () => {
  const mountPin = (postSession: () => Response) => {
    const c = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, { authenticated: false, pin_required: true, csrf_token: null }),
      ),
      route('POST', '/api/v1/auth/session', postSession),
    ]);
    render(
      <Providers client={c.client}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    return c;
  };
  it('TC-VF-232 403(출처 거절)은 "PIN 이 틀렸다" 가 아니라 서버가 준 사유와 다음에 할 일을 보여 준다 [DEF-VF-004]', async () => {
    const user = userEvent.setup();
    mountPin(() =>
      problem(
        403,
        'origin_not_allowed',
        '허용되지 않은 출처의 요청입니다.',
        '',
        'http://127.0.0.1:8080 주소로 접속해 사용하세요.',
      ),
    );
    await user.type(await screen.findByLabelText(ko.conn.pinLabel), '1234{Enter}');
    expect(await screen.findByText('허용되지 않은 출처의 요청입니다.')).toBeInTheDocument();
    expect(screen.queryByText(ko.conn.pinWrong)).toBeNull();
  });
  it('TC-VF-233 401 pin_invalid 는 입력칸 아래에 "PIN 이 올바르지 않습니다" 로 보인다', async () => {
    const user = userEvent.setup();
    mountPin(() => problem(401, 'pin_invalid', 'PIN 이 올바르지 않습니다.'));
    await user.type(await screen.findByLabelText(ko.conn.pinLabel), '0000{Enter}');
    expect(await screen.findByText(ko.conn.pinWrong)).toBeInTheDocument();
  });
  it('TC-VF-234 429 pin_locked 는 틀린 PIN 문구가 아니라 잠금 안내(한도 계열)를 보인다', async () => {
    const user = userEvent.setup();
    mountPin(() =>
      problem(429, 'pin_locked', 'PIN 입력이 잠겼습니다.', '', '5분 뒤 다시 입력하세요.'),
    );
    await user.type(await screen.findByLabelText(ko.conn.pinLabel), '0000{Enter}');
    expect((await screen.findAllByText(/PIN 입력이 잠겼습니다|한도/)).length).toBeGreaterThan(0);
    expect(screen.queryByText(ko.conn.pinWrong)).toBeNull();
  });
});

describe('오류 톤 구분', () => {
  it('TC-VF-235 한도 계열(429)은 경고 톤, 그 밖의 오류는 위험 톤 스타일을 쓴다', () => {
    const { container, rerender } = render(
      <ErrorPanel error={new ApiError({ status: 429, code: 'rate_limited', title: 't' })} />,
    );
    expect(container.querySelector('.callout--warning')).not.toBeNull();
    expect(container.querySelector('.callout--danger')).toBeNull();
    rerender(<ErrorPanel error={new ApiError({ status: 500, code: 'http_500', title: 't' })} />);
    expect(container.querySelector('.callout--danger')).not.toBeNull();
  });
});

describe('작업 창: 이전 작업의 읽기 오류가 새 작업으로 새지 않는다', () => {
  it('TC-VF-236 첫 작업이 404 로 닫을 수 있게 된 뒤, 새 작업이 진행 중이면 닫기가 다시 꺼진다 [X11]', async () => {
    const user = userEvent.setup();
    let n = 0;
    const jobBody = (id: string, status: string) => ({
      id,
      type: 'suggestions.generate',
      status,
      progress: 0,
      total: 1,
      error: null,
      result: null,
    });
    mountApp(
      [
        route('GET', '/api/v1/videos', () =>
          json(200, { items: [video(1)], total: 1, page: 1, page_size: 50 }),
        ),
        route('POST', '/api/v1/suggestions/generate', () =>
          json(202, jobBody(n++ === 0 ? 'ja' : 'jb', 'queued')),
        ),
        route('GET', '/api/v1/jobs/ja', () =>
          problem(404, 'job_not_found', '작업을 찾을 수 없습니다'),
        ),
        route('GET', '/api/v1/jobs/jb', () => json(200, jobBody('jb', 'running'))),
      ],
      '/videos',
    );
    await user.click(await screen.findByRole('checkbox', { name: '테스트 영상 1 선택' }));
    await user.click(screen.getByRole('button', { name: ko.videos.generate }));
    await screen.findAllByText('작업을 찾을 수 없습니다', undefined, { timeout: 6000 });
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: '닫기' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await user.click(screen.getByRole('button', { name: ko.videos.generate }));
    const dlg = await screen.findByRole('dialog');
    await screen.findByRole('progressbar', { name: ko.videos.generateTitle });
    expect(within(dlg).getByRole('button', { name: '닫기' })).toBeDisabled();
  }, 20000);
});

describe('PIN 화면: 빈 PIN 제출 금지', () => {
  it('TC-VF-237 PIN 을 비워 둔 채 제출(엔터)해도 세션 발급 요청이 나가지 않는다', async () => {
    const c = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, { authenticated: false, pin_required: true, csrf_token: null }),
      ),
      route('POST', '/api/v1/auth/session', () =>
        problem(401, 'pin_invalid', 'PIN 이 올바르지 않습니다.'),
      ),
    ]);
    render(
      <Providers client={c.client}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    const input = await screen.findByLabelText(ko.conn.pinLabel);
    const before = c.calls.filter((x) => x.path === '/api/v1/auth/session').length;
    fireEvent.submit(input.closest('form')!);
    await new Promise((r) => setTimeout(r, 150));
    expect(c.calls.filter((x) => x.path === '/api/v1/auth/session').length).toBe(before);
    expect(screen.getByRole('button', { name: ko.conn.pinSubmit })).toBeDisabled();
  });
});

// ---------- 홈·목록 보강: 라이브 표시, 불러오기/생성 요청 실패 ----------
describe('홈·영상 목록: 실패와 라이브 표시', () => {
  it('TC-VF-238 서버가 live_enabled=true 를 주면 홈이 "켜짐" 을 글자로 보여 준다(꺼짐 문구는 없다)', async () => {
    mountApp([
      route('GET', '/api/v1/dashboard', () => json(200, dashboard({ live_enabled: true }))),
    ]);
    expect(await screen.findByText(ko.home.liveOn)).toBeInTheDocument();
    expect(screen.queryByText(ko.home.liveOff)).toBeNull();
  });
  it('TC-VF-239 live_enabled=false 면 "꺼짐" 이고, 이력의 데모 모드 표기는 ko.ts 문구다', async () => {
    mountApp([
      route('GET', '/api/v1/dashboard', () => json(200, dashboard({ live_enabled: false }))),
    ]);
    expect(await screen.findByText(ko.home.liveOff)).toBeInTheDocument();
    expect(ko.history.modeDemo).toBe('데모');
  });
  it('TC-VF-240 데모 영상 불러오기 요청이 500 이면 오류 안내가 보이고 버튼이 다시 켜진다', async () => {
    const user = userEvent.setup();
    mountApp([
      route('GET', '/api/v1/dashboard', () =>
        json(
          200,
          dashboard({
            counts: { videos: 0, excluded: 0, suggested: 0, approved: 0, queued: 0, applied: 0 },
          }),
        ),
      ),
      route('POST', '/api/v1/videos/sync', () =>
        problem(500, 'internal', '서버 오류', '', '잠시 뒤 다시 시도하세요.'),
      ),
    ]);
    await user.click(await screen.findByRole('button', { name: ko.home.syncDemo }));
    expect(await screen.findByText('잠시 뒤 다시 시도하세요.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: ko.home.syncDemo })).toBeEnabled();
  });
  it('TC-VF-241 AI 제안 생성 요청이 409(제외 영상 포함)로 거절되면 오류 창이 뜨고 닫을 수 있으며 선택은 유지된다', async () => {
    const user = userEvent.setup();
    mountApp(
      [
        route('GET', '/api/v1/videos', () =>
          json(200, { items: [video(1)], total: 1, page: 1, page_size: 50 }),
        ),
        route('POST', '/api/v1/suggestions/generate', () =>
          problem(409, 'video_excluded', '제외 대상 영상입니다.', '', '제외 사유를 확인하세요.'),
        ),
      ],
      '/videos',
    );
    await user.click(await screen.findByRole('checkbox', { name: '테스트 영상 1 선택' }));
    await user.click(screen.getByRole('button', { name: ko.videos.generate }));
    const dlg = await screen.findByRole('dialog');
    expect(within(dlg).getByText('제외 사유를 확인하세요.')).toBeInTheDocument();
    await user.click(within(dlg).getByRole('button', { name: '닫기' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByRole('checkbox', { name: '테스트 영상 1 선택' })).toBeChecked();
    // 같은 오류 창은 Esc 로도 닫힌다
    await user.click(screen.getByRole('button', { name: ko.videos.generate }));
    await screen.findByRole('dialog');
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});
