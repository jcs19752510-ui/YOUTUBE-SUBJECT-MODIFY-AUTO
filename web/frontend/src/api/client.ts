import type { AuthMe, ProblemJson, SessionResponse } from './types';

export type ConnectionState =
  | 'starting' // 첫 확인 중
  | 'online'
  | 'offline' // 서버에 닿지 않음
  | 'pin_required' // PIN 입력 필요
  | 'loggedout' // 사용자가 로그아웃함
  | 'error'; // 세션 시작 실패(PIN 외)

export interface ConnectionSnapshot {
  state: ConnectionState;
  /** 사용 중이던 세션이 만료되어 PIN 재입력이 필요한 경우 */
  expired: boolean;
  error: ApiError | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly detail: string;
  readonly hint: string;

  constructor(init: {
    status: number;
    code: string;
    title: string;
    detail?: string;
    hint?: string;
  }) {
    super(init.detail ? `${init.title}: ${init.detail}` : init.title);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.title = init.title;
    this.detail = init.detail ?? '';
    this.hint = init.hint ?? '';
  }

  get isNetwork(): boolean {
    return this.code === 'network_error';
  }
  get isSessionExpired(): boolean {
    return this.code === 'session_expired';
  }
  /** 한도 초과 계열(일일 상한, 쿼터, 속도 제한) */
  get isLimit(): boolean {
    return (
      this.status === 429 ||
      /limit|quota|cap_|_cap|rate/.test(this.code) ||
      this.code === 'daily_cap_exceeded'
    );
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  query?: Query;
  body?: unknown;
  /** 위험 동작(배치 생성·실행, 롤백): Idempotency-Key 를 자동 부착한다. */
  risky?: boolean;
  /** 재시도(사용자가 다시 누름)에서 같은 키를 쓰려면 호출자가 넘긴다. */
  idempotencyKey?: string;
  signal?: AbortSignal;
}

export interface ApiClientOptions {
  fetchImpl?: typeof fetch;
  baseUrl?: string;
}

export function newKey(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  const b = new Uint8Array(16);
  c.getRandomValues(b);
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
}

const NETWORK_ERROR = () =>
  new ApiError({
    status: 0,
    code: 'network_error',
    title: '서버 연결이 끊겼습니다',
    detail: '서버에 연결할 수 없습니다.',
    hint: '서버가 켜져 있는지 확인한 뒤 "다시 연결"을 눌러 주세요.',
  });

export class ApiClient {
  private csrf: string | null = null;
  private snapshot: ConnectionSnapshot = { state: 'starting', expired: false, error: null };
  private listeners = new Set<() => void>();
  private ensuring: Promise<void> | null = null;
  private readonly fetchImpl: typeof fetch;
  private readonly baseUrl: string;

  constructor(opts: ApiClientOptions = {}) {
    this.fetchImpl = opts.fetchImpl ?? ((...a) => globalThis.fetch(...a));
    this.baseUrl = opts.baseUrl ?? '';
  }

  // ---- 연결 상태 (useSyncExternalStore 용) ----
  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };
  getSnapshot = (): ConnectionSnapshot => this.snapshot;

  private set(patch: Partial<ConnectionSnapshot>): void {
    const next = { ...this.snapshot, ...patch };
    if (
      next.state === this.snapshot.state &&
      next.expired === this.snapshot.expired &&
      next.error === this.snapshot.error
    )
      return;
    this.snapshot = next;
    this.listeners.forEach((l) => l());
  }

  // ---- 세션 ----
  /** 앱 시작: auth/me → 필요하면 세션 발급. PIN 이 필요하면 상태만 바꾸고 반환한다. */
  bootstrap(): Promise<void> {
    if (!this.ensuring) {
      this.ensuring = this.ensureSession().finally(() => {
        this.ensuring = null;
      });
    }
    return this.ensuring.catch(() => undefined);
  }

  async submitPin(pin: string): Promise<void> {
    await this.ensureSession(pin);
  }

  async logout(): Promise<void> {
    // 서버에 닿지 못한 채 "로그아웃됨"으로 보이면 세션이 서버에 남아 있는데 사용자가 모르게 되므로 성공했을 때만 상태를 바꾼다
    await this.request<void>('DELETE', '/api/v1/auth/session');
    this.csrf = null;
    this.set({ state: 'loggedout', expired: false, error: null });
  }

  private async ensureSession(pin?: string): Promise<void> {
    try {
      const me = await this.raw<AuthMe>('GET', '/api/v1/auth/me');
      if (me.authenticated && me.csrf_token) {
        this.csrf = me.csrf_token;
        this.set({ state: 'online', expired: false, error: null });
        return;
      }
      if (me.pin_required && pin === undefined) {
        this.csrf = null;
        this.set({ state: 'pin_required' });
        throw new ApiError({
          status: 401,
          code: 'pin_required',
          title: 'PIN 입력이 필요합니다',
        });
      }
      const res = await this.raw<SessionResponse>('POST', '/api/v1/auth/session', {
        body: pin === undefined ? {} : { pin },
      });
      this.csrf = res.csrf_token;
      this.set({ state: 'online', expired: false, error: null });
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.isNetwork) this.set({ state: 'offline', error: e });
        else if (e.code !== 'pin_required' && this.snapshot.state !== 'pin_required')
          this.set({ state: 'error', error: e });
      }
      throw e;
    }
  }

  // ---- 요청 ----
  async request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
    const mutating = method !== 'GET';
    const key = opts.risky ? (opts.idempotencyKey ?? newKey()) : undefined;
    if (mutating && !this.csrf) await this.ensureSession();
    try {
      return await this.raw<T>(method, path, { ...opts, key, csrf: mutating });
    } catch (e) {
      if (e instanceof ApiError && this.isAuthFailure(e)) {
        // 세션 만료: 조용히 재발급 1회 → 같은 멱등키로 재시도
        this.csrf = null;
        try {
          await this.ensureSession();
        } catch (re) {
          if (re instanceof ApiError && re.code === 'pin_required') {
            this.set({ state: 'pin_required', expired: true });
            throw new ApiError({
              status: 401,
              code: 'session_expired',
              title: '세션이 만료되었습니다',
              detail: '보안을 위해 연결이 끊겼습니다.',
              hint: 'PIN 을 다시 입력하면 이어서 사용할 수 있습니다.',
            });
          }
          throw re;
        }
        return this.raw<T>(method, path, { ...opts, key, csrf: mutating });
      }
      throw e;
    }
  }

  private isAuthFailure(e: ApiError): boolean {
    if (e.status === 401) return !e.code.startsWith('pin_');
    return e.status === 403 && /csrf/i.test(e.code);
  }

  async requestBlob(path: string, query?: Query): Promise<Blob> {
    const res = await this.send('GET', path, { query });
    return res.blob();
  }

  private async raw<T>(
    method: string,
    path: string,
    opts: RequestOptions & { key?: string; csrf?: boolean } = {},
  ): Promise<T> {
    const res = await this.send(method, path, opts);
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    if (!text) return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new ApiError({
        status: res.status,
        code: 'bad_response',
        title: '서버 응답을 읽을 수 없습니다',
        hint: '잠시 뒤 다시 시도해 주세요.',
      });
    }
  }

  private async send(
    method: string,
    path: string,
    opts: RequestOptions & { key?: string; csrf?: boolean } = {},
  ): Promise<Response> {
    const url = new URL(this.baseUrl + path, globalThis.location?.origin ?? 'http://localhost');
    for (const [k, v] of Object.entries(opts.query ?? {})) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    }
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
    if (opts.csrf && this.csrf) headers['X-CSRF-Token'] = this.csrf;
    if (opts.key) headers['Idempotency-Key'] = opts.key;

    let res: Response;
    try {
      res = await this.fetchImpl(url.pathname + url.search, {
        method,
        headers,
        credentials: 'same-origin',
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
        signal: opts.signal,
      });
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') throw e;
      const err = NETWORK_ERROR();
      this.set({ state: 'offline', error: err });
      throw err;
    }
    if (this.snapshot.state === 'offline') this.set({ state: 'online', error: null });
    if (!res.ok) throw await toApiError(res);
    return res;
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  let p: ProblemJson = {};
  try {
    const parsed: unknown = await res.json();
    if (parsed && typeof parsed === 'object') p = parsed as ProblemJson;
  } catch {
    // 본문이 JSON 이 아니면 아래 기본 문구를 쓴다
  }
  const retry = res.headers.get('Retry-After');
  const hint = [p.hint, retry && res.status === 429 ? `${retry}초 뒤에 다시 시도해 주세요.` : '']
    .filter(Boolean)
    .join(' ');
  return new ApiError({
    status: res.status,
    code: typeof p.code === 'string' && p.code ? p.code : `http_${res.status}`,
    title: str(p.title) || '요청을 처리하지 못했습니다',
    detail: str(p.detail),
    hint,
  });
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

/** 같은 요청(지문)이면 같은 멱등키를 돌려주고, 요청이 바뀌면 새 키를 만든다. 성공하면 clear(). */
export class IdempotencyKeys {
  private fp: string | null = null;
  private key: string | null = null;
  get(fingerprint: string): string {
    if (this.fp !== fingerprint || !this.key) {
      this.fp = fingerprint;
      this.key = newKey();
    }
    return this.key;
  }
  clear(): void {
    this.fp = null;
    this.key = null;
  }
}
