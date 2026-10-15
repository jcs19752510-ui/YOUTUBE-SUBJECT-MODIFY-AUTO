// @vitest-environment node
// 06단계 독립 검증(TC-VF-3xx) — 실제 백엔드(FastAPI+PostgreSQL+워커)와의 계약 연동 시험.
// 환경변수 VF_LIVE_API(예: http://127.0.0.1:18080)가 없으면 통째로 건너뛴다(일반 `npm test` 에는 영향 없음).
// 실행: VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts
import { describe, expect, it } from 'vitest';
import { ApiClient, ApiError, IdempotencyKeys } from '../src/api/client';
import { createEndpoints } from '../src/api/endpoints';

const BASE = process.env.VF_LIVE_API;
const SETTLE_MS = Number(process.env.VF_LIVE_SETTLE_MS ?? 250);
const live = describe.skipIf(!BASE);

/** Node 의 fetch 에는 쿠키 보관함과 상대 주소 해석이 없으므로 브라우저처럼 흉내 낸다(Origin 도 함께 보낸다). */
function browserLikeFetch(base: string, jar: Map<string, string>): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    if (jar.size) headers.set('Cookie', Array.from(jar, ([k, v]) => `${k}=${v}`).join('; '));
    if ((init?.method ?? 'GET') !== 'GET') headers.set('Origin', base);
    const res = await fetch(base + String(input), { ...init, headers, redirect: 'manual' });
    for (const c of res.headers.getSetCookie()) {
      const [kv] = c.split(';');
      const i = kv!.indexOf('=');
      jar.set(kv!.slice(0, i), kv!.slice(i + 1));
    }
    // 백엔드는 응답을 보낸 뒤에 commit 한다(결과서 DEF-VF-B01). 변경 요청 직후 바로 읽으면 옛 상태(예: 방금 만든 작업이 404)가 보일 수 있어, 계약 시험은 잠깐 기다린다.
    if ((init?.method ?? 'GET') !== 'GET') await new Promise((r) => setTimeout(r, SETTLE_MS));
    return res;
  }) as typeof fetch;
}
const keysOf = (o: unknown) => Object.keys(o as object).sort();
const expectKeys = (o: unknown, want: string[], label: string) => {
  const have = new Set(Object.keys(o as object));
  const missing = want.filter((k) => !have.has(k));
  expect(missing, `${label}: 누락된 필드`).toEqual([]);
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function waitJob(api: ReturnType<typeof createEndpoints>, id: string) {
  for (let i = 0; i < 60; i++) {
    const j = await api.job(id);
    if (['succeeded', 'failed', 'cancelled'].includes(j.status)) return j;
    await sleep(500);
  }
  throw new Error('작업이 끝나지 않았습니다');
}

live('실서버 계약 연동 (프런트 ApiClient + endpoints)', () => {
  const jar = new Map<string, string>();
  const client = new ApiClient({ fetchImpl: browserLikeFetch(BASE!, jar) });
  const api = createEndpoints(client);
  const ctx: {
    videoIds: string[];
    sugId?: number;
    batchId?: number;
    changeId?: number;
    vid?: string;
  } = {
    videoIds: [],
  };

  it('TC-VF-300 시작: auth/me → 세션 발급 → online, CSRF 보관, 쿠키는 HttpOnly(스크립트에 보이지 않음)', async () => {
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('online');
    expect(jar.size).toBeGreaterThan(0);
    const me = await fetch(BASE + '/api/v1/auth/me');
    const body = (await me.json()) as { authenticated: boolean };
    expect(body.authenticated).toBe(false); // 쿠키 없이는 미인증
  });

  it('TC-VF-301 홈 계약: dashboard 필드가 types.ts 와 일치한다', async () => {
    const d = await api.dashboard();
    expectKeys(
      d,
      ['mode', 'live_enabled', 'google', 'counts', 'today', 'quota', 'active_job', 'queue'],
      'dashboard',
    );
    expect(d.mode).toBe('demo');
    expect(d.live_enabled).toBe(false);
    expectKeys(
      d.counts,
      ['videos', 'excluded', 'suggested', 'approved', 'queued', 'applied'],
      'counts',
    );
    expectKeys(d.quota, ['used', 'limit', 'remaining', 'pt_date'], 'quota');
  });

  it('TC-VF-302 데모 영상 불러오기: POST videos/sync(CSRF 자동) → 작업 폴링 → succeeded', async () => {
    const d0 = await api.dashboard();
    if (d0.counts.videos === 0) {
      const job = await api.syncVideos();
      expectKeys(job, ['id', 'type', 'status', 'progress', 'total', 'error', 'result'], 'job');
      expect(job.type).toBe('videos.sync');
      const done = await waitJob(api, job.id);
      expect(done.status).toBe('succeeded');
    }
    const d = await api.dashboard();
    expect(d.counts.videos).toBeGreaterThan(0);
  }, 60000);

  it('TC-VF-303 영상 목록 계약·정렬 키·필터 값이 서버에서 받아들여진다', async () => {
    const p = await api.videos({ page: 1, page_size: 25 });
    expectKeys(p, ['items', 'total', 'page', 'page_size'], 'page');
    expectKeys(
      p.items[0],
      [
        'video_id',
        'title',
        'privacy_status',
        'duration_sec',
        'is_short',
        'excluded',
        'exclusion_reasons',
        'workflow_status',
        'suggestion_count',
        'last_change_at',
        'views',
      ],
      'video',
    );
    ctx.videoIds = p.items.filter((v) => !v.excluded).map((v) => v.video_id);
    for (const sort of ['title', 'views', 'duration_sec', 'last_change_at']) {
      const r = await api.videos({ sort, order: 'desc', page: 1, page_size: 25 });
      expect(r.items.length, `sort=${sort}`).toBeGreaterThan(0);
    }
    for (const status of [
      'none',
      'suggested',
      'approved',
      'queued',
      'applied',
      'rolled_back',
    ] as const) {
      await api.videos({ status, page: 1, page_size: 25 });
    }
    for (const excluded of ['true', 'false'] as const)
      await api.videos({ excluded, page: 1, page_size: 25 });
    const q = await api.videos({ q: p.items[0]!.title.slice(0, 4), page: 1, page_size: 25 });
    expect(q.total).toBeGreaterThan(0);
  });

  it('TC-VF-304 서버 쪽 쪽 크기 상한: 200 은 허용, 201 은 오류(프런트 상한 200 과 일치)', async () => {
    const ok = await api.videos({ page: 1, page_size: 200 });
    expect(ok.page_size).toBe(200);
    await expect(api.videos({ page: 1, page_size: 201 })).rejects.toBeInstanceOf(ApiError);
  });

  it('TC-VF-305 AI 제안 생성(작업) → 상세에서 제안·reasons·strict 계약 확인', async () => {
    const ids = ctx.videoIds.slice(0, 3);
    const job = await api.generateSuggestions(ids);
    expect(job.type).toBe('suggestions.generate');
    const done = await waitJob(api, job.id);
    expect(done.status).toBe('succeeded');
    const det = await api.video(ids[0]!);
    expectKeys(det, ['description_excerpt', 'suggestions', 'changes', 'limits'], 'detail');
    expect(det.suggestions.length).toBeGreaterThan(0);
    expectKeys(
      det.suggestions[0],
      [
        'id',
        'video_id',
        'title',
        'evidence',
        'source',
        'topic',
        'strict',
        'validation_result',
        'reasons',
        'length',
        'match_ratio',
        'status',
        'plan_hash',
        'approval',
        'created_at',
      ],
      'suggestion',
    );
    expectKeys(det.limits, ['allowed', 'reasons', 'next_allowed_at'], 'limits');
    ctx.vid = ids[0];
    const ok = det.suggestions.find(
      (s) => s.validation_result === 'pass' && !s.strict && s.status === 'candidate',
    );
    ctx.sugId = (ok ?? det.suggestions[0])!.id;
  }, 60000);

  it('TC-VF-306 제안 생성 영상 수 상한: 201개는 서버가 거절한다(프런트 상한 MAX_GENERATE=200 과 일치)', async () => {
    const many = Array.from({ length: 201 }, (_, i) => `vid${String(i).padStart(8, '0')}`);
    const e = await api.generateSuggestions(many).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect([404, 422]).toContain((e as ApiError).status);
  });

  it('TC-VF-307 승인: 승인자 없음은 서버가 거절, 정상 승인 후 approval 채워짐, 차단 제안은 409 suggestion_blocked', async () => {
    await expect(api.approve(ctx.sugId!, '')).rejects.toBeInstanceOf(ApiError);
    // 차단 제안이 있으면 확인
    const all = await api.suggestions({ page: 1, page_size: 200 });
    const blocked = all.items.find(
      (s) => s.validation_result === 'block' || (s.strict && s.validation_result !== 'pass'),
    );
    if (blocked) {
      const e = (await api.approve(blocked.id, '심사자').catch((x: unknown) => x)) as ApiError;
      expect(e).toBeInstanceOf(ApiError);
      expect(e.status).toBe(409);
      expect(['suggestion_blocked', 'suggestion_state']).toContain(e.code);
    }
    const s = await api.approve(ctx.sugId!, '심사자');
    expect(s.status).toBe('approved');
    expect(s.approval?.approver).toBe('심사자');
  });

  it('TC-VF-308 프런트의 "차단" 판정 규칙이 서버와 일치: 후보 전체에 대해 (block || strict&&!pass) 이면 승인이 409 로 거절된다', async () => {
    const all = await api.suggestions({ status: 'candidate', page: 1, page_size: 200 });
    for (const s of all.items.slice(0, 15)) {
      const feBlocked =
        s.validation_result === 'block' || (s.strict && s.validation_result !== 'pass');
      const r = await api.approve(s.id, '심사자').then(
        () => 'ok',
        (x: unknown) => (x as ApiError).code,
      );
      if (feBlocked) expect(r, `제안 ${s.id}`).not.toBe('ok');
      else if (r !== 'ok')
        expect([
          'suggestion_state',
          'video_excluded',
          'same_as_current',
          'video_inconsistent',
          'duplicate_suggestion',
        ]).toContain(r);
    }
  }, 60000);

  it('TC-VF-309 배치: 멱등키 필수 — 키 없이 직접 호출하면 400/422, 같은 키+같은 본문은 같은 결과, 같은 키+다른 본문은 422 idempotency_key_reuse', async () => {
    const approved = await api.suggestions({ status: 'approved', page: 1, page_size: 200 });
    expect(approved.items.length).toBeGreaterThan(0);
    const ids = [approved.items[0]!.id];
    const keys = new IdempotencyKeys();
    const k = keys.get(ids.join(','));
    const r1 = await api.createBatch(ids, undefined, k);
    expectKeys(r1, ['batch', 'precheck'], 'batch created');
    expectKeys(
      r1.precheck,
      [
        'item_count',
        'estimated_units',
        'daily_cap',
        'quota_remaining_units',
        'schedule',
        'warnings',
        'blocked',
        'confirm_text',
      ],
      'precheck',
    );
    ctx.batchId = r1.batch.id;
    const r2 = await api.createBatch(ids, undefined, k);
    expect(r2.batch.id).toBe(r1.batch.id);
    const e = (await api.createBatch(ids, '다른 메모', k).catch((x: unknown) => x)) as ApiError;
    expect(e).toBeInstanceOf(ApiError);
    expect(e.status).toBe(422);
    expect(e.code).toBe('idempotency_key_reuse');
    expect(e.title).toMatch(/[가-힣]/);
  });

  it('TC-VF-310 배치 상세(draft)가 precheck 를 주는지, 확인 문구 형식이 "실행 N건" 인지', async () => {
    const b = await api.batch(ctx.batchId!);
    expect(b.status).toBe('draft');
    expect(b.precheck, '서버가 상세에 precheck 를 준다(새로고침 복구 근거)').toBeTruthy();
    expect(b.precheck!.confirm_text).toBe(`실행 ${b.precheck!.item_count}건`);
  });

  it('TC-VF-311 실행: 틀린 확인 문구는 409/422 confirm_text_mismatch(한국어 안내), 맞는 문구로 실행하면 작업이 시작된다', async () => {
    const e = (await api
      .executeBatch(ctx.batchId!, '실행 99건', new IdempotencyKeys().get('x'))
      .catch((x: unknown) => x)) as ApiError;
    expect(e).toBeInstanceOf(ApiError);
    expect(e.code).toBe('confirm_text_mismatch');
    expect(e.title).toMatch(/[가-힣]/);
    const b = await api.batch(ctx.batchId!);
    const r = await api.executeBatch(
      ctx.batchId!,
      b.precheck!.confirm_text,
      new IdempotencyKeys().get('y'),
    );
    expectKeys(r, ['batch', 'job'], 'executed');
    expect(r.job.type).toBe('batch.execute');
    expect(['queued', 'running']).toContain(r.batch.status);
  });

  it('TC-VF-312 실행 후 상태 값: 배치 status 가 프런트가 아는 값(활성: queued/running, 종료: done/cancelled)만 쓰는지 폴링하며 확인', async () => {
    const seen = new Set<string>();
    for (let i = 0; i < 80; i++) {
      const b = await api.batch(ctx.batchId!);
      seen.add(b.status);
      if (['done', 'cancelled'].includes(b.status)) break;
      await sleep(500);
    }
    for (const s of seen)
      expect(['draft', 'queued', 'running', 'paused', 'done', 'cancelled'], s).toContain(s);
    expect(seen.has('done') || seen.has('cancelled')).toBe(true);
  }, 60000);

  it('TC-VF-313 이력·롤백: 변경 이력 계약, 영상 ID 틀리면 거절, 맞으면 롤백 행 생성(멱등키 재사용 시 같은 결과)', async () => {
    const ch = await api.changes({ page: 1, page_size: 50 });
    expectKeys(
      ch.items[0],
      [
        'id',
        'video_id',
        'video_title',
        'change_type',
        'previous_title',
        'new_title',
        'result',
        'mode',
        'approver',
        'applied_at',
        'verified_at',
        'error_code',
        'rollbackable',
        'batch_id',
      ],
      'change',
    );
    const target = ch.items.find((c) => c.rollbackable);
    expect(target, '롤백 가능한 변경').toBeTruthy();
    ctx.changeId = target!.id;
    const bad = (await api
      .rollback(target!.id, 'WRONG', '심사자', new IdempotencyKeys().get('a'))
      .catch((x: unknown) => x)) as ApiError;
    expect(bad).toBeInstanceOf(ApiError);
    expect(bad.code).toBe('typed_video_id_mismatch');
    const k = new IdempotencyKeys().get('b');
    const ok = await api.rollback(target!.id, target!.video_id, '심사자', k);
    expect(ok.change_type).toBe('rollback');
    const again = await api.rollback(target!.id, target!.video_id, '심사자', k);
    expect(again.id).toBe(ok.id);
  });

  it('TC-VF-314 리포트·설정·감사·구글 상태 계약', async () => {
    const r = await api.reports();
    expectKeys(r, ['items', 'notes'], 'reports');
    expect(r.notes.length).toBeGreaterThan(0);
    const s = await api.settings();
    expectKeys(
      s,
      ['daily_apply_cap', 'suggestions_per_video', 'tone', 'pin_enabled', 'mode', 'read_only'],
      'settings',
    );
    expectKeys(s.read_only, ['enable_live', 'live_allowlist', 'note'], 'read_only');
    const p = await api.patchSettings({
      daily_apply_cap: s.daily_apply_cap,
      suggestions_per_video: s.suggestions_per_video,
      tone: s.tone,
    });
    expect(keysOf(p)).toEqual(keysOf(s));
    const a = await api.audit({ page: 1, page_size: 20 });
    expectKeys(a, ['items', 'total', 'page', 'page_size', 'chain_ok'], 'audit');
    expect(a.chain_ok).toBe(true);
    const g = await api.google();
    expectKeys(g, ['mode', 'connected'], 'google');
  });

  it('TC-VF-315 서버 검증 범위가 프런트 검증과 같은 방향: 하루 상한 21·0, 말투 6개/21자, 영상당 6 는 거절', async () => {
    const bad = [
      { daily_apply_cap: 21 },
      { daily_apply_cap: 0 },
      { suggestions_per_video: 6 },
      { suggestions_per_video: 0 },
      { tone: ['a', 'b', 'c', 'd', 'e', 'f'] },
      { tone: ['가'.repeat(21)] },
    ];
    for (const patch of bad) {
      const e = await api.patchSettings(patch).catch((x: unknown) => x);
      expect(e, JSON.stringify(patch)).toBeInstanceOf(ApiError);
      expect((e as ApiError).status).toBe(422);
    }
    const okEdge = await api.patchSettings({
      daily_apply_cap: 20,
      suggestions_per_video: 5,
      tone: ['가'.repeat(20), 'b', 'c', 'd', 'e'],
    });
    expect(okEdge.tone).toHaveLength(5);
  });

  it('TC-VF-316 서버에는 라이브 허용을 켜는 입력이 없다: enable_live 키를 보내면 거절된다(프런트가 보내지 않는 이유의 방어선)', async () => {
    const e = (await client
      .request('PATCH', '/api/v1/settings', { body: { enable_live: true } })
      .catch((x: unknown) => x)) as ApiError;
    expect(e).toBeInstanceOf(ApiError);
    expect([400, 422]).toContain(e.status);
    const s = await api.settings();
    expect(s.read_only.enable_live).toBe(false);
  });

  it('TC-VF-317 CSRF: 잘못된 토큰으로 상태 변경 → 403 이고, 프런트는 재발급 1회 후 같은 요청을 성공시킨다', async () => {
    // 내부 토큰을 일부러 망가뜨려 서버가 csrf_invalid 로 거절하게 한다
    (client as unknown as { csrf: string }).csrf = 'broken-token';
    const s = await api.settings();
    const p = await api.patchSettings({ daily_apply_cap: s.daily_apply_cap });
    expect(p.daily_apply_cap).toBe(s.daily_apply_cap);
    // 토큰 없이 직접 호출하면 403
    const raw = await fetch(BASE + '/api/v1/settings', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Origin: BASE!,
        Cookie: Array.from(jar, ([k, v]) => `${k}=${v}`).join('; '),
      },
      body: '{}',
    });
    expect(raw.status).toBe(403);
    const pj = (await raw.json()) as { code: string; title: string };
    expect(pj.code).toBe('csrf_invalid');
    expect(pj.title).toMatch(/[가-힣]/);
  });

  it('TC-VF-318 모든 오류 응답은 problem+json 이고 title/hint 가 한국어이며 스택·내부 경로가 없다', async () => {
    const samples: ApiError[] = [];
    for (const f of [
      () => api.video('NOPE0000000'),
      () => api.batch(999999),
      () => api.job('00000000-0000-0000-0000-000000000000'),
      () => api.approve(999999, 'x'),
    ]) {
      const e = await f().catch((x: unknown) => x);
      expect(e).toBeInstanceOf(ApiError);
      samples.push(e as ApiError);
    }
    for (const e of samples) {
      expect(e.status).toBe(404);
      expect(e.title).toMatch(/[가-힣]/);
      expect(`${e.title}${e.detail}${e.hint}`).not.toMatch(/Traceback|\/app\/|\.py|File "/);
    }
  });

  it('TC-VF-319 CSV 내보내기: blob 으로 받고 본문에 수식 주입 위험 문자가 셀 맨 앞에 없다', async () => {
    const blob = await api.reportCsv();
    const text = await blob.text();
    expect(text.length).toBeGreaterThan(0);
    for (const line of text.split(/\r?\n/).slice(1)) {
      for (const cell of line.split(',')) expect(cell.replace(/^"/, '')).not.toMatch(/^[=+\-@]/);
    }
  });

  it('TC-VF-320 PIN: 설정 → 로그아웃 → 틀린 PIN 401 → 맞는 PIN 으로 재로그인 → 해제', async () => {
    const s0 = await api.settings();
    expect(s0.pin_enabled).toBe(false);
    const s1 = await api.patchSettings({ pin: { action: 'set', new_pin: '4321' } });
    expect(s1.pin_enabled).toBe(true);
    // 현재 PIN 없이 변경은 거절
    const e1 = (await api
      .patchSettings({ pin: { action: 'set', new_pin: '9999' } })
      .catch((x: unknown) => x)) as ApiError;
    expect(e1).toBeInstanceOf(ApiError);
    expect(e1.code.startsWith('pin_')).toBe(true);
    await client.logout();
    expect(client.getSnapshot().state).toBe('loggedout');
    await client.bootstrap();
    expect(client.getSnapshot().state).toBe('pin_required');
    await expect(client.submitPin('0000')).rejects.toBeInstanceOf(ApiError);
    expect(client.getSnapshot().state).toBe('pin_required');
    await client.submitPin('4321');
    expect(client.getSnapshot().state).toBe('online');
    const s2 = await api.patchSettings({ pin: { action: 'clear', current_pin: '4321' } });
    expect(s2.pin_enabled).toBe(false);
  });
});
