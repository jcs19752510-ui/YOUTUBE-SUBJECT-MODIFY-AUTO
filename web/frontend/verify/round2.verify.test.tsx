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
      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent(ko.app.crashTitle);
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
    await screen.findAllByText('작업을 찾을 수 없습니다');
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
      document.dispatchEvent(new Event('visibilitychange'));
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
