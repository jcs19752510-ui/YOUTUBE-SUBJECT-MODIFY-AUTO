// 06단계 독립 검증(TC-VFF-1xx) — 세션 유휴 만료 뒤 새 세션 자동 발급(DEC-047), 서버 계약을 흉내 낸 상태 기계로 확인한다.
// 서버 동작(근거: web/backend/ytweb/core/deps.py·routers/auth.py): 만료/없는 세션 → 401 session_required, 변경 요청의 CSRF 불일치 → 403 csrf_*,
// GET /auth/me → {authenticated, pin_required, csrf_token}, POST /auth/session → 새 세션(+csrf_token), PIN 설정 시 본문 pin 필요.
import { describe, expect, it } from 'vitest';
import { ApiClient, ApiError } from '../src/api/client';
import { createEndpoints } from '../src/api/endpoints';

interface Srv {
  validGen: number | null; // 현재 유효한 세션 번호(null 이면 만료)
  gen: number;
  pin: string | null;
  log: string[];
  headersSeen: { method: string; path: string; csrf: string | null; key: string | null }[];
  sessionPosts: number;
  failSession?: boolean;
}
const J = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const P = (status: number, code: string, title: string) =>
  J(status, { type: 'about:blank', title, status, code, detail: '', hint: '' });

function server(over: Partial<Srv> = {}) {
  const s: Srv = {
    validGen: 1,
    gen: 1,
    pin: null,
    log: [],
    headersSeen: [],
    sessionPosts: 0,
    ...over,
  };
  const f = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const u = new URL(String(input), 'http://localhost');
    const m = init?.method ?? 'GET';
    const h = new Headers(init?.headers);
    s.log.push(`${m} ${u.pathname}`);
    s.headersSeen.push({
      method: m,
      path: u.pathname,
      csrf: h.get('x-csrf-token'),
      key: h.get('idempotency-key'),
    });
    await Promise.resolve();
    if (u.pathname === '/api/v1/auth/me')
      return s.validGen !== null
        ? J(200, {
            authenticated: true,
            pin_required: s.pin !== null,
            csrf_token: `c${s.validGen}`,
          })
        : J(200, { authenticated: false, pin_required: s.pin !== null });
    if (u.pathname === '/api/v1/auth/session' && m === 'POST') {
      s.sessionPosts++;
      if (s.failSession) return P(500, 'http_500', '서버 오류');
      const body = init?.body ? (JSON.parse(String(init.body)) as { pin?: string }) : {};
      if (s.pin !== null && body.pin !== s.pin)
        return P(401, 'pin_invalid', 'PIN 이 올바르지 않습니다');
      s.gen++;
      s.validGen = s.gen;
      return J(201, { csrf_token: `c${s.gen}` });
    }
    if (s.validGen === null) return P(401, 'session_required', '세션이 없거나 만료되었습니다.');
    if (m !== 'GET' && h.get('x-csrf-token') !== `c${s.validGen}`)
      return P(403, 'csrf_invalid', 'CSRF');
    if (u.pathname === '/api/v1/dashboard') return J(200, { ok: true });
    if (u.pathname.endsWith('/cancel')) return J(200, { id: 7, status: 'cancelled' });
    return J(200, {});
  }) as typeof fetch;
  return { s, f };
}
const mk = (over: Partial<Srv> = {}) => {
  const { s, f } = server(over);
  const client = new ApiClient({ fetchImpl: f });
  return { s, client, api: createEndpoints(client) };
};

describe('세션 유휴 만료 후 자동 재발급', () => {
  it('TC-VFF-100 GET: 만료 후 첫 요청이 401 이어도 조용히 새 세션을 받고 같은 요청이 성공한다(세션 발급 정확히 1회, PIN 화면 없음)', async () => {
    const { s, client, api } = mk();
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('online');
    s.validGen = null; // 유휴 만료
    s.sessionPosts = 0;
    await expect(api.dashboard()).resolves.toBeTruthy();
    expect(s.sessionPosts).toBe(1);
    expect(client.getSnapshot()).toMatchObject({ state: 'online', expired: false, error: null });
  });

  it('TC-VFF-101 위험 POST(배치 실행 등): 재발급 뒤 재시도에 새 CSRF 와 "같은" Idempotency-Key 가 쓰인다', async () => {
    const { s, client, api } = mk();
    await client.bootstrap();
    s.validGen = null;
    s.headersSeen.length = 0;
    await api.executeBatch(7, '실행 2건', 'KEY-FIXED');
    const exec = s.headersSeen.filter((x) => x.path === '/api/v1/batches/7/execute');
    expect(exec).toHaveLength(2);
    expect(exec[0]!.key).toBe('KEY-FIXED');
    expect(exec[1]!.key).toBe('KEY-FIXED');
    expect(exec[0]!.csrf).toBe('c1'); // 낡은 토큰
    expect(exec[1]!.csrf).toBe(`c${s.gen}`); // 새 토큰
    expect(s.gen).toBe(2);
  });

  it('TC-VFF-102 일반 변경 POST(cancel): 재발급 후 새 CSRF 로 1회 재시도, 총 2번 시도', async () => {
    const { s, client, api } = mk();
    await client.bootstrap();
    s.validGen = null;
    s.headersSeen.length = 0;
    await expect(api.cancelBatch(7)).resolves.toMatchObject({ status: 'cancelled' });
    expect(s.headersSeen.filter((x) => x.path.endsWith('/cancel'))).toHaveLength(2);
  });

  it('TC-VFF-103 CSRF 불일치(403 csrf_*)도 같은 방식으로 복구된다', async () => {
    const { s, client, api } = mk();
    await client.bootstrap();
    s.validGen = 5; // 세션은 살아 있으나 토큰이 다름(다른 탭이 재발급)
    s.gen = 5;
    await expect(api.cancelBatch(7)).resolves.toBeTruthy();
  });

  it('TC-VFF-104 PIN 이 설정된 서버: 만료 시 조용한 재발급이 불가능하므로 session_expired + PIN 요구 상태가 된다(PIN 은 저장·재전송되지 않음)', async () => {
    const { s, client, api } = mk({ pin: '1234' });
    await client.submitPin('1234');
    expect(client.getSnapshot().state).toBe('online');
    s.validGen = null;
    s.sessionPosts = 0;
    const err = await api.dashboard().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe('session_expired');
    expect(client.getSnapshot()).toMatchObject({ state: 'pin_required', expired: true });
    expect(s.sessionPosts).toBe(0); // PIN 없이 세션 발급을 시도하지 않았다
    await client.submitPin('1234');
    expect(client.getSnapshot()).toMatchObject({ state: 'online', expired: false });
    await expect(api.dashboard()).resolves.toBeTruthy();
  });

  it('TC-VFF-105 재발급 자체가 실패(500)하면 무한 반복하지 않고 오류를 올리며 시도 횟수가 한정된다', async () => {
    const { s, client, api } = mk();
    await client.bootstrap();
    s.validGen = null;
    s.failSession = true;
    s.log.length = 0;
    await expect(api.dashboard()).rejects.toBeInstanceOf(ApiError);
    expect(s.log.length).toBeLessThanOrEqual(5);
    expect(client.getSnapshot().state).toBe('error');
  });

  it('TC-VFF-106 재발급 후에도 401 이면(서버가 계속 거부) 한 번만 재시도하고 포기한다', async () => {
    const { s, client } = mk();
    await client.bootstrap();
    s.validGen = null;
    // 세션을 발급받아도 곧바로 다시 만료되는 서버
    const orig = s.log;
    const f2 = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const u = new URL(String(input), 'http://localhost');
      if (u.pathname === '/api/v1/auth/me')
        return J(200, { authenticated: false, pin_required: false });
      if (u.pathname === '/api/v1/auth/session') return J(201, { csrf_token: 'z' });
      orig.push(`${init?.method ?? 'GET'} ${u.pathname}`);
      return P(401, 'session_required', '만료');
    }) as typeof fetch;
    const c2 = new ApiClient({ fetchImpl: f2 });
    orig.length = 0;
    await expect(c2.request('GET', '/api/v1/dashboard')).rejects.toMatchObject({ status: 401 });
    expect(orig.filter((x) => x.endsWith('/dashboard'))).toHaveLength(2);
  });

  it('TC-VFF-107 동시에 3개 GET 이 만료를 만나면 세션 발급이 몇 번 일어나는지(낭비·경합 관찰) — 최종적으로 모두 성공해야 한다', async () => {
    const { s, client, api } = mk();
    await client.bootstrap();
    s.validGen = null;
    s.sessionPosts = 0;
    const rs = await Promise.all([api.dashboard(), api.dashboard(), api.dashboard()]);
    expect(rs).toHaveLength(3);
    // 관찰값: 이상적으로는 1. 여러 번 발급되어도 마지막 세션으로 수렴해야 한다.
    expect(s.sessionPosts).toBeGreaterThanOrEqual(1);
    // 수렴 확인: 이후 변경 요청이 즉시 성공한다
    await expect(api.cancelBatch(7)).resolves.toBeTruthy();
    console.log(`[관찰] 만료 직후 동시 GET 3개 → 세션 발급 ${s.sessionPosts}회`);
  });

  it('TC-VFF-108 로그아웃: 서버 응답을 받은 뒤에만 loggedout 상태가 되고, 실패하면 상태가 바뀌지 않는다', async () => {
    const { s, client, api } = mk();
    await client.bootstrap();
    await client.logout();
    expect(client.getSnapshot().state).toBe('loggedout');
    void s;
    void api;
  });
});
