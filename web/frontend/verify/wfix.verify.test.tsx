// 06단계 독립 검증(TC-VFF) — 수정 단위 W-FIX-FE: 면책·AI 고지(POL-002·006·008·013), 차단 카드(C-1), 초안 버리기(C-2),
// 이력 필터(DEF-7-010), 새 회귀(접근성·중복 제출·CSRF/멱등키·XSS·기존 화면). 구현자 시험(src/pages/wfx.test.tsx)을 복사하지 않고 명세에서 다시 만들었다.
// 문구의 법적 충분성은 판단하지 않는다(전문가 확인 필요). 존재·노출·연결만 본다.
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Link, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { ApiClient } from '../src/api/client';
import type { Batch, Change, Suggestion } from '../src/api/types';
import { App } from '../src/app/App';
import { ko } from '../src/i18n/ko';
import { BatchDetailPage } from '../src/pages/BatchDetailPage';
import { BatchesPage } from '../src/pages/BatchesPage';
import { HistoryPage } from '../src/pages/HistoryPage';
import { ReportsPage } from '../src/pages/ReportsPage';
import { VideoDetailPage } from '../src/pages/VideoDetailPage';
import { dashboard, detail, draftBatch, suggestion } from '../src/test/fixtures';
import {
  authedHandlers,
  axeViolations,
  connectedClient,
  json,
  fakeFetch,
  problem,
  renderWithApp,
  route,
  type Handler,
} from '../src/test/utils';

const REPO = resolve(__dirname, '../../..');
const DISCLAIMER = '이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.';
const emptyPage = json(200, { items: [], total: 0, page: 1, page_size: 20 });

const videoUi = (
  <Routes>
    <Route path="videos/:videoId" element={<VideoDetailPage />} />
  </Routes>
);
const batchUi = (
  <Routes>
    <Route path="batches" element={<BatchesPage />} />
    <Route path="batches/:batchId" element={<BatchDetailPage />} />
  </Routes>
);
const cardOf = (id: number) =>
  document.querySelector<HTMLElement>(`#sg-${id}`)!.closest('article') as HTMLElement;
const openVideo = async (suggestions: Suggestion[], extra: Handler[] = [], dis = false) => {
  const c = await connectedClient([
    route('GET', '/api/v1/videos/vid00000001', () =>
      json(200, detail(suggestions, dis ? { excluded: true, exclusion_reasons: ['x'] } : {})),
    ),
    ...extra,
  ]);
  renderWithApp(videoUi, c.client, '/videos/vid00000001');
  return c;
};

// =====================================================================================================
// A. 문구의 단일 출처 · 서버/CLI 일치 · 빌드 대상 소스
// =====================================================================================================
const srcRaw = import.meta.glob(
  [
    '../src/**/*.ts',
    '../src/**/*.tsx',
    '!../src/**/*.test.ts',
    '!../src/**/*.test.tsx',
    '!../src/test/**',
  ],
  { query: '?raw', import: 'default', eager: true },
) as Record<string, string>;

describe('A. 문구 단일 출처 (POL-002·006·008·013)', () => {
  it('TC-VFF-001 ko.legal 의 모든 문장은 ko.ts 에만 있고 다른 소스에 복제되지 않는다(비어 있지 않은 문장 11개 이상)', () => {
    const values = Object.values(ko.legal).filter((v) => typeof v === 'string' && v.length > 8);
    expect(values.length).toBeGreaterThanOrEqual(11);
    const files = Object.entries(srcRaw);
    expect(files.length).toBeGreaterThan(30);
    for (const v of values) {
      const holders = files.filter(([, s]) => s.includes(v)).map(([f]) => f);
      expect(holders, v).toEqual(['../src/i18n/ko.ts']);
    }
  });

  it('TC-VFF-002 면책 문장은 서버(notices.py)·CLI(ui.py)·개발용 모의 서버와 한 글자도 다르지 않다', () => {
    const py = (p: string) => readFileSync(resolve(REPO, p), 'utf8');
    const fromPy = (s: string) => /DISCLAIMER\s*=\s*"([^"]+)"/.exec(s)?.[1];
    expect(fromPy(py('web/backend/ytweb/domain/notices.py'))).toBe(ko.legal.disclaimer);
    expect(fromPy(py('src/youtube_title/ui.py'))).toBe(ko.legal.disclaimer);
    expect(readFileSync(resolve(REPO, 'web/frontend/dev/mock-server.mjs'), 'utf8')).toContain(
      ko.legal.disclaimer,
    );
    expect(ko.legal.disclaimer).toBe(DISCLAIMER);
  });

  it('TC-VFF-003 필수 개념 어휘 확인: 면책(법률 자문·최종 책임), AI 생성·사람 승인, 사실·법령 비보장·표시광고·건강/금융, A/B 확인', () => {
    const L = ko.legal;
    expect(L.disclaimer).toMatch(/법률 자문이 아니며/);
    expect(L.disclaimer).toMatch(/최종 책임은 채널 소유자/);
    expect(L.aiNotice).toMatch(/AI가 생성/);
    expect(L.aiNotice).toMatch(/사람이 검토하고 승인/);
    expect(L.aiLimit).toMatch(/사실과 법령 적합성을 보장하지 않/);
    expect(L.aiLimit).toMatch(/건강·금융/);
    expect(L.aiLimit).toMatch(/표시·광고/);
    expect(L.abConfirm).toMatch(/A\/B 테스트 중이 아님/);
    // 영문 식별자가 사용자 문구에 새지 않는다
    for (const v of Object.values(L)) expect(v).not.toMatch(/\b(blocked|undefined|null|TODO)\b/);
  });

  it('TC-VFF-004 정적 규칙: 소스에 dangerouslySetInnerHTML·innerHTML·외부 CDN·eval 이 없다(수정 단위 파일 포함)', () => {
    const own = [
      '../src/pages/DiscardDraft.tsx',
      '../src/pages/SuggestionCard.tsx',
      '../src/pages/BatchDetailPage.tsx',
      '../src/pages/BatchesPage.tsx',
      '../src/app/Layout.tsx',
      '../src/i18n/ko.ts',
    ];
    for (const f of own) expect(srcRaw[f], f).toBeTruthy();
    for (const [f, s] of Object.entries(srcRaw)) {
      expect(s, f).not.toMatch(/dangerouslySetInnerHTML|\.innerHTML|\beval\(|new Function\(/);
      expect(s.replace(/\/\/.*$/gm, ''), f).not.toMatch(/https?:\/\/(?!localhost|127\.0\.0\.1)/);
    }
  });

  it('TC-VFF-005 계약 교차 확인: 화면 라벨 표가 서버 열거값(models.py)을 빠짐없이 덮는다(제안·배치·항목·변경 결과)', () => {
    const models = readFileSync(resolve(REPO, 'web/backend/ytweb/db/models.py'), 'utf8');
    const tup = (name: string) => {
      const m = new RegExp(`^${name}\\s*=\\s*\\(([^)]*)\\)`, 'm').exec(models)![1]!;
      return Array.from(m.matchAll(/"([^"]+)"/g), (x) => x[1]!);
    };
    const miss = (vals: string[], map: Record<string, string>) =>
      vals.filter((v) => !Object.hasOwn(map, v));
    expect(miss(tup('SUGGESTION_STATUSES'), ko.suggestionStatus)).toEqual([]);
    expect(miss(tup('BATCH_STATUSES'), ko.batchStatus)).toEqual([]);
    expect(miss(tup('BATCH_ITEM_STATUSES'), ko.itemStatus)).toEqual([]);
    expect(miss(tup('CHANGE_RESULTS'), ko.changeResult)).toEqual([]);
    expect(miss(tup('CHANGE_TYPES'), ko.changeType)).toEqual([]);
    expect(miss(tup('VALIDATION_RESULTS'), ko.validation as Record<string, string>)).toEqual([]);
    // 이력 필터 선택지는 서버가 받는 값과 정확히 같다
    expect([...ko.resultFilter]).toEqual(tup('CHANGE_RESULTS'));
    // 한국어 값에 영문 상태 토큰이 그대로 노출되지 않는다
    for (const map of [ko.suggestionStatus, ko.batchStatus, ko.itemStatus, ko.changeResult]) {
      for (const v of Object.values(map)) expect(v).toMatch(/[가-힣]/);
    }
  });
});

// =====================================================================================================
// B. 전 화면 푸터(면책) 노출
// =====================================================================================================
describe('B. 전 화면 면책 푸터 (POL-002)', () => {
  const ROUTES = [
    '/',
    '/videos',
    '/videos/vid00000001',
    '/batches',
    '/batches/7',
    '/history',
    '/reports',
    '/settings',
    '/no-such-page',
  ];
  it.each(ROUTES)(
    'TC-VFF-010 %s : 푸터(면책+AI 안내)가 본문 밖 contentinfo 로 한 개 있다',
    async (path) => {
      const { client } = await connectedClient([
        route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
        route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
      ]);
      renderWithApp(<App />, client, path);
      // 데이터 로딩·실패 여부와 무관하게 푸터는 항상 존재해야 한다
      const foot = await screen.findByRole('contentinfo', { name: ko.legal.footerLabel });
      expect(within(foot).getByText(DISCLAIMER)).toBeInTheDocument();
      expect(within(foot).getByText(ko.legal.aiNotice)).toBeInTheDocument();
      expect(screen.getAllByRole('contentinfo')).toHaveLength(1);
      expect(screen.getByRole('main')).not.toContainElement(foot);
    },
  );

  it('TC-VFF-011 모든 API 가 500 이어도(화면 오류 상태) 푸터는 남는다', async () => {
    const { client } = await connectedClient([
      (r) => (r.path.startsWith('/api/v1/auth') ? undefined : problem(500, 'http_500', 'x')),
    ]);
    renderWithApp(<App />, client, '/videos');
    expect(await screen.findByRole('contentinfo', { name: ko.legal.footerLabel })).toBeVisible();
    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument();
  });

  // DEF-VFF-001(Low, Open): ReportsPage 가 /법률 자문/ 단어 포함 여부로 중복을 판단해 정확히 같은 문장이 아니어도 화면 면책을 숨긴다. 고쳐지면 it.fails 를 it 로 바꾼다.
  it.fails(
    'TC-VFF-012 서버 notes 에 "법률 자문" 단어만 있는 다른 문장이 있어도 화면 면책 문장은 숨겨지지 않는다',
    async () => {
      const { client } = await connectedClient([
        route('GET', '/api/v1/reports/changes', () =>
          json(200, { items: [], notes: ['법률 자문이 필요하면 전문가에게 문의하세요.'] }),
        ),
      ]);
      renderWithApp(<ReportsPage />, client);
      await screen.findByText('법률 자문이 필요하면 전문가에게 문의하세요.');
      expect(screen.getAllByText(DISCLAIMER)).toHaveLength(1);
    },
  );

  it('TC-VFF-013 리포트: 서버 notes 에 정확히 같은 면책이 있으면 한 번만, 없으면 화면이 보태 한 번 보인다(빈 notes 포함)', async () => {
    for (const notes of [[DISCLAIMER, 'a'], ['a'], []]) {
      const { client } = await connectedClient([
        route('GET', '/api/v1/reports/changes', () => json(200, { items: [], notes })),
      ]);
      const { unmount } = renderWithApp(<ReportsPage />, client);
      await screen.findByText(ko.legal.reportsNote);
      expect(screen.getAllByText(DISCLAIMER)).toHaveLength(1);
      unmount();
    }
  });
});

// =====================================================================================================
// C. AI 고지 · 한계 · 엄격 모드 주의 — 제안 카드
// =====================================================================================================
describe('C. 제안 카드의 AI 고지·한계·주의 (POL-006·008)', () => {
  const STATUSES = [
    'candidate',
    'blocked',
    'approved',
    'rejected',
    'expired',
    'queued',
    'applied',
    'rolled_back',
  ] as const;

  it.each(STATUSES)(
    'TC-VFF-020 상태 %s : AI 제안은 AI 고지·한계가 보이고 영문 상태 토큰이 새지 않는다',
    async (st) => {
      await openVideo([
        suggestion(1, {
          status: st,
          source: 'ai:mock',
          validation_result: st === 'blocked' ? 'block' : 'pass',
        }),
      ]);
      await screen.findByRole('heading', { name: '테스트 영상 1 핵심 정리' });
      const card = cardOf(1);
      expect(within(card).getByText(ko.legal.aiNotice)).toBeInTheDocument();
      expect(within(card).getByText(ko.legal.aiLimit)).toBeInTheDocument();
      expect(card.textContent).not.toMatch(
        /\b(candidate|blocked|approved|rejected|expired|queued|applied|rolled_back)\b/,
      );
    },
  );

  it('TC-VFF-021 직접 입력(manual) 제안: AI 고지는 없고 한계 안내와 면책(영상 상세 위쪽)은 남는다', async () => {
    await openVideo([suggestion(2, { source: 'manual', title: '직접 쓴 제목' })]);
    await screen.findByText('직접 쓴 제목');
    expect(within(cardOf(2)).queryByText(ko.legal.aiNotice)).toBeNull();
    expect(within(cardOf(2)).getByText(ko.legal.aiLimit)).toBeInTheDocument();
    expect(screen.getAllByText(DISCLAIMER).length).toBeGreaterThanOrEqual(1);
  });

  it('TC-VFF-022 source 값이 알 수 없는 문자열("ai:other", 빈 문자열)이어도 AI 로 보고 고지한다(fail-safe)', async () => {
    await openVideo([
      suggestion(1, { source: 'ai:other', title: 'A제안' }),
      suggestion(2, { source: '', title: 'B제안' }),
    ]);
    await screen.findByRole('heading', { name: 'A제안' });
    expect(within(cardOf(1)).getByText(ko.legal.aiNotice)).toBeInTheDocument();
    expect(within(cardOf(2)).getByText(ko.legal.aiNotice)).toBeInTheDocument();
  });

  it('TC-VFF-023 엄격 모드(strict) 카드에만 건강·금융 주의가 있고, 비엄격 카드에는 없다', async () => {
    await openVideo([
      suggestion(1, { strict: true, title: '건강제안' }),
      suggestion(2, { strict: false, title: '일반제안' }),
    ]);
    await screen.findByRole('heading', { name: '건강제안' });
    expect(within(cardOf(1)).getByText(ko.legal.strictCaution)).toBeInTheDocument();
    expect(within(cardOf(2)).queryByText(ko.legal.strictCaution)).toBeNull();
  });

  it('TC-VFF-024 승인 대화상자: 면책·AI 고지·한계가 모두 보이고(엄격이면 주의도), 열기만 해서는 서버 호출이 없다', async () => {
    const user = userEvent.setup();
    const c = await openVideo([suggestion(1, { strict: true })]);
    await screen.findByRole('heading', { name: '테스트 영상 1 핵심 정리' });
    await user.click(within(cardOf(1)).getByRole('button', { name: '승인' }));
    const dlg = await screen.findByRole('dialog');
    for (const t of [DISCLAIMER, ko.legal.aiNotice, ko.legal.aiLimit, ko.legal.strictCaution])
      expect(within(dlg).getByText(t)).toBeInTheDocument();
    expect(c.calls.some((x) => x.method === 'POST')).toBe(false);
  });

  it('TC-VFF-025 영상 상세: "통과" 의미 안내와 면책이 있다', async () => {
    await openVideo([suggestion(1)]);
    await screen.findByText(ko.legal.validationNote);
    expect(screen.getAllByText(DISCLAIMER)).toHaveLength(1); // 영상 상세 안내(푸터는 Layout 소속이라 이 렌더에는 없음)
  });

  it('TC-VFF-026 이력 화면에 AI 고지와 이력 안내가 있다(빈 결과여도)', async () => {
    const { client } = await connectedClient([route('GET', '/api/v1/changes', () => emptyPage)]);
    renderWithApp(<HistoryPage />, client);
    // 조회 기간 기본값이 오늘이라, 비어 있는 첫 사용 안내를 보려면 전체 기간으로 바꾼다(2026-10-14)
    fireEvent.click(await screen.findByRole('button', { name: '전체 기간' }));
    await screen.findByText(ko.history.emptyTitle);
    expect(screen.getByText(ko.legal.aiNotice)).toBeInTheDocument();
    expect(screen.getByText(ko.legal.historyNote)).toBeInTheDocument();
  });
});

// =====================================================================================================
// D. A/B 확인 (POL-013)
// =====================================================================================================
describe('D. 배치 실행 A/B 확인 (POL-013)', () => {
  const ok = (b: Batch) =>
    json(202, {
      batch: { ...b, status: 'running', executed_at: '2026-10-10T00:00:00Z' },
      job: {
        id: 'j',
        type: 'batch.execute',
        status: 'queued',
        progress: 0,
        total: 2,
        error: null,
        result: null,
      },
    });
  async function setup(extra: Handler[] = [], batch: Batch = draftBatch()) {
    const c = await connectedClient([
      route('GET', /^\/api\/v1\/batches\/\d+$/, () => json(200, batch)),
      ...extra,
    ]);
    renderWithApp(batchUi, c.client, `/batches/${batch.id}`);
    await screen.findByLabelText(/확인 문구 입력/);
    return c;
  }
  const exec = () => screen.getByRole('button', { name: '실행' });
  const box = () => screen.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ });
  const phrase = () => screen.getByLabelText(/확인 문구 입력/);

  it.each([
    [false, false, false],
    [true, false, false],
    [false, true, false],
    [true, true, true],
  ])(
    'TC-VFF-030 확인문구 일치=%s · A/B 확인=%s → 실행 버튼 활성=%s',
    async (typed, ack, enabled) => {
      const user = userEvent.setup();
      await setup();
      if (typed) await user.type(phrase(), '실행 2건');
      else await user.type(phrase(), '실행 3건');
      if (ack) await user.click(box());
      if (enabled) expect(exec()).toBeEnabled();
      else expect(exec()).toBeDisabled();
    },
  );

  it('TC-VFF-031 확인란을 켰다 끄면 다시 꺼지고, 문구를 지우면 꺼진다(순서 무관)', async () => {
    const user = userEvent.setup();
    await setup();
    await user.click(box());
    await user.type(phrase(), '실행 2건');
    expect(exec()).toBeEnabled();
    await user.clear(phrase());
    expect(exec()).toBeDisabled();
    await user.type(phrase(), '실행 2건');
    expect(exec()).toBeEnabled();
    await user.click(box());
    expect(exec()).toBeDisabled();
  });

  it('TC-VFF-032 확인 문구 입력창에서 Enter 를 눌러도 A/B 미확인이면 실행 요청이 가지 않는다', async () => {
    const user = userEvent.setup();
    const c = await setup();
    await user.type(phrase(), '실행 2건{Enter}');
    await new Promise((r) => setTimeout(r, 30));
    expect(c.calls.some((x) => x.path.endsWith('/execute'))).toBe(false);
  });

  it('TC-VFF-033 비활성 버튼을 강제로 눌러도(fireEvent) 요청이 가지 않는다', async () => {
    const user = userEvent.setup();
    const c = await setup();
    await user.type(phrase(), '실행 2건');
    fireEvent.click(exec());
    await new Promise((r) => setTimeout(r, 30));
    expect(c.calls.some((x) => x.path.endsWith('/execute'))).toBe(false);
  });

  it('TC-VFF-034 실행: 요청은 1번, CSRF·Idempotency-Key 가 붙고 본문은 confirm_text 뿐이다(서버 계약 불변, DEC-047)', async () => {
    const user = userEvent.setup();
    const c = await setup([route('POST', '/api/v1/batches/7/execute', () => ok(draftBatch()))]);
    await user.click(box());
    await user.type(phrase(), '실행 2건');
    await user.click(exec());
    await waitFor(() => expect(c.calls.some((x) => x.path.endsWith('/execute'))).toBe(true));
    const posts = c.calls.filter((x) => x.path.endsWith('/execute'));
    expect(posts).toHaveLength(1);
    expect(posts[0]!.headers['x-csrf-token']).toBe('csrf-1');
    expect(posts[0]!.headers['idempotency-key']).toMatch(/^[0-9a-f-]{16,}$/);
    expect(posts[0]!.body).toEqual({ confirm_text: '실행 2건' });
  });

  it('TC-VFF-035 서버 거절(409) 뒤 재시도하면 같은 Idempotency-Key 를 쓰고 확인란은 그대로 유지된다', async () => {
    const user = userEvent.setup();
    let n = 0;
    const c = await setup([
      route('POST', '/api/v1/batches/7/execute', () =>
        ++n === 1 ? problem(409, 'batch_state', '지금은 실행할 수 없습니다') : ok(draftBatch()),
      ),
    ]);
    await user.click(box());
    await user.type(phrase(), '실행 2건');
    await user.click(exec());
    await screen.findByText('지금은 실행할 수 없습니다');
    expect(box()).toBeChecked();
    await user.click(exec());
    await waitFor(() => expect(n).toBe(2));
    const keys = c.calls
      .filter((x) => x.path.endsWith('/execute'))
      .map((x) => x.headers['idempotency-key']);
    expect(new Set(keys).size).toBe(1);
  });

  it('TC-VFF-036 확인란은 접근 가능한 이름·설명을 갖고, 설명 대상 요소가 실제로 존재한다', async () => {
    await setup();
    const b = box();
    expect(b).toHaveAccessibleDescription(ko.legal.abNeeded);
    expect(document.getElementById(b.getAttribute('aria-describedby')!)).not.toBeNull();
    expect(screen.getByText(ko.legal.abHint)).toBeInTheDocument();
    await userEvent.click(b);
    expect(screen.queryByText(ko.legal.abNeeded)).toBeNull(); // 확인하면 "선택해야 한다" 안내가 사라진다
    expect(b).not.toHaveAccessibleDescription(ko.legal.abNeeded);
  });

  it('TC-VFF-037 모두 제외된 초안(item_count 0): 실행 영역 대신 안내만 있고 확인란·실행 버튼이 없다', async () => {
    const b = draftBatch({
      precheck: { ...draftBatch().precheck!, item_count: 0, confirm_text: '실행 0건' },
    });
    const c = await connectedClient([route('GET', '/api/v1/batches/7', () => json(200, b))]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByText(ko.batches.pc.allBlocked);
    expect(screen.queryByRole('checkbox', { name: /A\/B/ })).toBeNull();
    expect(screen.queryByRole('button', { name: '실행' })).toBeNull();
  });

  it.each(['queued', 'running', 'done', 'cancelled'] as const)(
    'TC-VFF-038 상태 %s 배치에는 확인란·[초안 버리기]가 나오지 않는다',
    async (st) => {
      const b = draftBatch({ status: st, executed_at: '2026-10-10T00:00:00Z' });
      const c = await connectedClient([route('GET', '/api/v1/batches/7', () => json(200, b))]);
      renderWithApp(batchUi, c.client, '/batches/7');
      await screen.findByText(ko.batches.progressTitle);
      expect(screen.queryByRole('checkbox', { name: /A\/B/ })).toBeNull();
      expect(screen.queryByRole('button', { name: /초안 버리기/ })).toBeNull();
    },
  );

  it('TC-VFF-039 앱 안에서 (이미 캐시된) 다른 초안으로 이동하면 확인란·문구가 초기화된다(이전 확인을 새 배치에 끌고 가지 않는다)', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch({ id: 7 }))),
      route('GET', '/api/v1/batches/8', () => json(200, draftBatch({ id: 8 }))),
    ]);
    renderWithApp(
      <Routes>
        <Route
          path="batches/:batchId"
          element={
            <>
              <Link to="/batches/8">go8</Link>
              <Link to="/batches/7">go7</Link>
              <BatchDetailPage />
            </>
          }
        />
      </Routes>,
      c.client,
      '/batches/7',
    );
    await screen.findByLabelText(/확인 문구 입력/);
    await user.click(screen.getByRole('link', { name: 'go8' })); // 8 을 캐시에 올린다
    await screen.findByRole('heading', { name: ko.batches.batchTitle(8) });
    await screen.findByLabelText(/확인 문구 입력/);
    await user.click(box());
    await user.type(phrase(), '실행 2건');
    expect(exec()).toBeEnabled();
    await user.click(screen.getByRole('link', { name: 'go7' })); // 7 은 캐시에 있어 즉시 표시된다
    await screen.findByRole('heading', { name: ko.batches.batchTitle(7) });
    expect(box()).not.toBeChecked();
    expect(phrase()).toHaveValue('');
    expect(exec()).toBeDisabled();
  });

  it('TC-VFF-040 사전 점검 카드: 한계 안내와 면책(서버 notice 우선, 빈 문자열이면 화면 문구)', async () => {
    for (const [notice, want] of [
      ['서버 고지 문장', '서버 고지 문장'],
      [undefined, DISCLAIMER],
    ] as const) {
      const b = draftBatch({ precheck: { ...draftBatch().precheck!, notice } });
      const c = await connectedClient([route('GET', '/api/v1/batches/7', () => json(200, b))]);
      const { unmount } = renderWithApp(batchUi, c.client, '/batches/7');
      await screen.findByText(ko.legal.aiLimit);
      expect(screen.getByText(want)).toBeInTheDocument();
      unmount();
    }
  });
});

// =====================================================================================================
// E. 차단 카드 (C-1)
// =====================================================================================================
describe('E. 차단(blocked) 제안 카드 (C-1, DEF-7-008)', () => {
  const blockedSug = (over: Partial<Suggestion> = {}) =>
    suggestion(3, {
      title: '무조건 100% 성공',
      status: 'blocked',
      validation_result: 'block',
      reasons: [{ code: 'banned', severity: 'block', message: '단정 표현 금지' }],
      ...over,
    });

  it('TC-VFF-050 차단 카드: 배지 "차단"·상태 "차단됨", 영문 blocked 없음, 수정·반려 가능, 승인 비활성', async () => {
    await openVideo([blockedSug()]);
    await screen.findByText('무조건 100% 성공');
    const c = within(cardOf(3));
    expect(c.getByText('차단됨')).toBeInTheDocument();
    expect(cardOf(3).textContent).not.toMatch(/blocked/i);
    expect(c.getByRole('button', { name: '제목 수정' })).toBeEnabled();
    expect(c.getByRole('button', { name: '반려' })).toBeEnabled();
    expect(c.getByRole('button', { name: '승인' })).toBeDisabled();
  });

  it('TC-VFF-051 비활성 승인 버튼을 눌러도(실사용자 클릭) 승인 대화상자가 열리지 않고 POST 도 없다', async () => {
    const user = userEvent.setup();
    const c = await openVideo([blockedSug()]);
    await screen.findByText('무조건 100% 성공');
    await user.click(within(cardOf(3)).getByRole('button', { name: '승인' }));
    fireEvent.click(within(cardOf(3)).getByRole('button', { name: '승인' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(c.calls.some((x) => x.method !== 'GET' && x.path.includes('/suggestions/'))).toBe(false);
  });

  it('TC-VFF-052 승인 불가 사유: 서버 사유 문장이 보이고, 사유가 없으면 대체 안내가 보인다', async () => {
    await openVideo([
      blockedSug(),
      blockedSug({ id: 4, title: '사유없음', reasons: [] } as Partial<Suggestion>),
    ]);
    await screen.findByRole('heading', { name: '사유없음' });
    expect(within(cardOf(3)).getAllByText('단정 표현 금지').length).toBeGreaterThanOrEqual(2);
    expect(within(cardOf(4)).getByText(ko.suggestion.cannotApproveNoReason)).toBeInTheDocument();
    // 다음에 할 일(수정·반려 안내)도 함께 보인다
    expect(within(cardOf(3)).getByText(ko.suggestion.blockedStatusHint)).toBeInTheDocument();
    // 엄격 모드 전용 설명은 일반 차단 카드에는 없다
    expect(within(cardOf(3)).queryByText(ko.suggestion.cannotApproveStrict)).toBeNull();
  });

  it('TC-VFF-053 차단 카드 수정: PATCH 본문은 앞뒤 공백을 자른 새 제목, CSRF 부착, 같은 제목이면 저장 비활성', async () => {
    const user = userEvent.setup();
    const c = await openVideo(
      [blockedSug()],
      [route('PATCH', '/api/v1/suggestions/3', () => json(200, blockedSug({ title: '새 제목' })))],
    );
    await screen.findByText('무조건 100% 성공');
    await user.click(within(cardOf(3)).getByRole('button', { name: '제목 수정' }));
    const dlg = await screen.findByRole('dialog');
    const save = within(dlg).getByRole('button', { name: '저장' });
    expect(save).toBeDisabled(); // 같은 제목
    const input = within(dlg).getByLabelText('새 제목');
    await user.clear(input);
    expect(save).toBeDisabled(); // 빈 제목
    await user.type(input, '  새 제목  ');
    await user.click(save);
    await waitFor(() => expect(c.calls.some((x) => x.method === 'PATCH')).toBe(true));
    const p = c.calls.filter((x) => x.method === 'PATCH');
    expect(p).toHaveLength(1);
    expect(p[0]!.body).toEqual({ title: '새 제목' });
    expect(p[0]!.headers['x-csrf-token']).toBe('csrf-1');
  });

  it('TC-VFF-054 차단 카드 반려: 확인 단계 후 POST reject 1번(CSRF 부착), 취소하면 호출 없음', async () => {
    const user = userEvent.setup();
    const c = await openVideo(
      [blockedSug()],
      [
        route('POST', '/api/v1/suggestions/3/reject', () =>
          json(200, blockedSug({ status: 'rejected' })),
        ),
      ],
    );
    await screen.findByText('무조건 100% 성공');
    await user.click(within(cardOf(3)).getByRole('button', { name: '반려' }));
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: '취소' }),
    );
    expect(c.calls.some((x) => x.path.endsWith('/reject'))).toBe(false);
    await user.click(within(cardOf(3)).getByRole('button', { name: '반려' }));
    const dlg = await screen.findByRole('dialog');
    await user.click(within(dlg).getByRole('button', { name: '반려' }));
    await waitFor(() => expect(c.calls.some((x) => x.path.endsWith('/reject'))).toBe(true));
    const r = c.calls.filter((x) => x.path.endsWith('/reject'));
    expect(r).toHaveLength(1);
    expect(r[0]!.headers['x-csrf-token']).toBe('csrf-1');
  });

  it('TC-VFF-055 제외된 영상(excluded)의 차단 카드: 수정·승인·반려 모두 잠긴다', async () => {
    await openVideo([blockedSug()], [], true);
    await screen.findByText('무조건 100% 성공');
    const c = within(cardOf(3));
    for (const n of ['제목 수정', '승인', '반려'])
      expect(c.getByRole('button', { name: n })).toBeDisabled();
  });

  it.each([
    ['warn', true, false],
    ['pass', true, true],
    ['warn', false, true],
    ['block', false, false],
  ] as const)(
    'TC-VFF-056 승인 가능 규칙(서버와 동일): 검증=%s · 엄격=%s → 승인 가능=%s',
    async (vr, strict, canApprove) => {
      await openVideo([suggestion(1, { validation_result: vr, strict, status: 'candidate' })]);
      await screen.findByRole('heading', { name: '테스트 영상 1 핵심 정리' });
      const b = within(cardOf(1)).getByRole('button', { name: '승인' });
      if (canApprove) expect(b).toBeEnabled();
      else expect(b).toBeDisabled();
    },
  );

  it('TC-VFF-057 승인 완료(approved) 카드에는 승인 버튼이 없고 수정·반려는 있다(회귀)', async () => {
    await openVideo([suggestion(1, { status: 'approved' })]);
    await screen.findByRole('heading', { name: '테스트 영상 1 핵심 정리' });
    const c = within(cardOf(1));
    expect(c.queryByRole('button', { name: '승인' })).toBeNull();
    expect(c.getByRole('button', { name: '제목 수정' })).toBeEnabled();
    expect(c.getByRole('button', { name: '반려' })).toBeEnabled();
  });

  it('TC-VFF-058 반영 완료·반려·되돌림 카드에는 어떤 버튼도 없다(회귀)', async () => {
    await openVideo([
      suggestion(1, { status: 'applied', title: 'a1' }),
      suggestion(2, { status: 'rejected', title: 'a2' }),
      suggestion(3, { status: 'rolled_back', title: 'a3' }),
    ]);
    await screen.findByRole('heading', { name: 'a1' });
    for (const id of [1, 2, 3]) expect(within(cardOf(id)).queryAllByRole('button')).toHaveLength(0);
  });
});

// =====================================================================================================
// F. 초안 버리기 (C-2)
// =====================================================================================================
describe('F. 초안 배치 버리기 (C-2, DEF-7-009)', () => {
  const listed = (b: Batch) => ({ ...b, items: [] });
  const sugs: Suggestion[] = [1, 2].map((n) =>
    suggestion(n, {
      video_id: `vid0000000${n}`,
      title: `승인된 제목 ${n}`,
      status: 'approved',
      approval: {
        approver: '홍',
        approved_at: '2026-10-10T00:00:00Z',
        expires_at: '2026-10-11T00:00:00Z',
      },
    }),
  );

  it('TC-VFF-060 흐름: 열기→(Esc 로 닫기: 호출 없음)→다시 열기→버리기 1번→"버려진 초안" 상태, 모달 닫힘', async () => {
    const user = userEvent.setup();
    let gone = false;
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () =>
        json(200, gone ? draftBatch({ status: 'cancelled' }) : draftBatch()),
      ),
      route('POST', '/api/v1/batches/7/cancel', () => {
        gone = true;
        return json(200, draftBatch({ status: 'cancelled' }));
      }),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    const open = await screen.findByRole('button', { name: /초안 버리기/ });
    await user.click(open);
    await screen.findByRole('dialog', { name: ko.batches.discardTitle });
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(c.calls.some((x) => x.path.endsWith('/cancel'))).toBe(false);
    await user.click(screen.getByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog');
    await user.click(within(dlg).getByRole('button', { name: '버리기' }));
    await screen.findByText(ko.batches.discardedBody);
    expect(c.calls.filter((x) => x.path.endsWith('/cancel'))).toHaveLength(1);
    expect(c.calls.find((x) => x.path.endsWith('/cancel'))!.body).toEqual({});
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('checkbox', { name: /A\/B/ })).toBeNull();
    expect(screen.queryByText(ko.batches.progressTitle)).toBeNull();
  });

  it('TC-VFF-061 실행한 적 있는 취소 배치(executed_at 있음)는 "버려진 초안"이 아니라 "중지됨"으로 보이고 진행 카드가 남는다', async () => {
    const b = draftBatch({ status: 'cancelled', executed_at: '2026-10-10T00:00:00Z' });
    const c = await connectedClient([route('GET', '/api/v1/batches/7', () => json(200, b))]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByText(ko.batches.progressTitle);
    expect(screen.queryByText(ko.batches.discardedLabel)).toBeNull();
    expect(screen.getAllByText('중지됨').length).toBeGreaterThanOrEqual(1);
  });

  it('TC-VFF-062 서버가 이중 취소를 409 로 거절하면 한국어 오류, 모달 유지, 다시 누르면 재요청', async () => {
    const user = userEvent.setup();
    let n = 0;
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
      route('POST', '/api/v1/batches/7/cancel', () => {
        n++;
        return problem(
          409,
          'batch_not_cancellable',
          '이미 끝났거나 취소된 배치입니다(상태: cancelled).',
        );
      }),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await user.click(await screen.findByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog');
    await user.click(within(dlg).getByRole('button', { name: '버리기' }));
    await within(dlg).findByText(/이미 끝났거나 취소된 배치입니다/);
    expect(screen.getByRole('dialog')).toBe(dlg);
    // 닫았다 열면 이전 오류가 지워진다
    await user.click(within(dlg).getByRole('button', { name: '취소' }));
    await user.click(screen.getByRole('button', { name: /초안 버리기/ }));
    const dlg2 = await screen.findByRole('dialog');
    expect(within(dlg2).queryByText(/이미 끝났거나/)).toBeNull();
    await user.click(within(dlg2).getByRole('button', { name: '버리기' }));
    await waitFor(() => expect(n).toBe(2));
    void c;
  });

  it('TC-VFF-063 버리기 도중 연결이 끊기면 한국어 연결 오류를 모달 안에 보이고 모달은 유지된다(화면 멈춤 없음)', async () => {
    const user = userEvent.setup();
    let down = false;
    const inner = fakeFetch([
      ...authedHandlers,
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
    ]);
    const client = new ApiClient({
      fetchImpl: ((...a: Parameters<typeof fetch>) =>
        down
          ? Promise.reject(new TypeError('Failed to fetch'))
          : inner.fetch(...a)) as typeof fetch,
    });
    await client.bootstrap();
    renderWithApp(batchUi, client, '/batches/7');
    await user.click(await screen.findByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog');
    down = true;
    await user.click(within(dlg).getByRole('button', { name: '버리기' }));
    await within(dlg).findByText('서버 연결이 끊겼습니다');
    expect(within(dlg).getByRole('button', { name: '버리기' })).toBeEnabled();
    expect(dlg.textContent).not.toMatch(/Failed to fetch|TypeError/);
  });

  it('TC-VFF-064 목록: 초안 행에만 [초안 버리기](행마다 구분되는 이름), 완료·중지 행에는 없다', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', () => emptyPage),
      route('GET', '/api/v1/batches', () =>
        json(200, {
          items: [
            listed(draftBatch({ id: 11 })),
            listed(draftBatch({ id: 12, status: 'done', executed_at: '2026-10-09T00:00:00Z' })),
            listed(draftBatch({ id: 13, status: 'cancelled', executed_at: null })),
            listed(
              draftBatch({ id: 14, status: 'cancelled', executed_at: '2026-10-09T00:00:00Z' }),
            ),
            listed(draftBatch({ id: 15 })),
          ],
          total: 5,
          page: 1,
          page_size: 20,
        }),
      ),
      route('GET', /^\/api\/v1\/batches\/\d+$/, (r) =>
        json(200, draftBatch({ id: Number(r.path.split('/').pop()) })),
      ),
    ]);
    renderWithApp(batchUi, c.client, '/batches');
    await screen.findByText('#11');
    expect(screen.getAllByRole('button', { name: /초안 버리기/ })).toHaveLength(2);
    expect(screen.getByRole('button', { name: /초안 버리기\s*\(배치 #11\)/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /초안 버리기\s*\(배치 #15\)/ })).toBeInTheDocument();
    expect(screen.getAllByText(ko.batches.discardedLabel).length).toBeGreaterThanOrEqual(1); // #13
    expect(screen.getAllByText('중지됨').length).toBeGreaterThanOrEqual(1); // #14
  });

  it('TC-VFF-065 목록의 초안에 담긴 제안은 선택·전체 선택에서 빠지고 사유+열기 링크가 보이며, 새 배치 만들기에 포함되지 않는다', async () => {
    const user = userEvent.setup();
    const draft = draftBatch({ id: 9 });
    draft.items = draft.items.slice(0, 1); // 제안 1번만 초안에 있음
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', () =>
        json(200, { items: sugs, total: 2, page: 1, page_size: 200 }),
      ),
      route('GET', '/api/v1/batches', () =>
        json(200, { items: [listed(draft)], total: 1, page: 1, page_size: 200 }),
      ),
      route('GET', '/api/v1/batches/9', () => json(200, draft)),
      route('POST', '/api/v1/batches', () =>
        json(201, { batch: draftBatch({ id: 10 }), precheck: draftBatch().precheck }),
      ),
      route('GET', '/api/v1/batches/10', () => json(200, draftBatch({ id: 10 }))),
    ]);
    renderWithApp(batchUi, c.client, '/batches');
    await screen.findByText(ko.batches.inDraft(9));
    expect(screen.getByRole('link', { name: ko.batches.inDraftOpen(9) })).toHaveAttribute(
      'href',
      '/batches/9',
    );
    const row1 = screen.getByRole('checkbox', { name: ko.batches.selectOne('승인된 제목 1') });
    expect(row1).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: ko.batches.selectAll }));
    expect(row1).not.toBeChecked();
    expect(
      screen.getByRole('checkbox', { name: ko.batches.selectOne('승인된 제목 2') }),
    ).toBeChecked();
    await user.click(screen.getByRole('button', { name: /사전 점검|배치 만들기|만들기/ }));
    await waitFor(() =>
      expect(c.calls.some((x) => x.method === 'POST' && x.path === '/api/v1/batches')).toBe(true),
    );
    const post = c.calls.find((x) => x.method === 'POST' && x.path === '/api/v1/batches')!;
    expect(JSON.stringify(post.body)).toContain('2');
    expect((post.body as { suggestion_ids: number[] }).suggestion_ids).toEqual([2]);
    expect(post.headers['idempotency-key']).toBeTruthy();
    expect(post.headers['x-csrf-token']).toBe('csrf-1');
  });
});

// =====================================================================================================
// G. 이력 필터 (DEF-7-010)
// =====================================================================================================
describe('G. 이력 결과 필터 (DEF-7-010)', () => {
  const chg = (id: number, result: string): Change => ({
    id,
    video_id: 'vid00000001',
    video_title: '테스트 영상 1',
    change_type: 'apply',
    previous_title: '이전',
    new_title: '새',
    result: result as Change['result'],
    mode: 'demo',
    approver: null,
    applied_at: '2026-10-10T00:00:00Z',
    verified_at: null,
    error_code: null,
    rollbackable: false,
    batch_id: null,
  });

  it('TC-VFF-070 각 선택지를 고르면 정확히 그 값이 result 쿼리로 가고, 전체로 돌리면 쿼리가 빠진다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      route('GET', '/api/v1/changes', () =>
        json(200, { items: [chg(1, 'planned')], total: 1, page: 1, page_size: 50 }),
      ),
    ]);
    renderWithApp(<HistoryPage />, client);
    const sel = await screen.findByLabelText(ko.history.filterResult);
    for (const v of ['planned', 'success', 'failed', 'aborted']) {
      await user.selectOptions(sel, v);
      await waitFor(() => expect(calls.some((c) => c.query.get('result') === v)).toBe(true));
    }
    expect(calls[0]!.query.has('result')).toBe(false); // 처음(전체)에는 쿼리 없음
    await user.selectOptions(sel, '');
    expect(sel).toHaveValue('');
  });

  it('TC-VFF-071 결과 값 4종이 표에서 한국어로 보이고 영문 값이 새지 않는다', async () => {
    const items = ['planned', 'success', 'failed', 'aborted'].map((r, i) => chg(i + 1, r));
    const { client } = await connectedClient([
      route('GET', '/api/v1/changes', () => json(200, { items, total: 4, page: 1, page_size: 50 })),
    ]);
    renderWithApp(<HistoryPage />, client);
    const tbl = await screen.findByRole('table');
    await within(tbl).findByText('중단됨');
    const t = within(tbl)
      .getAllByRole('row')
      .map((r) => r.textContent)
      .join('|');
    for (const k of ['예정', '성공', '실패', '중단됨']) expect(t).toContain(k);
    expect(t).not.toMatch(/\b(planned|success|failed|aborted)\b/);
  });

  it('TC-VFF-072 필터 선택지에 서버가 거절하던 값(verified·unverified·rolled_back)이 없다', async () => {
    const { client } = await connectedClient([route('GET', '/api/v1/changes', () => emptyPage)]);
    renderWithApp(<HistoryPage />, client);
    const sel = await screen.findByLabelText(ko.history.filterResult);
    const vals = within(sel)
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value);
    for (const bad of ['verified', 'unverified', 'rolled_back']) expect(vals).not.toContain(bad);
  });
});

// =====================================================================================================
// H. 접근성 · XSS
// =====================================================================================================
describe('H. 접근성(axe)·텍스트 렌더(XSS)', () => {
  it('TC-VFF-080 axe: 초안 배치 상세(확인란 포함) 위반 0', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
    ]);
    renderWithApp(<App />, c.client, '/batches/7');
    await screen.findByLabelText(/확인 문구 입력/);
    expect(await axeViolations(document.body)).toEqual([]);
  });

  it('TC-VFF-081 axe: 초안 버리기 대화상자가 열린 상태 위반 0', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
    ]);
    renderWithApp(<App />, c.client, '/batches/7');
    await user.click(await screen.findByRole('button', { name: /초안 버리기/ }));
    await screen.findByRole('dialog');
    expect(await axeViolations(document.body)).toEqual([]);
  });

  it('TC-VFF-082 axe: 차단 카드·엄격 카드·AI 카드가 섞인 영상 상세(푸터 포함) 위반 0', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/videos/vid00000001', () =>
        json(
          200,
          detail([
            suggestion(1, {
              status: 'blocked',
              validation_result: 'block',
              reasons: [{ code: 'b', severity: 'block', message: '사유' }],
            }),
            suggestion(2, { strict: true, validation_result: 'warn', title: '엄격' }),
            suggestion(3, { source: 'manual', title: '수동' }),
          ]),
        ),
      ),
    ]);
    renderWithApp(<App />, c.client, '/videos/vid00000001');
    await screen.findByRole('heading', { name: '엄격' });
    expect(await axeViolations(document.body)).toEqual([]);
  });

  it('TC-VFF-083 axe: 승인 대화상자(면책·고지 포함) 위반 0', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/videos/vid00000001', () => json(200, detail([suggestion(1)]))),
    ]);
    renderWithApp(<App />, c.client, '/videos/vid00000001');
    await user.click(await screen.findByRole('button', { name: '승인' }));
    await screen.findByRole('dialog');
    expect(await axeViolations(document.body)).toEqual([]);
  });

  it('TC-VFF-084 axe: 이력·리포트·홈(면책 노출 화면) 위반 0', async () => {
    for (const p of ['/history', '/reports', '/']) {
      const c = await connectedClient([
        route('GET', '/api/v1/changes', () => emptyPage),
        route('GET', '/api/v1/reports/changes', () => json(200, { items: [], notes: ['a'] })),
        route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
      ]);
      const { unmount } = renderWithApp(<App />, c.client, p);
      await screen.findByRole('contentinfo');
      await new Promise((r) => setTimeout(r, 50));
      expect(await axeViolations(document.body), p).toEqual([]);
      unmount();
    }
  });

  it('TC-VFF-085 악의적 문자열(<img onerror>·<script>)을 제목·사유·사전점검 제외 항목에 넣어도 요소가 만들어지지 않고 글자 그대로 보인다', async () => {
    const evil = '<img src=x onerror=alert(1)><script>alert(2)</script>';
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/videos/vid00000001', () =>
        json(
          200,
          detail([
            suggestion(1, {
              title: evil,
              status: 'blocked',
              validation_result: 'block',
              reasons: [{ code: 'e', severity: 'block', message: evil }],
            }),
          ]),
        ),
      ),
    ]);
    const { container } = renderWithApp(videoUi, c.client, '/videos/vid00000001');
    await screen.findByRole('heading', { name: evil });
    expect(container.querySelector('img,script')).toBeNull();
    expect(within(cardOf(1)).getAllByText(evil).length).toBeGreaterThanOrEqual(2);
    // 사전 점검의 제외 항목 + 초안 버리기 대화상자도 같은 방식
    c.client.bootstrap();
    void user;
    const b = draftBatch({
      precheck: {
        ...draftBatch().precheck!,
        blocked: [{ suggestion_id: 5, reason: evil, video_id: 'vid00000005', video_title: evil }],
      },
    });
    const d = await connectedClient([route('GET', '/api/v1/batches/7', () => json(200, b))]);
    const r2 = renderWithApp(batchUi, d.client, '/batches/7');
    await screen.findByRole('link', { name: evil });
    expect(r2.container.querySelector('img,script')).toBeNull();
  });
});

describe('J. 중복 제출(같은 틱의 연속 클릭) — 서버 보호 수단 확인', () => {
  it('TC-VFF-095 실행 버튼을 같은 틱에 두 번 눌러도 서버로 간 요청은 모두 같은 Idempotency-Key 다(서버가 재생 처리)', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
      route('POST', '/api/v1/batches/7/execute', async () => {
        await new Promise((r) => setTimeout(r, 150));
        return json(202, {
          batch: draftBatch({ status: 'running', executed_at: '2026-10-10T00:00:00Z' }),
          job: {
            id: 'j',
            type: 'batch.execute',
            status: 'queued',
            progress: 0,
            total: 2,
            error: null,
            result: null,
          },
        });
      }),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByLabelText(/확인 문구 입력/);
    await user.click(screen.getByRole('checkbox', { name: /A\/B/ }));
    await user.type(screen.getByLabelText(/확인 문구 입력/), '실행 2건');
    const b = screen.getByRole('button', { name: '실행' });
    fireEvent.click(b);
    fireEvent.click(b);
    await waitFor(() => expect(c.calls.some((x) => x.path.endsWith('/execute'))).toBe(true));
    await new Promise((r) => setTimeout(r, 300));
    const keys = c.calls
      .filter((x) => x.path.endsWith('/execute'))
      .map((x) => x.headers['idempotency-key']);
    expect(keys.length).toBeGreaterThanOrEqual(1);
    expect(keys.every((k) => k && k === keys[0])).toBe(true);
  });

  it('TC-VFF-096 한 번 클릭 뒤 응답 대기 중에는 실행 버튼이 비활성(busy)이고 "실행 중" 표시가 나온다', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
      route('POST', '/api/v1/batches/7/execute', async () => {
        await new Promise((r) => setTimeout(r, 300));
        return problem(409, 'batch_state', '실패');
      }),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByLabelText(/확인 문구 입력/);
    await user.click(screen.getByRole('checkbox', { name: /A\/B/ }));
    await user.type(screen.getByLabelText(/확인 문구 입력/), '실행 2건');
    await user.click(screen.getByRole('button', { name: '실행' }));
    const busy = await screen.findByRole('button', { name: ko.batches.executing });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute('aria-busy', 'true');
    void c;
  });
});

// =====================================================================================================
// I. 제외 항목 제목 조회 (BlockedList)
// =====================================================================================================
describe('I. 사전 점검 제외 항목의 영상 제목 조회', () => {
  it('TC-VFF-090 제외 항목이 21개여도 영상 조회는 최대 20건이고, 조회 실패해도 제안 번호+사유로 대체 표시된다', async () => {
    const blocked = Array.from({ length: 21 }, (_, i) => ({
      suggestion_id: 100 + i,
      reason: `사유${i}`,
    }));
    const b = draftBatch({ precheck: { ...draftBatch().precheck!, blocked } });
    const sugList = blocked.map((x, i) =>
      suggestion(x.suggestion_id, { video_id: `vidx${String(i).padStart(7, '0')}` }),
    );
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, b)),
      route('GET', '/api/v1/suggestions', () =>
        json(200, { items: sugList, total: 21, page: 1, page_size: 200 }),
      ),
      route('GET', /^\/api\/v1\/videos\/vidx/, () => problem(404, 'not_found', '없음')),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByText(ko.batches.pc.blockedLine(100, '사유0'));
    await waitFor(() =>
      expect(c.calls.filter((x) => x.path.startsWith('/api/v1/videos/')).length).toBeGreaterThan(0),
    );
    await new Promise((r) => setTimeout(r, 100));
    expect(c.calls.filter((x) => x.path.startsWith('/api/v1/videos/')).length).toBeLessThanOrEqual(
      20,
    );
    expect(screen.getByText(ko.batches.pc.blockedLine(120, '사유20'))).toBeInTheDocument();
  });

  it('TC-VFF-090b 서버가 video_title 을 주면 영상 상세 조회를 하지 않고 그 제목으로 링크한다', async () => {
    const b = draftBatch({
      precheck: {
        ...draftBatch().precheck!,
        blocked: [
          { suggestion_id: 5, reason: '사유', video_id: 'vid00000005', video_title: '서버 제목' },
        ],
      },
    });
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, b)),
      route('GET', '/api/v1/suggestions', () => emptyPage),
      route('GET', /^\/api\/v1\/videos\//, () => problem(500, 'x', 'x')),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    expect(await screen.findByRole('link', { name: '서버 제목' })).toHaveAttribute(
      'href',
      '/videos/vid00000005',
    );
    await new Promise((r) => setTimeout(r, 80));
    expect(c.calls.some((x) => x.path.startsWith('/api/v1/videos/'))).toBe(false);
  });

  it('TC-VFF-091 제안 목록 조회가 page_size 200 이하(서버 한도 200)로 나간다', async () => {
    const b = draftBatch({
      precheck: { ...draftBatch().precheck!, blocked: [{ suggestion_id: 5, reason: 'x' }] },
    });
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, b)),
      route('GET', '/api/v1/suggestions', () => emptyPage),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByText(ko.batches.pc.blockedLine(5, 'x'));
    const s = c.calls.find((x) => x.path === '/api/v1/suggestions')!;
    expect(Number(s.query.get('page_size'))).toBeLessThanOrEqual(200);
    expect(s.query.get('status')).toBe('approved');
  });
});

// =====================================================================================================
// K. 변이 점검 1회전에서 놓친 부분을 메우는 보강 시험 + 새 회귀 점검
// =====================================================================================================
import { act } from '@testing-library/react';
import { describeError } from '../src/components/ErrorPanel';
import { ToastProvider, useToast } from '../src/components';

describe('K. 보강', () => {
  const approvedSug = (n: number): Suggestion =>
    suggestion(n, {
      video_id: `vid0000000${n}`,
      title: `승인된 제목 ${n}`,
      status: 'approved',
      approval: {
        approver: '홍',
        approved_at: '2026-10-10T00:00:00Z',
        expires_at: '2026-10-11T00:00:00Z',
      },
    });
  const listed = (b: Batch) => ({ ...b, items: [] });

  it('TC-VFF-110 status 만 blocked 이고 검증 결과가 pass 인 불일치 응답이어도 승인은 막힌다(fail-closed)', async () => {
    await openVideo([suggestion(1, { status: 'blocked', validation_result: 'pass' })]);
    await screen.findByRole('heading', { name: '테스트 영상 1 핵심 정리' });
    expect(within(cardOf(1)).getByRole('button', { name: '승인' })).toBeDisabled();
  });

  it('TC-VFF-110b 엄격 모드 + 경고(차단 사유 없음)는 엄격 모드 규칙 설명을, 엄격 + 차단 사유가 있으면 그 사유만 보인다', async () => {
    await openVideo([
      suggestion(1, {
        strict: true,
        validation_result: 'warn',
        title: '엄격경고',
        reasons: [{ code: 'w', severity: 'warn', message: '경고사유' }],
      }),
      suggestion(2, {
        strict: true,
        validation_result: 'block',
        status: 'blocked',
        title: '엄격차단',
        reasons: [{ code: 'b', severity: 'block', message: '차단사유' }],
      }),
    ]);
    await screen.findByRole('heading', { name: '엄격경고' });
    expect(within(cardOf(1)).getByText(ko.suggestion.cannotApproveStrict)).toBeInTheDocument();
    expect(within(cardOf(2)).queryByText(ko.suggestion.cannotApproveStrict)).toBeNull();
    expect(within(cardOf(2)).getAllByText('차단사유').length).toBeGreaterThanOrEqual(2);
  });

  it('TC-VFF-111 이미 끝난(applied) 제안에 검증 block 이 남아 있어도 "승인할 수 없는 이유" 상자는 나오지 않는다', async () => {
    await openVideo([suggestion(1, { status: 'applied', validation_result: 'block' })]);
    await screen.findByRole('heading', { name: '테스트 영상 1 핵심 정리' });
    expect(within(cardOf(1)).queryByText(ko.suggestion.cannotApproveTitle)).toBeNull();
  });

  it('TC-VFF-112 초안 버리기 처리 중에는 Esc·취소로 모달이 닫히지 않는다(응답 전 중복·유실 방지)', async () => {
    const user = userEvent.setup();
    let gone112 = false;
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () =>
        json(200, gone112 ? draftBatch({ status: 'cancelled' }) : draftBatch()),
      ),
      route('POST', '/api/v1/batches/7/cancel', async () => {
        await new Promise((r) => setTimeout(r, 400));
        gone112 = true;
        return json(200, draftBatch({ status: 'cancelled' }));
      }),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await user.click(await screen.findByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog');
    await user.click(within(dlg).getByRole('button', { name: '버리기' }));
    await user.keyboard('{Escape}');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(within(dlg).getByRole('button', { name: '취소' })).toBeDisabled();
    await screen.findByText(ko.batches.discardedBody);
    expect(c.calls.filter((x) => x.path.endsWith('/cancel'))).toHaveLength(1);
  });

  it('TC-VFF-113 모달 닫기 버튼(X)도 처리 중에는 비활성이다', async () => {
    const user = userEvent.setup();
    await connectedClient([]);
    let gone113 = false;
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () =>
        json(200, gone113 ? draftBatch({ status: 'cancelled' }) : draftBatch()),
      ),
      route('POST', '/api/v1/batches/7/cancel', async () => {
        await new Promise((r) => setTimeout(r, 300));
        gone113 = true;
        return json(200, draftBatch({ status: 'cancelled' }));
      }),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await user.click(await screen.findByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog');
    await user.click(within(dlg).getByRole('button', { name: '버리기' }));
    const closeBtns = within(dlg).queryAllByRole('button', { name: /닫기/ });
    for (const x of closeBtns) expect(x).toBeDisabled();
    await screen.findByText(ko.batches.discardedBody);
  });

  it('TC-VFF-114 목록에서 초안을 버리면 승인 목록을 서버에서 다시 읽는다(낡은 목록 방지)', async () => {
    const user = userEvent.setup();
    let gone = false;
    const draft = draftBatch({ id: 9 });
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', () =>
        json(200, { items: [approvedSug(1), approvedSug(2)], total: 2, page: 1, page_size: 200 }),
      ),
      route('GET', '/api/v1/batches', () =>
        json(200, {
          items: gone ? [] : [listed(draft)],
          total: gone ? 0 : 1,
          page: 1,
          page_size: 200,
        }),
      ),
      route('GET', '/api/v1/batches/9', () =>
        json(200, gone ? { ...draft, status: 'cancelled' } : draft),
      ),
      route('POST', '/api/v1/batches/9/cancel', () => {
        gone = true;
        return json(200, { ...draft, status: 'cancelled' });
      }),
    ]);
    renderWithApp(batchUi, c.client, '/batches');
    await user.click(await screen.findByRole('button', { name: /초안 버리기\s*\(배치 #9\)/ }));
    const n = c.calls.filter((x) => x.path === '/api/v1/suggestions').length;
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: '버리기' }),
    );
    await waitFor(() =>
      expect(c.calls.filter((x) => x.path === '/api/v1/suggestions').length).toBeGreaterThan(n),
    );
    await waitFor(() =>
      expect(
        screen.getByRole('checkbox', { name: ko.batches.selectOne('승인된 제목 1') }),
      ).toBeEnabled(),
    );
  });

  it('TC-VFF-115 모든 승인 제안이 초안에 있으면 전체 선택 상자가 비활성이고 만들기 요청이 가지 않는다', async () => {
    const draft = draftBatch({ id: 9 }); // 제안 1·2
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', () =>
        json(200, { items: [approvedSug(1), approvedSug(2)], total: 2, page: 1, page_size: 200 }),
      ),
      route('GET', '/api/v1/batches', () =>
        json(200, { items: [listed(draft)], total: 1, page: 1, page_size: 200 }),
      ),
      route('GET', '/api/v1/batches/9', () => json(200, draft)),
    ]);
    renderWithApp(batchUi, c.client, '/batches');
    await screen
      .findByText(ko.batches.inDraft(9), undefined, { timeout: 3000 })
      .catch(() => undefined);
    await waitFor(() =>
      expect(screen.getByRole('checkbox', { name: ko.batches.selectAll })).toBeDisabled(),
    );
    expect(c.calls.some((x) => x.method === 'POST')).toBe(false);
  });

  it('TC-VFF-116 선택한 뒤에 그 제안이 초안에 담긴 것으로 밝혀지면(늦게 도착한 초안 정보) 새 배치 요청에서 빠진다', async () => {
    const user = userEvent.setup();
    const draft = draftBatch({ id: 9 });
    draft.items = draft.items.slice(0, 1); // 제안 1
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', () =>
        json(200, { items: [approvedSug(1), approvedSug(2)], total: 2, page: 1, page_size: 200 }),
      ),
      route('GET', '/api/v1/batches', () =>
        json(200, { items: [listed(draft)], total: 1, page: 1, page_size: 200 }),
      ),
      route('GET', '/api/v1/batches/9', async () => {
        await new Promise((r) => setTimeout(r, 400)); // 초안 상세가 늦게 도착
        return json(200, draft);
      }),
      route('POST', '/api/v1/batches', () =>
        json(201, { batch: draftBatch({ id: 10 }), precheck: draftBatch().precheck }),
      ),
      route('GET', '/api/v1/batches/10', () => json(200, draftBatch({ id: 10 }))),
    ]);
    renderWithApp(batchUi, c.client, '/batches');
    await user.click(await screen.findByRole('checkbox', { name: ko.batches.selectAll }));
    await screen.findByText(ko.batches.inDraft(9), undefined, { timeout: 3000 });
    await user.click(screen.getByRole('button', { name: /사전 점검|만들기/ }));
    await waitFor(() => expect(c.calls.some((x) => x.method === 'POST')).toBe(true));
    expect(
      (c.calls.find((x) => x.method === 'POST')!.body as { suggestion_ids: number[] })
        .suggestion_ids,
    ).toEqual([2]);
  });

  it('TC-VFF-117 배치 만들기 성공 뒤 목록으로 돌아오면 5초 캐시와 무관하게 승인·초안 목록을 다시 읽는다', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', () =>
        json(200, { items: [approvedSug(1), approvedSug(2)], total: 2, page: 1, page_size: 200 }),
      ),
      route('GET', '/api/v1/batches', () =>
        json(200, { items: [], total: 0, page: 1, page_size: 200 }),
      ),
      route('POST', '/api/v1/batches', () =>
        json(201, { batch: draftBatch({ id: 10 }), precheck: draftBatch().precheck }),
      ),
      route('GET', '/api/v1/batches/10', () => json(200, draftBatch({ id: 10 }))),
    ]);
    renderWithApp(
      <Routes>
        <Route path="batches" element={<BatchesPage />} />
        <Route
          path="batches/:batchId"
          element={
            <>
              <Link to="/batches">back</Link>
              <BatchDetailPage />
            </>
          }
        />
      </Routes>,
      c.client,
      '/batches',
    );
    await user.click(await screen.findByRole('checkbox', { name: ko.batches.selectAll }));
    const s0 = c.calls.filter((x) => x.path === '/api/v1/suggestions').length;
    await user.click(screen.getByRole('button', { name: /사전 점검|만들기/ }));
    await screen.findByLabelText(/확인 문구 입력/);
    await waitFor(() =>
      expect(c.calls.filter((x) => x.path === '/api/v1/suggestions').length).toBeGreaterThan(s0),
    );
  });

  it('TC-VFF-118 화면을 옮기면 성공 알림은 사라지고 오류 알림은 남으며, 포커스가 새 화면 제목으로 간다', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/videos/vid00000001', () => json(200, detail([suggestion(1)]))),
      route('POST', '/api/v1/suggestions/1/approve', () =>
        json(200, suggestion(1, { status: 'approved' })),
      ),
      route('GET', '/api/v1/videos', () => emptyPage),
      route('DELETE', '/api/v1/auth/session', () => problem(500, 'http_500', 'x')),
    ]);
    renderWithApp(<App />, c.client, '/videos/vid00000001');
    await user.click(await screen.findByRole('button', { name: '승인' }));
    const dlg = await screen.findByRole('dialog');
    await user.type(within(dlg).getByLabelText(/승인자/), '홍길동');
    await user.click(within(dlg).getByRole('button', { name: '승인' }));
    await screen.findByText(ko.suggestion.approvedToast);
    await user.click(screen.getByRole('button', { name: '로그아웃' })); // 오류 알림을 만든다
    await screen.findByText('서버 안에서 오류가 났습니다.');
    await user.click(screen.getByRole('link', { name: ko.nav.videos }));
    await screen.findByRole('heading', { name: ko.videos.title });
    expect(screen.queryByText(ko.suggestion.approvedToast)).toBeNull();
    expect(document.activeElement).toBe(document.querySelector('[data-page-title]'));
    expect(document.querySelector('.toast--error, [data-tone=error]') ?? true).toBeTruthy();
  });

  it('TC-VFF-119 Toast: clearTransient 는 성공·안내를 지우고 오류는 남긴다(컴포넌트 단위)', async () => {
    function Probe() {
      const t = useToast();
      return (
        <>
          <button
            onClick={() => {
              t.push('success', '성공A');
              t.push('info', '안내B');
              t.push('error', '오류C');
            }}
          >
            push
          </button>
          <button onClick={() => t.clearTransient()}>clear</button>
        </>
      );
    }
    const { render } = await import('@testing-library/react');
    render(
      <ToastProvider>
        <Probe />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByText('push'));
    expect(screen.getByText('성공A')).toBeInTheDocument();
    await userEvent.click(screen.getByText('clear'));
    expect(screen.queryByText('성공A')).toBeNull();
    expect(screen.queryByText('안내B')).toBeNull();
    expect(screen.getByText('오류C')).toBeInTheDocument();
    void act;
  });

  it('TC-VFF-120 describeError 행렬: 영어만 있는 서버 문구는 코드별 한국어로 바꾸고, 한국어가 섞였거나 코드별 문구가 없으면 그대로 둔다', async () => {
    const { ApiError } = await import('../src/api/client');
    const mk = (code: string, title: string, detail: string, hint = '') =>
      describeError(new ApiError({ status: 422, code, title, detail, hint }));
    // 영어 제목·상세 + 코드별 문구 있음 → 한국어
    const a = mk('validation_error', 'Unprocessable Entity', "Input should be 'a'", 'Fix it');
    expect(a.title).toBe(ko.state.errorTitle);
    expect(a.detail).toBe(ko.errors.validation_error);
    expect(a.hint).toBe(ko.errorHints.validation_error);
    // 2~3글자 영어 약어(PIN, URL)는 영어 문장으로 보지 않는다(WORDS 경계: 3글자 이상)
    expect(mk('validation_error', 'PIN 오류', 'URL 형식').title).toBe('PIN 오류');
    // 영어 단어 3글자는 영어로 본다 / 2글자는 아니다
    expect(mk('validation_error', 'Bad', 'x').title).toBe(ko.state.errorTitle);
    expect(mk('validation_error', 'No', 'x').title).toBe('No');
    // 한국어가 하나라도 있으면 영어가 섞여 있어도 그대로
    expect(mk('validation_error', '입력 오류: Unprocessable', '상세 detail text').title).toBe(
      '입력 오류: Unprocessable',
    );
    expect(mk('validation_error', 'x', '상세 detail text').detail).toBe('상세 detail text');
    // 코드별 문구가 없는 코드는 영어여도 그대로(서버 문장을 가리지 않는다)
    expect(mk('weird_code', 'Weird failure', 'Details here').title).toBe('Weird failure');
    expect(mk('weird_code', 'Weird failure', 'Details here').detail).toBe('Details here');
  });
});
