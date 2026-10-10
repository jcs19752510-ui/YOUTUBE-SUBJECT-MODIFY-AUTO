// 06단계 독립 검증(TC-VF) — API 클라이언트: CSRF·멱등키·401 재발급·오류 구분
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError, IdempotencyKeys, newKey } from '../src/api/client';
import { createEndpoints } from '../src/api/endpoints';
import {
  authedHandlers,
  connectedClient,
  fakeFetch,
  json,
  makeClient,
  problem,
  route,
  type Handler,
} from '../src/test/utils';

/** 무한 재시도 버그가 있어도 테스트가 멈추지 않도록, 호출 수가 한도를 넘으면 예외를 던진다 */
const runawayGuard = (limit = 40): Handler => {
  let n = 0;
  return () => {
    n += 1;
    if (n > limit) throw new Error('RUNAWAY: 요청이 한도를 넘었습니다(무한 재시도 의심)');
    return undefined;
  };
};

const ok = (body: unknown = {}) => json(200, body);

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('CSRF·Idempotency-Key 부착 규칙', () => {
  it('TC-VF-001 GET 엔드포인트 전부는 X-CSRF-Token 도 Idempotency-Key 도 보내지 않는다', async () => {
    const { client, calls } = await connectedClient([
      () => ok({ items: [], total: 0, page: 1, page_size: 1 }),
    ]);
    const api = createEndpoints(client);
    await api.dashboard();
    await api.videos({ page: 1 });
    await api.video('v1');
    await api.suggestions({ video_id: 'v1' });
    await api.batches({ page: 1 });
    await api.batch(3);
    await api.job('j1');
    await api.changes({ page: 1 });
    await api.reports();
    await api.audit({ page: 1 });
    await api.settings();
    await api.google();
    const gets = calls.filter((c) => c.path !== '/api/v1/auth/me');
    expect(gets).toHaveLength(12);
    for (const c of gets) {
      expect(c.method).toBe('GET');
      expect(c.headers['x-csrf-token']).toBeUndefined();
      expect(c.headers['idempotency-key']).toBeUndefined();
    }
  });

  it('TC-VF-002 상태 변경 엔드포인트(POST/PATCH) 전부가 세션에서 받은 CSRF 토큰을 보낸다', async () => {
    const { client, calls } = await connectedClient([() => ok([])]);
    const api = createEndpoints(client);
    await api.syncVideos();
    await api.suggestForVideo('v1', 2);
    await api.generateSuggestions(['v1', 'v2']);
    await api.editSuggestion(1, '새 제목');
    await api.approve(1, '홍길동');
    await api.reject(1);
    await api.createBatch([1, 2], undefined, 'k1');
    await api.executeBatch(7, '실행 2건', 'k2');
    await api.cancelBatch(7);
    await api.rollback(5, 'v1', '홍길동', 'k3');
    await api.patchSettings({ daily_apply_cap: 5 });
    const muts = calls.filter((c) => c.method !== 'GET');
    expect(muts).toHaveLength(11);
    for (const c of muts) expect(c.headers['x-csrf-token'], `${c.method} ${c.path}`).toBe('csrf-1');
  });

  it('TC-VF-003 DELETE(로그아웃)도 CSRF 토큰을 보낸다', async () => {
    const { client, calls } = await connectedClient([
      route('DELETE', '/api/v1/auth/session', () => json(204, null)),
    ]);
    await client.logout();
    const del = calls.find((c) => c.method === 'DELETE');
    expect(del?.headers['x-csrf-token']).toBe('csrf-1');
  });

  it('TC-VF-004 Idempotency-Key 는 위험 동작 3종(배치 생성·실행, 롤백)에만 붙고 넘겨준 값 그대로다', async () => {
    const { client, calls } = await connectedClient([() => ok({})]);
    const api = createEndpoints(client);
    await api.createBatch([1], '메모', 'KEY-A');
    await api.executeBatch(1, '실행 1건', 'KEY-B');
    await api.rollback(1, 'v1', '나', 'KEY-C');
    await api.approve(1, '나');
    await api.reject(1);
    await api.editSuggestion(1, 'x');
    await api.cancelBatch(1);
    await api.patchSettings({ daily_apply_cap: 3 });
    await api.syncVideos();
    await api.generateSuggestions(['v1']);
    await api.suggestForVideo('v1');
    const keyed = Object.fromEntries(
      calls.filter((c) => c.method !== 'GET').map((c) => [c.path, c.headers['idempotency-key']]),
    );
    expect(keyed['/api/v1/batches']).toBe('KEY-A');
    expect(keyed['/api/v1/batches/1/execute']).toBe('KEY-B');
    expect(keyed['/api/v1/changes/1/rollback']).toBe('KEY-C');
    const others = Object.entries(keyed).filter(
      ([p]) =>
        !['/api/v1/batches', '/api/v1/batches/1/execute', '/api/v1/changes/1/rollback'].includes(p),
    );
    expect(others.length).toBeGreaterThanOrEqual(8);
    for (const [p, k] of others) expect(k, p).toBeUndefined();
  });

  it('TC-VF-005 키를 넘기지 않은 위험 호출은 호출마다 서로 다른 키(UUID 형식)를 만든다', async () => {
    const { client, calls } = await connectedClient([() => ok({})]);
    await client.request('POST', '/api/v1/batches', { body: {}, risky: true });
    await client.request('POST', '/api/v1/batches', { body: {}, risky: true });
    const keys = calls
      .filter((c) => c.path === '/api/v1/batches')
      .map((c) => c.headers['idempotency-key']);
    expect(keys[0]).toMatch(/^[0-9a-f-]{32,36}$/);
    expect(keys[0]).not.toBe(keys[1]);
  });

  it('TC-VF-006 Content-Type 은 본문이 있을 때만, Accept 는 항상, 쿠키는 same-origin 으로 보낸다', async () => {
    const seen: RequestInit[] = [];
    const fetchImpl = (async (_u: RequestInfo | URL, init?: RequestInit) => {
      seen.push(init ?? {});
      return json(200, { authenticated: true, pin_required: false, csrf_token: 'c' });
    }) as typeof fetch;
    const client = new ApiClient({ fetchImpl });
    await client.bootstrap();
    await client.request('GET', '/api/v1/dashboard');
    await client.request('POST', '/api/v1/videos/sync', { body: {} });
    const h = (i: number) => new Headers(seen[i]?.headers);
    expect(h(1).get('Content-Type')).toBeNull();
    expect(h(2).get('Content-Type')).toBe('application/json');
    for (let i = 0; i < seen.length; i++) {
      expect(h(i).get('Accept')).toBe('application/json');
      expect(seen[i]?.credentials).toBe('same-origin');
    }
  });

  it('TC-VF-007 엔드포인트 계약: 메서드·경로·본문이 설계서 §3 과 같다', async () => {
    const { client, calls } = await connectedClient([() => ok({})]);
    const api = createEndpoints(client);
    await api.suggestForVideo('v1', 3);
    await api.generateSuggestions(['a', 'b'], 2);
    await api.editSuggestion(9, '제목');
    await api.approve(9, '나');
    await api.reject(9);
    await api.createBatch([3, 1], '메모', 'k');
    await api.executeBatch(4, '실행 2건', 'k');
    await api.cancelBatch(4);
    await api.rollback(8, 'vid', '나', 'k');
    const sig = calls
      .filter((c) => c.method !== 'GET')
      .map((c) => `${c.method} ${c.path} ${JSON.stringify(c.body)}`);
    expect(sig).toEqual([
      'POST /api/v1/videos/v1/suggestions {"count":3}',
      'POST /api/v1/suggestions/generate {"video_ids":["a","b"],"count":2}',
      'PATCH /api/v1/suggestions/9 {"title":"제목"}',
      'POST /api/v1/suggestions/9/approve {"approver":"나"}',
      'POST /api/v1/suggestions/9/reject {}',
      'POST /api/v1/batches {"suggestion_ids":[3,1],"note":"메모"}',
      'POST /api/v1/batches/4/execute {"confirm_text":"실행 2건"}',
      'POST /api/v1/batches/4/cancel {}',
      'POST /api/v1/changes/8/rollback {"typed_video_id":"vid","approver":"나"}',
    ]);
  });

  it('TC-VF-008 쿼리 문자열: 빈 값·undefined·null 은 빼고 0·false 는 유지하며 특수문자를 인코딩한다', async () => {
    const { client, calls } = await connectedClient([() => ok({})]);
    await client.request('GET', '/api/v1/videos', {
      query: { q: 'a&b=c 가', status: '', excluded: false, page: 0, x: undefined, y: null },
    });
    const c = calls.at(-1)!;
    expect(c.query.get('q')).toBe('a&b=c 가');
    expect(c.query.has('status')).toBe(false);
    expect(c.query.get('excluded')).toBe('false');
    expect(c.query.get('page')).toBe('0');
    expect(c.query.has('x')).toBe(false);
    expect(c.query.has('y')).toBe(false);
    expect([...c.query.keys()].sort()).toEqual(['excluded', 'page', 'q']);
  });

  it('TC-VF-009 경로의 영상 ID 는 인코딩되어 다른 경로로 새지 않는다(? # / 포함)', async () => {
    const { client, calls } = await connectedClient([() => ok({})]);
    const api = createEndpoints(client);
    await api.video('a/b?c#d');
    const c = calls.at(-1)!;
    expect(c.path).toBe('/api/v1/videos/a%2Fb%3Fc%23d');
    expect(c.query.toString()).toBe('');
  });
});

describe('Idempotency-Key 재사용 규칙', () => {
  it('TC-VF-010 같은 지문은 같은 키, 지문이 바뀌면 새 키, clear 뒤에는 같은 지문이라도 새 키', () => {
    const k = new IdempotencyKeys();
    const a = k.get('x');
    expect(k.get('x')).toBe(a);
    const b = k.get('y');
    expect(b).not.toBe(a);
    expect(k.get('y')).toBe(b);
    expect(k.get('x')).not.toBe(a); // 되돌아가도 옛 키를 재사용하지 않는다(다른 요청이 섞이지 않게)
    const c = k.get('x');
    k.clear();
    expect(k.get('x')).not.toBe(c);
  });

  it('TC-VF-011 서로 다른 IdempotencyKeys 인스턴스는 키를 공유하지 않는다', () => {
    expect(new IdempotencyKeys().get('same')).not.toBe(new IdempotencyKeys().get('same'));
  });

  it('TC-VF-012 newKey 는 1000번 호출해도 중복이 없다', () => {
    const s = new Set(Array.from({ length: 1000 }, () => newKey()));
    expect(s.size).toBe(1000);
  });

  it('TC-VF-013 crypto.randomUUID 가 없는 환경에서도 32자리 16진수 키를 만든다', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (b: Uint8Array) => globalThis.crypto && b.fill(171),
    });
    const k = newKey();
    expect(k).toMatch(/^[0-9a-f]{32}$/);
  });
});

describe('401 재발급 1회와 재시도', () => {
  it('TC-VF-014 재시도에서는 새 CSRF 토큰을 쓰되 Idempotency-Key 는 처음과 같다', async () => {
    let me = 0;
    let first = true;
    const { client, calls } = makeClient([
      route('GET', '/api/v1/auth/me', () => {
        me += 1;
        return json(200, { authenticated: true, pin_required: false, csrf_token: `tok-${me}` });
      }),
      route('POST', '/api/v1/batches/1/execute', () => {
        if (first) {
          first = false;
          return problem(401, 'session_required', '세션 만료');
        }
        return ok({ batch: {}, job: {} });
      }),
    ]);
    await client.bootstrap();
    await client.request('POST', '/api/v1/batches/1/execute', {
      body: {},
      risky: true,
      idempotencyKey: 'KEEP',
    });
    const ex = calls.filter((c) => c.path === '/api/v1/batches/1/execute');
    expect(ex).toHaveLength(2);
    expect(ex[0]?.headers['idempotency-key']).toBe('KEEP');
    expect(ex[1]?.headers['idempotency-key']).toBe('KEEP');
    expect(ex[0]?.headers['x-csrf-token']).toBe('tok-1');
    expect(ex[1]?.headers['x-csrf-token']).toBe('tok-2');
  });

  it('TC-VF-015 키를 넘기지 않은 위험 호출도 401 재시도에서 처음 만든 키를 그대로 쓴다', async () => {
    let first = true;
    const { client, calls } = await connectedClient([
      route('POST', '/api/v1/changes/2/rollback', () => {
        if (first) {
          first = false;
          return problem(401, 'session_required', '세션 만료');
        }
        return ok({});
      }),
    ]);
    await client.request('POST', '/api/v1/changes/2/rollback', { body: {}, risky: true });
    const rb = calls.filter((c) => c.path === '/api/v1/changes/2/rollback');
    expect(rb).toHaveLength(2);
    expect(rb[0]?.headers['idempotency-key']).toBeTruthy();
    expect(rb[1]?.headers['idempotency-key']).toBe(rb[0]?.headers['idempotency-key']);
  });

  it('TC-VF-016 계속 401 이면 원 요청은 정확히 2번(처음+재시도 1회)만 가고 오류를 던진다(무한 루프 없음)', async () => {
    const { client, calls } = makeClient([
      runawayGuard(),
      ...authedHandlers,
      route('POST', '/api/v1/batches/1/cancel', () =>
        problem(401, 'session_required', '세션 만료'),
      ),
    ]);
    await client.bootstrap();
    await expect(
      client.request('POST', '/api/v1/batches/1/cancel', { body: {} }),
    ).rejects.toMatchObject({
      status: 401,
      code: 'session_required',
    });
    expect(calls.filter((c) => c.path === '/api/v1/batches/1/cancel')).toHaveLength(2);
    expect(calls.length).toBeLessThan(10);
  });

  it('TC-VF-017 GET 이 계속 401 이어도 2번만 보내고 멈춘다', async () => {
    const { client, calls } = makeClient([
      runawayGuard(),
      ...authedHandlers,
      route('GET', '/api/v1/dashboard', () => problem(401, 'session_required', '세션 만료')),
    ]);
    await client.bootstrap();
    await expect(client.request('GET', '/api/v1/dashboard')).rejects.toBeInstanceOf(ApiError);
    expect(calls.filter((c) => c.path === '/api/v1/dashboard')).toHaveLength(2);
  });

  it('TC-VF-018 CSRF 거절(403 csrf_invalid)도 재발급 후 1회만 재시도한다', async () => {
    let n = 0;
    const { client, calls } = makeClient([
      runawayGuard(),
      ...authedHandlers,
      route('POST', '/api/v1/suggestions/1/reject', () => {
        n += 1;
        return n === 1 ? problem(403, 'csrf_invalid', 'CSRF') : ok({});
      }),
    ]);
    await client.bootstrap();
    await client.request('POST', '/api/v1/suggestions/1/reject', { body: {} });
    expect(n).toBe(2);
    expect(calls.filter((c) => c.path === '/api/v1/auth/me')).toHaveLength(2);
  });

  it('TC-VF-019 CSRF 와 무관한 403(origin_not_allowed 등)은 재발급·재시도를 하지 않는다', async () => {
    const { client, calls } = await connectedClient([
      route('POST', '/api/v1/suggestions/1/reject', () =>
        problem(403, 'origin_not_allowed', 'Origin'),
      ),
    ]);
    await expect(
      client.request('POST', '/api/v1/suggestions/1/reject', { body: {} }),
    ).rejects.toMatchObject({
      code: 'origin_not_allowed',
    });
    expect(calls.filter((c) => c.path === '/api/v1/suggestions/1/reject')).toHaveLength(1);
    expect(calls.filter((c) => c.path === '/api/v1/auth/me')).toHaveLength(1);
  });

  it('TC-VF-020 틀린 PIN(401 pin_invalid)은 세션 재발급을 시도하지 않는다', async () => {
    const { client, calls } = await connectedClient([
      route('PATCH', '/api/v1/settings', () => problem(401, 'pin_invalid', 'PIN 불일치')),
    ]);
    await expect(client.request('PATCH', '/api/v1/settings', { body: {} })).rejects.toMatchObject({
      code: 'pin_invalid',
    });
    expect(calls.filter((c) => c.path === '/api/v1/auth/me')).toHaveLength(1);
    expect(calls.filter((c) => c.path === '/api/v1/auth/session')).toHaveLength(0);
    expect(client.getSnapshot().state).toBe('online');
  });

  it('TC-VF-021 재발급 중 PIN 이 필요하면 session_expired 로 바꾸고 expired 표시를 켠다(재시도는 하지 않음)', async () => {
    let authed = true;
    const { client, calls } = makeClient([
      runawayGuard(),
      route('GET', '/api/v1/auth/me', () =>
        authed
          ? json(200, { authenticated: true, pin_required: true, csrf_token: 'c1' })
          : json(200, { authenticated: false, pin_required: true, csrf_token: null }),
      ),
      route('POST', '/api/v1/batches/1/cancel', () => {
        authed = false;
        return problem(401, 'session_required', '만료');
      }),
    ]);
    await client.bootstrap();
    await expect(
      client.request('POST', '/api/v1/batches/1/cancel', { body: {} }),
    ).rejects.toMatchObject({
      code: 'session_expired',
    });
    expect(client.getSnapshot()).toMatchObject({ state: 'pin_required', expired: true });
    expect(calls.filter((c) => c.path === '/api/v1/batches/1/cancel')).toHaveLength(1);
  });

  it('TC-VF-022 PIN 을 다시 넣으면 PIN 은 본문으로만 전송되고(URL·헤더 제외) 상태가 online 으로 돌아온다', async () => {
    let authed = false;
    const { client, calls } = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, {
          authenticated: authed,
          pin_required: !authed,
          csrf_token: authed ? 'c' : null,
        }),
      ),
      route('POST', '/api/v1/auth/session', () => {
        authed = true;
        return json(200, { csrf_token: 'c' });
      }),
    ]);
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('pin_required');
    await client.submitPin('987654');
    expect(client.getSnapshot()).toMatchObject({ state: 'online', expired: false });
    for (const c of calls) {
      expect(c.path + c.query.toString()).not.toContain('987654');
      expect(JSON.stringify(c.headers)).not.toContain('987654');
    }
    expect(calls.find((c) => c.path === '/api/v1/auth/session')?.body).toEqual({ pin: '987654' });
  });
});

describe('오류 형태 구분', () => {
  it('TC-VF-023 problem+json 의 필드가 문자열이 아니어도(숫자·객체·배열) 안전한 기본값으로 바꾼다', async () => {
    const { client } = await connectedClient([
      route(
        'GET',
        '/api/v1/dashboard',
        () =>
          new Response(JSON.stringify({ title: 42, detail: { a: 1 }, code: 7, hint: ['x'] }), {
            status: 500,
            headers: { 'Content-Type': 'application/problem+json' },
          }),
      ),
    ]);
    const e = await client.request('GET', '/api/v1/dashboard').catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
    const a = e as ApiError;
    expect(a.status).toBe(500);
    expect(a.code).toBe('http_500');
    expect(a.title).toBe('요청을 처리하지 못했습니다');
    expect(a.detail).toBe('');
    expect(typeof a.hint).toBe('string');
  });

  it.each([
    ['null', 'null'],
    ['배열', '[1,2]'],
    ['문자열', '"boom"'],
    ['빈 본문', ''],
  ])('TC-VF-024 오류 본문이 %s 이어도 ApiError 로 바뀐다', async (_n, body) => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/dashboard', () => new Response(body, { status: 500 })),
    ]);
    const e = (await client
      .request('GET', '/api/v1/dashboard')
      .catch((x: unknown) => x)) as ApiError;
    expect(e).toBeInstanceOf(ApiError);
    expect(e.code).toBe('http_500');
    expect(e.title).toBe('요청을 처리하지 못했습니다');
  });

  it('TC-VF-025 프록시가 돌려준 HTML 오류 페이지(502)는 코드 http_502 로만 알리고 HTML 을 화면용 문구에 싣지 않는다', async () => {
    const html = '<html><body><h1>502 Bad Gateway</h1><script>alert(1)</script></body></html>';
    const { client } = await connectedClient([
      route(
        'GET',
        '/api/v1/dashboard',
        () => new Response(html, { status: 502, headers: { 'Content-Type': 'text/html' } }),
      ),
    ]);
    const e = (await client
      .request('GET', '/api/v1/dashboard')
      .catch((x: unknown) => x)) as ApiError;
    expect(e.code).toBe('http_502');
    expect(e.status).toBe(502);
    expect(`${e.title}${e.detail}${e.hint}`).not.toMatch(/<|script|Bad Gateway/);
  });

  it('TC-VF-026 200 인데 JSON 이 깨진 응답은 bad_response 로 구분한다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/dashboard', () => new Response('{"a":', { status: 200 })),
    ]);
    await expect(client.request('GET', '/api/v1/dashboard')).rejects.toMatchObject({
      code: 'bad_response',
      status: 200,
    });
  });

  it('TC-VF-027 200 빈 본문과 204 는 undefined 로 처리하고 오류로 보지 않는다', async () => {
    const { client } = await connectedClient([
      route('POST', '/api/v1/a', () => new Response('', { status: 200 })),
      route('POST', '/api/v1/b', () => json(204, null)),
    ]);
    await expect(client.request('POST', '/api/v1/a', { body: {} })).resolves.toBeUndefined();
    await expect(client.request('POST', '/api/v1/b', { body: {} })).resolves.toBeUndefined();
  });

  it('TC-VF-028 429 의 Retry-After 는 안내에 넣고, 다른 상태 코드의 Retry-After 는 무시한다', async () => {
    const { client } = await connectedClient([
      route(
        'GET',
        '/api/v1/a',
        () =>
          new Response(JSON.stringify({ code: 'rate_limited', title: '많음', hint: '잠시' }), {
            status: 429,
            headers: { 'Retry-After': '17' },
          }),
      ),
      route(
        'GET',
        '/api/v1/b',
        () =>
          new Response(JSON.stringify({ code: 'x', title: 't' }), {
            status: 503,
            headers: { 'Retry-After': '99' },
          }),
      ),
    ]);
    const a = (await client.request('GET', '/api/v1/a').catch((x: unknown) => x)) as ApiError;
    const b = (await client.request('GET', '/api/v1/b').catch((x: unknown) => x)) as ApiError;
    expect(a.hint).toContain('17초');
    expect(a.isLimit).toBe(true);
    expect(b.hint).not.toContain('99');
  });

  it('TC-VF-029 네트워크 오류(fetch 거부)는 status 0 · network_error 로 구분하고 연결 상태를 offline 으로 바꾼다', async () => {
    let down = true;
    const { client } = makeClient([
      () => {
        if (down) throw new TypeError('Failed to fetch');
        return undefined;
      },
      ...authedHandlers,
      route('GET', '/api/v1/dashboard', () => ok({})),
    ]);
    const e = (await client
      .request('GET', '/api/v1/dashboard')
      .catch((x: unknown) => x)) as ApiError;
    expect(e).toMatchObject({ status: 0, code: 'network_error' });
    expect(e.isNetwork).toBe(true);
    expect(client.getSnapshot().state).toBe('offline');
    down = false;
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('online');
    expect(client.getSnapshot().error).toBeNull();
  });

  it('TC-VF-030 서버가 오류 응답(500)을 주는 것은 네트워크 끊김이 아니다: 상태는 online 유지', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/dashboard', () => problem(500, 'boom', '서버 오류')),
    ]);
    await client.request('GET', '/api/v1/dashboard').catch(() => undefined);
    expect(client.getSnapshot().state).toBe('online');
  });

  it('TC-VF-031 사용자 취소(AbortError)는 network_error 로 둔갑하지 않고 연결 상태도 바꾸지 않는다', async () => {
    const f = fakeFetch([
      ...authedHandlers,
      () => {
        throw new DOMException('aborted', 'AbortError');
      },
    ]);
    const client = new ApiClient({ fetchImpl: f.fetch });
    // me 는 정상, 이후 요청은 모두 Abort
    const ctl = new AbortController();
    ctl.abort();
    await client.bootstrap();
    const before = client.getSnapshot();
    const e = await client
      .request('GET', '/api/v1/dashboard', { signal: ctl.signal })
      .catch((x: unknown) => x);
    expect((e as { name?: string }).name).toBe('AbortError');
    expect(client.getSnapshot()).toBe(before);
  });

  // 결함 DEF-6-001(Low): 응답이 오지 않는 서버에 대한 시간 제한이 없다. 고쳐지면 .fails 를 제거할 것.
  it('TC-VF-032 응답이 영영 오지 않으면 일정 시간 뒤 연결 끊김 오류로 끝난다(시간 제한) [DEF-6-001]', async () => {
    vi.useFakeTimers();
    const client = new ApiClient({
      fetchImpl: (() => new Promise<Response>(() => undefined)) as typeof fetch,
    });
    let settled = false;
    const p = client.request('GET', '/api/v1/dashboard').then(
      () => (settled = true),
      () => (settled = true),
    );
    await vi.advanceTimersByTimeAsync(10 * 60 * 1000); // 10분
    expect(settled).toBe(true);
    void p;
  });

  it('TC-VF-033 오류 분류(isLimit): 서버가 실제로 내는 코드 중 한도 계열만 true 다', () => {
    const mk = (status: number, code: string) => new ApiError({ status, code, title: 't' });
    const limit = [
      mk(429, 'rate_limited'),
      mk(429, 'quota_exhausted'),
      mk(409, 'limit_reached'),
      mk(429, 'pin_locked'),
    ];
    for (const e of limit) expect(e.isLimit, e.code).toBe(true);
    const notLimit = [
      'ai_no_candidates',
      'ai_unavailable',
      'already_in_batch',
      'batch_empty',
      'batch_not_found',
      'confirm_text_mismatch',
      'csrf_invalid',
      'duplicate_suggestion',
      'gateway_error',
      'idempotency_key_required',
      'pin_invalid',
      'precheck_stale',
      'schedule_overflow',
      'session_required',
      'suggestion_blocked',
      'title_too_long',
      'typed_video_id_mismatch',
      'validation_error',
      'video_excluded',
    ];
    for (const c of notLimit) expect(mk(400, c).isLimit, c).toBe(false);
  });

  // 결함 DEF-6-002(Low, 잠복): 한도 판별 정규식 /rate/ 가 generate·operate 같은 단어에도 걸린다.
  it('TC-VF-034 "generate_failed" 같은 한도와 무관한 코드를 한도 초과로 분류하지 않는다 [DEF-6-002]', () => {
    for (const code of [
      'generate_failed',
      'migrate_error',
      'operate_failed',
      'accurate_mismatch',
    ]) {
      expect(new ApiError({ status: 500, code, title: 't' }).isLimit, code).toBe(false);
    }
  });
});

describe('세션 수명', () => {
  it('TC-VF-035 로그아웃이 네트워크 때문에 실패하면 loggedout 으로 바꾸지 않고 CSRF 도 유지한다', async () => {
    let down = false;
    const { client, calls } = makeClient([
      () => {
        if (down) throw new TypeError('Failed to fetch');
        return undefined;
      },
      ...authedHandlers,
      route('POST', '/api/v1/videos/sync', () => ok({})),
    ]);
    await client.bootstrap();
    down = true;
    await expect(client.logout()).rejects.toMatchObject({ code: 'network_error' });
    expect(client.getSnapshot().state).toBe('offline');
    down = false;
    await client.request('POST', '/api/v1/videos/sync', { body: {} });
    expect(calls.at(-1)?.headers['x-csrf-token']).toBe('csrf-1');
  });

  it('TC-VF-036 로그아웃 뒤 상태 변경을 시도하면 먼저 세션을 다시 확인한다(옛 토큰 재사용 금지)', async () => {
    let me = 0;
    const { client, calls } = makeClient([
      route('GET', '/api/v1/auth/me', () => {
        me += 1;
        return json(200, { authenticated: true, pin_required: false, csrf_token: `t${me}` });
      }),
      route('DELETE', '/api/v1/auth/session', () => json(204, null)),
      route('POST', '/api/v1/videos/sync', () => ok({})),
    ]);
    await client.bootstrap();
    await client.logout();
    await client.request('POST', '/api/v1/videos/sync', { body: {} });
    expect(calls.at(-1)?.headers['x-csrf-token']).toBe('t2');
  });

  it('TC-VF-037 CSRF 토큰·PIN 은 localStorage/sessionStorage/document.cookie 에 남지 않는다', async () => {
    document.cookie = '';
    const { client } = await connectedClient([]);
    await client.request('GET', '/api/v1/dashboard').catch(() => undefined);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(document.cookie).not.toContain('csrf-1');
  });

  it('TC-VF-038 오류·재시도 경로에서 console 로 토큰·PIN 을 출력하지 않는다', async () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) =>
      vi.spyOn(console, m).mockImplementation(() => undefined),
    );
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, { authenticated: false, pin_required: true, csrf_token: null }),
      ),
      route('POST', '/api/v1/auth/session', () => problem(401, 'pin_invalid', 'PIN 불일치')),
    ]);
    await client.bootstrap();
    await client.submitPin('424242').catch(() => undefined);
    const out = spies
      .flatMap((s) => s.mock.calls)
      .flat()
      .map(String)
      .join(' ');
    expect(out).not.toContain('424242');
    expect(out).not.toContain('csrf-1');
  });

  it('TC-VF-039 PIN 이 필요한 서버에서 틀린 PIN 은 pin_required 상태를 유지하고 error 상태로 바뀌지 않는다', async () => {
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, { authenticated: false, pin_required: true, csrf_token: null }),
      ),
      route('POST', '/api/v1/auth/session', () => problem(401, 'pin_invalid', 'PIN 불일치')),
    ]);
    await client.bootstrap();
    await expect(client.submitPin('0000')).rejects.toMatchObject({ code: 'pin_invalid' });
    expect(client.getSnapshot().state).toBe('pin_required');
  });

  it('TC-VF-040 시작 직후 서버가 꺼져 있으면 offline, 켜진 뒤 bootstrap 하면 online 으로 복구된다', async () => {
    let down = true;
    const { client } = makeClient([
      () => {
        if (down) throw new TypeError('x');
        return undefined;
      },
      ...authedHandlers,
    ]);
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('offline');
    down = false;
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('online');
  });

  it('TC-VF-041 동시에 시작된 bootstrap 호출은 auth/me 를 한 번만 부른다', async () => {
    const { client, calls } = makeClient([...authedHandlers]);
    await Promise.all([client.bootstrap(), client.bootstrap(), client.bootstrap()]);
    expect(calls.filter((c) => c.path === '/api/v1/auth/me')).toHaveLength(1);
  });
});
