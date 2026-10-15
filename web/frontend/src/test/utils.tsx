import { render } from '@testing-library/react';
import axe from 'axe-core';
import type { ReactElement } from 'react';
import { MemoryRouter, type InitialEntry } from 'react-router-dom';
import { ApiClient } from '../api/client';
import { Providers } from '../app/providers';

export interface Req {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
  headers: Record<string, string>;
}
export type Handler = (req: Req) => Response | undefined | Promise<Response | undefined>;

export const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });

export const problem = (status: number, code: string, title: string, detail = '', hint = '') =>
  new Response(JSON.stringify({ type: 'about:blank', title, status, detail, code, hint }), {
    status,
    headers: { 'Content-Type': 'application/problem+json' },
  });

/** 요청을 기록하고 handlers 를 위에서부터 시험하는 가짜 fetch. 매칭이 없으면 테스트가 실패하도록 404 를 낸다. */
export function fakeFetch(handlers: Handler[]) {
  const calls: Req[] = [];
  const fn = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost');
    const headers: Record<string, string> = {};
    new Headers(init?.headers).forEach((v, k) => (headers[k.toLowerCase()] = v));
    const raw = typeof init?.body === 'string' ? init.body : undefined;
    const req: Req = {
      method: init?.method ?? 'GET',
      path: url.pathname,
      query: url.searchParams,
      body: raw ? (JSON.parse(raw) as unknown) : undefined,
      headers,
    };
    calls.push(req);
    for (const h of handlers) {
      const r = await h(req);
      if (r) return r;
    }
    return problem(404, 'test_unhandled', `처리되지 않은 요청: ${req.method} ${req.path}`);
  }) as typeof fetch;
  return { fetch: fn, calls };
}

export const route =
  (
    method: string,
    path: string | RegExp,
    respond: (req: Req) => Response | Promise<Response>,
  ): Handler =>
  (req) =>
    req.method === method && (typeof path === 'string' ? req.path === path : path.test(req.path))
      ? respond(req)
      : undefined;

/** 세션이 이미 있는 상태(me → authenticated)로 만드는 기본 핸들러 */
export const authedHandlers: Handler[] = [
  route('GET', '/api/v1/auth/me', () =>
    json(200, { authenticated: true, pin_required: false, csrf_token: 'csrf-1' }),
  ),
];

export function makeClient(handlers: Handler[]) {
  const f = fakeFetch(handlers);
  const client = new ApiClient({ fetchImpl: f.fetch });
  return { client, calls: f.calls };
}

export async function connectedClient(handlers: Handler[]) {
  const c = makeClient([...authedHandlers, ...handlers]);
  await c.client.bootstrap();
  return c;
}

export function renderWithApp(ui: ReactElement, client: ApiClient, entry: InitialEntry = '/') {
  return render(
    <Providers client={client}>
      <MemoryRouter initialEntries={[entry]}>{ui}</MemoryRouter>
    </Providers>,
  );
}

/** axe-core 로 접근성 위반을 검사한다. jsdom 은 레이아웃·색을 계산하지 못하므로 색 대비와 페이지 단위 규칙은 끈다(색 대비는 토큰 설계와 실제 브라우저 확인으로 별도 점검). */
export async function axeViolations(container: Element): Promise<string[]> {
  const res = await axe.run(container, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
  });
  return res.violations.map(
    (v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(' ')).join(' | ')})`,
  );
}
