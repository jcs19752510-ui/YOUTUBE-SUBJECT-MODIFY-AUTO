import { describe, expect, it } from 'vitest';
import { ApiError, IdempotencyKeys } from './client';
import { createEndpoints } from './endpoints';
import { json, makeClient, problem, route, type Handler } from '../test/utils';

const me = (authenticated: boolean, pin_required = false, csrf: string | null = null): Handler =>
  route('GET', '/api/v1/auth/me', () =>
    json(200, { authenticated, pin_required, csrf_token: csrf }),
  );
const session = (token = 'csrf-new'): Handler =>
  route('POST', '/api/v1/auth/session', () =>
    json(200, { csrf_token: token }, { 'Set-Cookie': 'ytw_session=x' }),
  );

describe('세션 시작', () => {
  it('TC-WF-001 미인증이면 세션을 발급받고 CSRF 토큰을 메모리에만 둔다', async () => {
    const { client, calls } = makeClient([
      me(false),
      session('tok-1'),
      route('POST', '/api/v1/videos/sync', () => json(202, { id: 'j' })),
    ]);
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('online');
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      'GET /api/v1/auth/me',
      'POST /api/v1/auth/session',
    ]);
    await createEndpoints(client).syncVideos();
    expect(calls.at(-1)?.headers['x-csrf-token']).toBe('tok-1');
    expect(JSON.stringify({ ...localStorage })).not.toContain('tok-1');
    expect(JSON.stringify({ ...sessionStorage })).not.toContain('tok-1');
  });

  it('TC-WF-002 이미 인증된 세션이면 새로 발급하지 않는다', async () => {
    const { client, calls } = makeClient([me(true, false, 'tok-2'), session()]);
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('online');
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('TC-WF-003 PIN 이 필요하면 입력 상태로 멈추고, 입력한 PIN 으로 세션을 발급한다', async () => {
    const { client, calls } = makeClient([me(false, true), session('tok-pin')]);
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('pin_required');
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    await client.submitPin('1234');
    expect(client.getSnapshot().state).toBe('online');
    expect(calls.at(-1)?.body).toEqual({ pin: '1234' });
  });

  it('TC-WF-004 틀린 PIN 은 오류를 던지고 PIN 입력 상태를 유지한다', async () => {
    const { client } = makeClient([
      me(false, true),
      route('POST', '/api/v1/auth/session', () =>
        problem(401, 'pin_invalid', 'PIN 이 맞지 않습니다'),
      ),
    ]);
    await client.bootstrap();
    await expect(client.submitPin('0000')).rejects.toMatchObject({ code: 'pin_invalid' });
    expect(client.getSnapshot().state).toBe('pin_required');
  });
});

describe('요청 헤더', () => {
  const base = [me(true, false, 'csrf-x')];
  it('TC-WF-005 상태 변경 요청에만 X-CSRF-Token 을 붙인다', async () => {
    const { client, calls } = makeClient([
      ...base,
      route('GET', '/api/v1/dashboard', () => json(200, {})),
      route('POST', /suggestions\/1\/reject/, () => json(200, {})),
    ]);
    await client.bootstrap();
    const api = createEndpoints(client);
    await api.dashboard();
    await api.reject(1);
    expect(
      calls.find((c) => c.path === '/api/v1/dashboard')?.headers['x-csrf-token'],
    ).toBeUndefined();
    expect(calls.find((c) => c.method === 'POST')?.headers['x-csrf-token']).toBe('csrf-x');
  });

  it('TC-WF-006 위험 동작(배치 생성·실행, 롤백)에는 Idempotency-Key 를 붙이고 일반 변경에는 붙이지 않는다', async () => {
    const { client, calls } = makeClient([...base, route('POST', /.*/, () => json(200, {}))]);
    await client.bootstrap();
    const api = createEndpoints(client);
    await api.createBatch([1], undefined, 'k-1');
    await api.executeBatch(3, '실행 1건', 'k-2');
    await api.rollback(4, 'abc', '홍', 'k-3');
    await api.approve(1, '홍');
    const keys = calls.filter((c) => c.method === 'POST').map((c) => c.headers['idempotency-key']);
    expect(keys).toEqual(['k-1', 'k-2', 'k-3', undefined]);
  });

  it('TC-WF-007 같은 요청을 다시 보내면 같은 멱등키를, 요청이 바뀌면 새 키를 쓴다', () => {
    const k = new IdempotencyKeys();
    const a = k.get('1,2');
    expect(k.get('1,2')).toBe(a);
    expect(k.get('1,2,3')).not.toBe(a);
    const b = k.get('1,2,3');
    k.clear();
    expect(k.get('1,2,3')).not.toBe(b);
  });

  it('TC-WF-008 키를 넘기지 않은 위험 요청은 자동으로 키를 만들어 붙인다', async () => {
    const { client, calls } = makeClient([...base, route('POST', /.*/, () => json(200, {}))]);
    await client.bootstrap();
    await client.request('POST', '/api/v1/batches', { body: {}, risky: true });
    expect(calls.at(-1)?.headers['idempotency-key']).toMatch(/.{16,}/);
  });
});

describe('오류 변환', () => {
  it('TC-WF-009 problem+json 을 ApiError(code,title,detail,hint)로 바꾼다', async () => {
    const { client } = makeClient([
      me(true, false, 'c'),
      route('GET', '/api/v1/dashboard', () =>
        problem(409, 'suggestion_blocked', '차단됨', '사유', '수정하세요'),
      ),
    ]);
    await client.bootstrap();
    const err = await createEndpoints(client)
      .dashboard()
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 409,
      code: 'suggestion_blocked',
      title: '차단됨',
      detail: '사유',
      hint: '수정하세요',
    });
  });

  it('TC-WF-010 JSON 이 아닌 오류 응답도 안전한 기본 문구로 바꾼다', async () => {
    const { client } = makeClient([
      me(true, false, 'c'),
      route('GET', '/api/v1/dashboard', () => new Response('<html>502</html>', { status: 502 })),
    ]);
    await client.bootstrap();
    const err = (await createEndpoints(client)
      .dashboard()
      .catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe('http_502');
    expect(err.title).not.toContain('html');
  });

  it('TC-WF-011 429 와 한도 코드는 한도 초과로 분류한다', async () => {
    const { client } = makeClient([
      me(true, false, 'c'),
      route(
        'GET',
        '/api/v1/dashboard',
        () =>
          new Response(JSON.stringify({ title: '많음', code: 'rate_limited' }), {
            status: 429,
            headers: { 'Retry-After': '30', 'Content-Type': 'application/problem+json' },
          }),
      ),
    ]);
    await client.bootstrap();
    const err = (await createEndpoints(client)
      .dashboard()
      .catch((e: unknown) => e)) as ApiError;
    expect(err.isLimit).toBe(true);
    expect(err.hint).toContain('30');
  });
});

describe('세션 만료와 연결 끊김', () => {
  it('TC-WF-012 401 이면 조용히 재발급하고 같은 멱등키로 한 번 다시 보낸다', async () => {
    let first = true;
    const { client, calls } = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, { authenticated: first, pin_required: false, csrf_token: first ? 'old' : null }),
      ),
      session('fresh'),
      route('POST', /\/execute$/, (req) => {
        if (first) {
          first = false;
          return problem(401, 'unauthenticated', '로그인 필요');
        }
        return json(202, { ok: true, token: req.headers['x-csrf-token'] });
      }),
    ]);
    await client.bootstrap();
    await createEndpoints(client).executeBatch(1, '실행 1건', 'same-key');
    const posts = calls.filter((c) => c.path.endsWith('/execute'));
    expect(posts).toHaveLength(2);
    expect(posts.map((p) => p.headers['idempotency-key'])).toEqual(['same-key', 'same-key']);
    expect(posts[1]?.headers['x-csrf-token']).toBe('fresh');
    expect(client.getSnapshot().state).toBe('online');
  });

  it('TC-WF-013 재발급에 PIN 이 필요하면 session_expired 오류와 함께 PIN 입력 상태(만료)로 바뀐다', async () => {
    let authed = true;
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(
          200,
          authed
            ? { authenticated: true, pin_required: false, csrf_token: 'c' }
            : { authenticated: false, pin_required: true, csrf_token: null },
        ),
      ),
      route('GET', '/api/v1/dashboard', () => {
        authed = false;
        return problem(401, 'unauthenticated', '로그인 필요');
      }),
    ]);
    await client.bootstrap();
    const err = (await createEndpoints(client)
      .dashboard()
      .catch((e: unknown) => e)) as ApiError;
    expect(err.isSessionExpired).toBe(true);
    expect(client.getSnapshot()).toMatchObject({ state: 'pin_required', expired: true });
  });

  it('TC-WF-014 네트워크 오류는 "서버 연결 끊김"으로 구분하고, 다시 성공하면 복구된다', async () => {
    let down = false;
    const { client } = makeClient([
      me(true, false, 'c'),
      () => {
        if (down) throw new TypeError('Failed to fetch');
        return undefined;
      },
      route('GET', '/api/v1/dashboard', () => json(200, {})),
    ]);
    await client.bootstrap();
    down = true;
    const err = (await createEndpoints(client)
      .dashboard()
      .catch((e: unknown) => e)) as ApiError;
    expect(err.isNetwork).toBe(true);
    expect(client.getSnapshot().state).toBe('offline');
    down = false;
    await createEndpoints(client).dashboard();
    expect(client.getSnapshot().state).toBe('online');
  });

  it('TC-WF-015 로그아웃하면 상태가 loggedout 이 되고 CSRF 토큰을 버린다', async () => {
    const { client, calls } = makeClient([
      me(true, false, 'c'),
      route('DELETE', '/api/v1/auth/session', () => json(204, null)),
      session('again'),
    ]);
    await client.bootstrap();
    await client.logout();
    expect(client.getSnapshot().state).toBe('loggedout');
    await createEndpoints(client)
      .reject(1)
      .catch(() => undefined);
    // 토큰이 없으므로 먼저 세션 확인을 다시 한다
    expect(calls.filter((c) => c.path === '/api/v1/auth/me').length).toBeGreaterThan(1);
  });
});
