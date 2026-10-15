import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Providers } from './providers';
import { axeViolations, json, makeClient, problem, renderWithApp, route, type Handler } from '../test/utils';
import { AuthGate } from './AuthGate';
import { LoginForm } from './LoginForm';
import { SetupForm } from './SetupForm';
import { warnSeconds } from './IdleLogout';

const ME_LOGIN = { authenticated: false, pin_required: false, csrf_token: null, login_required: true };
const ME_OK = (idle: number | null = 600) => ({
  authenticated: true,
  pin_required: false,
  csrf_token: 'c1',
  login_required: false,
  admin_login_id: 'test-admin',
  idle_timeout_seconds: idle,
});
const LOGIN_OK = { csrf_token: 'c2', admin_login_id: 'test-admin', idle_timeout_seconds: 3600 };
const PW = 'Test-Passw0rd!';
// 테스트 하네스의 토스트 영역에도 빈 role=alert 가 있어 카드 안내 문구(.auth-card__msg)만 고른다
const findCardAlert = () =>
  waitFor(() => {
    const el = document.querySelector('.auth-card__msg[role="alert"]');
    if (!el) throw new Error('카드 안내 문구(alert) 없음');
    return el as HTMLElement;
  });
// 제품 변경 근거(선생님 지시): 로그인 화면 제목이 '로그인' -> '유튜브 제목 로그인 입력화면' 로 바뀜. 기대값은 이 문구만 갱신.
const LOGIN_TITLE = '유튜브 제목 로그인 입력화면';
const ME_SETUP = { authenticated: false, pin_required: false, csrf_token: null, login_required: false, setup_required: true };

describe('client 로그인 모드', () => {
  it('login_required 이면 익명 세션을 만들지 않고 login_required 상태가 된다', async () => {
    const { client, calls } = makeClient([route('GET', '/api/v1/auth/me', () => json(200, ME_LOGIN))]);
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('login_required');
    expect(calls.some((c) => c.method === 'POST' && c.path === '/api/v1/auth/session')).toBe(false);
    await expect(client.request('POST', '/api/v1/x')).rejects.toMatchObject({ code: 'login_required' });
    expect(calls.some((c) => c.path === '/api/v1/auth/session')).toBe(false);
  });

  it('login 성공: csrf·아이디·한도 저장, online', async () => {
    const { client, calls } = makeClient([
      route('POST', '/api/v1/auth/login', () => json(200, LOGIN_OK)),
      route('POST', '/api/v1/y', () => json(200, {})),
    ]);
    await client.login('test-admin', PW);
    expect(client.getSnapshot().state).toBe('online');
    expect(client.adminLoginId).toBe('test-admin');
    expect(client.idleTimeoutSeconds).toBe(3600);
    await client.request('POST', '/api/v1/y');
    expect(calls[calls.length - 1].headers['x-csrf-token']).toBe('c2');
  });

  it('login 401 은 login_invalid 로 던지고 상태는 바뀌지 않는다', async () => {
    const { client } = makeClient([
      route('POST', '/api/v1/auth/login', () => problem(401, 'login_invalid', '실패')),
    ]);
    await expect(client.login('test-admin', 'x')).rejects.toMatchObject({ status: 401, code: 'login_invalid' });
    expect(client.getSnapshot().state).toBe('starting');
  });

  it('로그인 모드에서 사용 중 401 session_required 이면 재발급 없이 login_required + expired', async () => {
    const { client, calls } = makeClient([
      route('GET', '/api/v1/auth/me', () => json(200, ME_OK())),
      route('GET', '/api/v1/z', () => problem(401, 'session_required', '세션')),
    ]);
    await client.bootstrap();
    await expect(client.request('GET', '/api/v1/z')).rejects.toMatchObject({ code: 'session_expired' });
    expect(client.getSnapshot()).toMatchObject({ state: 'login_required', expired: true });
    expect(calls.filter((c) => c.path === '/api/v1/auth/session')).toHaveLength(0);
    expect(calls.filter((c) => c.path === '/api/v1/auth/me')).toHaveLength(1);
  });

  it('로그인 모드 logout 성공 뒤 login_required, 비로그인 모드는 loggedout 유지', async () => {
    const a = makeClient([
      route('GET', '/api/v1/auth/me', () => json(200, ME_OK())),
      route('DELETE', '/api/v1/auth/session', () => json(204, null)),
    ]);
    await a.client.bootstrap();
    await a.client.logout();
    expect(a.client.getSnapshot()).toMatchObject({ state: 'login_required', expired: false });
    const b = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, { authenticated: true, pin_required: false, csrf_token: 'c' }),
      ),
      route('DELETE', '/api/v1/auth/session', () => json(204, null)),
    ]);
    await b.client.bootstrap();
    await b.client.logout();
    expect(b.client.getSnapshot().state).toBe('loggedout');
  });
});

describe('LoginForm', () => {
  const setup = (h: Handler[], onDone = vi.fn()) => {
    const { client } = makeClient(h);
    renderWithApp(<LoginForm onDone={onDone} />, client);
    return { client, onDone };
  };

  it('빈 입력이면 버튼이 꺼져 있고 요청하지 않는다', () => {
    setup([]);
    expect(screen.getByRole('button', { name: '로그인' })).toBeDisabled();
  });

  it('성공하면 onDone 호출, 비밀번호 입력은 비워진다', async () => {
    const user = userEvent.setup();
    const { onDone } = setup([route('POST', '/api/v1/auth/login', () => json(200, LOGIN_OK))]);
    await user.type(screen.getByLabelText('아이디'), 'test-admin');
    await user.type(screen.getByLabelText('비밀번호'), PW);
    await user.click(screen.getByRole('button', { name: '로그인' }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(screen.getByLabelText('비밀번호')).toHaveValue('');
  });

  it('401 이면 고정 문구, 429 이면 대기 시간 안내, 네트워크 오류 안내', async () => {
    const user = userEvent.setup();
    let mode: 401 | 429 | 0 = 401;
    setup([
      () => {
        if (mode === 0) throw new TypeError('Failed to fetch');
        return undefined;
      },
      route('POST', '/api/v1/auth/login', () =>
        mode === 401
          ? problem(401, 'login_invalid', '실패')
          : new Response(JSON.stringify({ code: 'login_locked', title: '잠김' }), {
              status: 429,
              headers: { 'Content-Type': 'application/problem+json', 'Retry-After': '300' },
            }),
      ),
    ]);
    await user.type(screen.getByLabelText('아이디'), 'test-admin');
    await user.type(screen.getByLabelText('비밀번호'), 'wrong');
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(await screen.findByText('아이디 또는 비밀번호가 올바르지 않습니다.')).toBeInTheDocument();
    mode = 429;
    await user.type(screen.getByLabelText('비밀번호'), 'wrong');
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(await screen.findByText(/300초 뒤에 다시 시도/)).toBeInTheDocument();
    mode = 0;
    await user.type(screen.getByLabelText('비밀번호'), 'wrong');
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(await screen.findByText(/서버에 연결할 수 없습니다/)).toBeInTheDocument();
  });

  it('접근성: label 연결, 비밀번호 type=password, autocomplete, axe 위반 없음, 값이 URL·저장소에 남지 않음', async () => {
    const user = userEvent.setup();
    const { client } = makeClient([]);
    const { container } = renderWithApp(<LoginForm expired />, client);
    const id = screen.getByLabelText('아이디');
    const pw = screen.getByLabelText('비밀번호');
    expect(id).toHaveAttribute('autocomplete', 'username');
    expect(id).toHaveAttribute('name', 'username');
    expect(pw).toHaveAttribute('type', 'password');
    expect(pw).toHaveAttribute('autocomplete', 'current-password');
    expect(screen.getByText(/자동 로그아웃되었습니다/)).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
    await user.type(id, 'test-admin');
    await user.type(pw, PW);
    expect(window.location.href).not.toContain('test-admin');
    expect(JSON.stringify({ ...localStorage })).not.toContain(PW);
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(PW);
  });
});

describe('AuthGate 로그인', () => {
  it('login_required → 폼, 로그인 후 children', async () => {
    const user = userEvent.setup();
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () => json(200, ME_LOGIN)),
      route('POST', '/api/v1/auth/login', () => json(200, LOGIN_OK)),
    ]);
    renderWithApp(<AuthGate><p>비밀 데이터</p></AuthGate>, client);
    expect(await screen.findByRole('heading', { name: LOGIN_TITLE })).toBeInTheDocument();
    expect(screen.queryByText('비밀 데이터')).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('아이디'), 'test-admin');
    await user.type(screen.getByLabelText('비밀번호'), PW);
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(await screen.findByText('비밀 데이터')).toBeInTheDocument();
  });

  it('사용 중 만료되면 데이터 화면을 가리고 만료 안내와 함께 로그인 폼을 보여 준다', async () => {
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () => json(200, ME_OK(null))),
      route('GET', '/api/v1/z', () => problem(401, 'session_required', '세션')),
    ]);
    renderWithApp(<AuthGate><p>비밀 데이터</p></AuthGate>, client);
    expect(await screen.findByText('비밀 데이터')).toBeInTheDocument();
    await act(async () => {
      await client.request('GET', '/api/v1/z').catch((e: unknown) => e);
    });
    expect(await screen.findByRole('heading', { name: LOGIN_TITLE })).toBeInTheDocument();
    expect(screen.queryByText('비밀 데이터')).not.toBeInTheDocument();
    expect(screen.getByText(/로그인 시간이 지나 자동 로그아웃되었습니다/)).toBeInTheDocument();
  });
});

describe('IdleLogout', () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout', 'Date'] }));
  afterEach(() => vi.useRealTimers());

  const mount = async (idle: number) => {
    const { client, calls } = makeClient([
      route('GET', '/api/v1/auth/me', () => json(200, ME_OK(idle))),
      route('DELETE', '/api/v1/auth/session', () => json(204, null)),
    ]);
    render(
      <Providers client={client}>
        <MemoryRouter>
          <AuthGate><p>데이터</p></AuthGate>
        </MemoryRouter>
      </Providers>,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getByText('데이터')).toBeInTheDocument();
    return { client, calls };
  };
  const adv = (s: number) => act(async () => { await vi.advanceTimersByTimeAsync(s * 1000); });

  it('경고 시점 계산: 5분 상한, 짧은 한도는 1/6', () => {
    expect(warnSeconds(3600)).toBe(300);
    expect(warnSeconds(600)).toBe(100);
    expect(warnSeconds(30)).toBe(5);
    expect(warnSeconds(3)).toBe(1);
  });

  it('한도가 없으면 기능 비활성(경고·로그아웃 없음)', async () => {
    const { calls } = await mount(0);
    await adv(7200);
    expect(screen.queryByText('곧 자동 로그아웃됩니다')).not.toBeInTheDocument();
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
  });

  it('한도 5분 전(3600초 → 3300초)에 경고, 계속 사용 누르면 /auth/me 호출 후 리셋', async () => {
    const { calls } = await mount(3600);
    await adv(3290);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await adv(20);
    expect(screen.getByRole('dialog', { name: '곧 자동 로그아웃됩니다' })).toBeInTheDocument();
    expect(screen.getByText(/4분 \d+초 뒤 자동 로그아웃/)).toBeInTheDocument();
    const meBefore = calls.filter((c) => c.path === '/api/v1/auth/me').length;
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '계속 사용' }));
      await vi.advanceTimersByTimeAsync(5);
    });
    expect(calls.filter((c) => c.path === '/api/v1/auth/me').length).toBe(meBefore + 1);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await adv(3000);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
  });

  it('활동하면 경고 전에 타이머가 리셋된다', async () => {
    await mount(600);
    await adv(400);
    fireEvent.mouseMove(window);
    await adv(400);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('한도에 도달하면 logout 후 만료 안내가 있는 로그인 화면', async () => {
    const { calls } = await mount(600);
    await adv(601);
    expect(calls.some((c) => c.method === 'DELETE' && c.path === '/api/v1/auth/session')).toBe(true);
    expect(screen.getByRole('heading', { name: LOGIN_TITLE })).toBeInTheDocument();
    expect(screen.queryByText('데이터')).not.toBeInTheDocument();
    expect(screen.getByText(/자동 로그아웃되었습니다/)).toBeInTheDocument();
  });

  it('logout 이 실패해도 로그인 화면으로 간다', async () => {
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () => json(200, ME_OK(60))),
      route('DELETE', '/api/v1/auth/session', () => problem(500, 'boom', '실패')),
    ]);
    render(
      <Providers client={client}>
        <MemoryRouter>
          <AuthGate><p>데이터</p></AuthGate>
        </MemoryRouter>
      </Providers>,
    );
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    await adv(61);
    expect(screen.getByRole('heading', { name: LOGIN_TITLE })).toBeInTheDocument();
    expect(client.getSnapshot().expired).toBe(true);
  });

  it('절전 복귀: 시계가 한도를 넘겨 점프한 뒤 탭이 보이면 즉시 로그아웃', async () => {
    const { calls } = await mount(600);
    vi.setSystemTime(Date.now() + 700_000); // 타이머는 멈춘 채 시계만 점프
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(5);
    });
    expect(calls.some((c) => c.method === 'DELETE')).toBe(true);
    expect(screen.getByRole('heading', { name: LOGIN_TITLE })).toBeInTheDocument();
  });

  it('경고 중에는 마우스 이동만으로 연장되지 않는다', async () => {
    await mount(600);
    await adv(510);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.mouseMove(window);
    await adv(2);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('Layout 로그인 표시', () => {
  it('로그인 아이디와 로그아웃 버튼이 보이고 비밀번호는 보이지 않는다', async () => {
    const { App } = await import('./App');
    const { dashboard } = await import('../test/fixtures');
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () => json(200, ME_OK(null))),
      route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
    ]);
    renderWithApp(<App />, client);
    expect(await screen.findByText('관리자: test-admin')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '로그아웃' })).toBeInTheDocument();
  });
});


describe('client 최초 계정 만들기', () => {
  it('setup_required 이면 익명 세션 없이 setup_required 상태', async () => {
    const { client, calls } = makeClient([route('GET', '/api/v1/auth/me', () => json(200, ME_SETUP))]);
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('setup_required');
    expect(calls.some((c) => c.path === '/api/v1/auth/session')).toBe(false);
  });

  it('setup 성공: 본문은 아이디·비밀번호만, csrf 저장, online', async () => {
    const { client, calls } = makeClient([route('POST', '/api/v1/auth/setup', () => json(200, LOGIN_OK))]);
    await client.setup('testadmin', PW);
    expect(client.getSnapshot().state).toBe('online');
    expect(client.adminLoginId).toBe('test-admin');
    const c = calls.find((x) => x.path === '/api/v1/auth/setup');
    expect(c?.body).toEqual({ login_id: 'testadmin', password: PW });
  });

  it('setup 409 setup_closed 이면 login_required 로 바꾸고 던진다', async () => {
    const { client } = makeClient([route('POST', '/api/v1/auth/setup', () => problem(409, 'setup_closed', '닫힘'))]);
    await expect(client.setup('testadmin', PW)).rejects.toMatchObject({ code: 'setup_closed' });
    expect(client.getSnapshot().state).toBe('login_required');
  });
});

describe('SetupForm', () => {
  const mount = (h: Handler[], onDone = vi.fn()) => {
    const { client, calls } = makeClient(h);
    const r = renderWithApp(<SetupForm onDone={onDone} />, client);
    return { client, calls, onDone, ...r };
  };
  const fill = async (user: ReturnType<typeof userEvent.setup>, id: string, pw: string, cf: string) => {
    if (id) await user.type(screen.getByLabelText('아이디'), id);
    if (pw) await user.type(screen.getByLabelText('비밀번호', { exact: true }), pw);
    if (cf) await user.type(screen.getByLabelText('비밀번호 확인'), cf);
    await user.click(screen.getByRole('button', { name: '계정 만들기' }));
  };

  it('제목·안내문이 보이고 처음 안내 문구가 나온다', () => {
    mount([]);
    expect(screen.getByRole('heading', { name: '관리자 계정 만들기' })).toBeInTheDocument();
    expect(screen.getByText('처음 한 번만 만듭니다. 이 아이디와 비밀번호로 이후 로그인합니다.')).toBeInTheDocument();
    expect(screen.getByText('아이디를 입력해 주세요.')).toBeInTheDocument();
  });

  it.each([
    ['아이디가 3자', 'abc', PW, PW, '아이디는 영문·숫자 4~20자'],
    ['아이디에 한글/기호', 'test-admin', PW, PW, '아이디는 영문·숫자 4~20자'],
    ['비밀번호 7자', 'testadmin', '1234567', '1234567', '비밀번호는 8~64자'],
    ['비밀번호 불일치', 'testadmin', PW, PW + 'x', '두 비밀번호가 서로 다릅니다'],
  ])('화면 검사: %s 이면 서버를 부르지 않는다', async (_n, id, pw, cf, text) => {
    const user = userEvent.setup();
    const { calls } = mount([]);
    await fill(user, id, pw, cf);
    expect(await findCardAlert()).toHaveTextContent(text);
    expect(calls.some((c) => c.path === '/api/v1/auth/setup')).toBe(false);
  });

  it('성공하면 onDone, 비밀번호 입력은 비워지고 확인값은 서버로 가지 않는다', async () => {
    const user = userEvent.setup();
    const { onDone, calls } = mount([route('POST', '/api/v1/auth/setup', () => json(200, LOGIN_OK))]);
    await fill(user, 'testadmin', PW, PW);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const c = calls.find((x) => x.path === '/api/v1/auth/setup');
    expect(Object.keys(c?.body as object).sort()).toEqual(['login_id', 'password']);
    expect(screen.getByLabelText('비밀번호', { exact: true })).toHaveValue('');
  });

  it('서버 setup_invalid 문구를 그대로 보여 준다', async () => {
    const user = userEvent.setup();
    mount([route('POST', '/api/v1/auth/setup', () => problem(422, 'setup_invalid', '규칙', '서버 규칙 위반 문구'))]);
    await fill(user, 'testadmin', PW, PW);
    expect(await findCardAlert()).toHaveTextContent('서버 규칙 위반 문구');
  });

  it('409 setup_closed 이면 안내 후 AuthGate 가 로그인 화면으로 전환', async () => {
    const user = userEvent.setup();
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () => json(200, ME_SETUP)),
      route('POST', '/api/v1/auth/setup', () => problem(409, 'setup_closed', '닫힘')),
    ]);
    renderWithApp(<AuthGate><p>비밀 데이터</p></AuthGate>, client);
    expect(await screen.findByRole('heading', { name: '관리자 계정 만들기' })).toBeInTheDocument();
    expect(screen.queryByText('비밀 데이터')).not.toBeInTheDocument();
    await fill(user, 'testadmin', PW, PW);
    expect(await screen.findByRole('heading', { name: LOGIN_TITLE })).toBeInTheDocument();
  });

  it('AuthGate: 계정 만들기 성공 시 바로 앱 화면', async () => {
    const user = userEvent.setup();
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () => json(200, ME_SETUP)),
      route('POST', '/api/v1/auth/setup', () => json(200, LOGIN_OK)),
    ]);
    renderWithApp(<AuthGate><p>비밀 데이터</p></AuthGate>, client);
    await screen.findByRole('heading', { name: '관리자 계정 만들기' });
    await fill(user, 'testadmin', PW, PW);
    expect(await screen.findByText('비밀 데이터')).toBeInTheDocument();
  });

  it('접근성·보안: label, autocomplete new-password, axe 위반 없음, 값이 URL·저장소·console 에 남지 않음', async () => {
    const user = userEvent.setup();
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m));
    const { container } = mount([]);
    const pw = screen.getByLabelText('비밀번호', { exact: true });
    expect(pw).toHaveAttribute('type', 'password');
    expect(pw).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('비밀번호 확인')).toHaveAttribute('type', 'password');
    expect(screen.getByLabelText('아이디')).toHaveAttribute('autocomplete', 'username');
    expect(await axeViolations(container)).toEqual([]);
    await user.type(screen.getByLabelText('아이디'), 'testadmin');
    await user.type(pw, PW);
    await user.type(screen.getByLabelText('비밀번호 확인'), PW);
    await user.click(screen.getByRole('button', { name: '계정 만들기' }));
    expect(window.location.href).not.toContain(PW);
    expect(JSON.stringify({ ...localStorage })).not.toContain(PW);
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(PW);
    for (const s of spies) expect(JSON.stringify(s.mock.calls)).not.toContain(PW);
    spies.forEach((s) => s.mockRestore());
  });
});

describe('LoginForm 새 구성', () => {
  it('빨간 안내 문구: 처음 아이디 안내 → 오류가 나면 오류 문구(role=alert)', async () => {
    const user = userEvent.setup();
    const { client } = makeClient([route('POST', '/api/v1/auth/login', () => problem(401, 'login_invalid', '실패'))]);
    renderWithApp(<LoginForm />, client);
    expect(screen.getByText('아이디를 입력해 주세요.')).toBeInTheDocument();
    expect(screen.getByLabelText('아이디')).toHaveAttribute('placeholder', '아이디(영숫자 4~20자)');
    expect(screen.getByLabelText('비밀번호')).toHaveAttribute('placeholder', '비밀번호(8~64자)');
    await user.type(screen.getByLabelText('아이디'), 'testadmin');
    await user.type(screen.getByLabelText('비밀번호'), 'wrong-pass');
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(await findCardAlert()).toHaveTextContent('아이디 또는 비밀번호가 올바르지 않습니다.');
  });
});
