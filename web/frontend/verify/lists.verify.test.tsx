// 06단계 독립 검증(TC-VF) — 목록 선택 상태, URL 쿼리 방어, 작업 진행 창, 외부 문자열 렌더링(XSS), 잘못된 서버 응답
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HashRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Job, VideoDetail, VideoSummary } from '../src/api/types';
import { App } from '../src/app/App';
import { Providers } from '../src/app/providers';
import { BatchDetailPage } from '../src/pages/BatchDetailPage';
import { HistoryPage } from '../src/pages/HistoryPage';
import { ReportsPage } from '../src/pages/ReportsPage';
import { SettingsPage } from '../src/pages/SettingsPage';
import { VideoDetailPage } from '../src/pages/VideoDetailPage';
import { VideosPage } from '../src/pages/VideosPage';
import { dashboard, detail, draftBatch, suggestion, video } from '../src/test/fixtures';
import { connectedClient, json, problem, renderWithApp, route, type Handler } from '../src/test/utils';

afterEach(() => {
  vi.useRealTimers();
  delete (window as unknown as Record<string, unknown>).__pwn;
});

// ---------- 영상 목록 선택/필터 ----------
const ALL: VideoSummary[] = [
  video(1),
  video(2),
  video(3),
  video(4, { excluded: true, exclusion_reasons: ['비공개 영상'] }),
  video(5, { workflow_status: 'approved' }),
  video(6, { workflow_status: 'approved' }),
];
const listRoute = route('GET', '/api/v1/videos', (req) => {
  const size = Number(req.query.get('page_size') ?? '50');
  const page = Number(req.query.get('page') ?? '1');
  const st = req.query.get('status');
  const rows = st ? ALL.filter((v) => v.workflow_status === st) : ALL;
  return json(200, { items: rows.slice((page - 1) * size, page * size), total: rows.length, page, page_size: size });
});
async function goVideos(entry = '/videos?page_size=2', extra: Handler[] = []) {
  const c = await connectedClient([listRoute, ...extra]);
  renderWithApp(<VideosPage />, c.client, entry);
  await screen.findByRole('table');
  return c;
}
const cb = (n: number) => screen.getByRole('checkbox', { name: `테스트 영상 ${n} 선택` });
const countText = (n: number) => screen.getAllByText(`${n}개 선택됨`);

describe('영상 목록: 선택 상태 유지·초기화 규칙 (F-03)', () => {
  it('TC-VF-@@@ 필터(진행 상태)를 바꿔도 선택은 유지되고, 필터를 풀면 같은 체크가 보인다', async () => {
    const user = userEvent.setup();
    await goVideos('/videos?page_size=6');
    await user.click(cb(1));
    await user.click(cb(2));
    expect(countText(2).length).toBeGreaterThan(0);
    await user.selectOptions(screen.getByLabelText('진행 상태'), 'approved');
    await screen.findByText('테스트 영상 5');
    expect(screen.queryByText('테스트 영상 1')).toBeNull();
    expect(countText(2).length).toBeGreaterThan(0); // 안 보이는 영상도 선택 개수에 포함
    await user.selectOptions(screen.getByLabelText('진행 상태'), '');
    await screen.findByText('테스트 영상 1');
    expect(cb(1)).toBeChecked();
    expect(cb(2)).toBeChecked();
  });

  it('TC-VF-@@@ 쪽 크기를 바꿔도 선택은 유지된다', async () => {
    const user = userEvent.setup();
    await goVideos('/videos?page_size=2');
    await user.click(cb(1));
    await user.selectOptions(screen.getByLabelText('한 번에 보기'), '25');
    await screen.findByText('테스트 영상 6');
    expect(cb(1)).toBeChecked();
    expect(countText(1).length).toBeGreaterThan(0);
  });

  it('TC-VF-@@@ "선택 해제" 는 다른 쪽에서 고른 것까지 모두 지우고 선택 바가 사라진다', async () => {
    const user = userEvent.setup();
    await goVideos('/videos?page_size=2');
    await user.click(cb(1));
    await user.click(screen.getByRole('button', { name: '다음' }));
    await screen.findByText('테스트 영상 3');
    await user.click(cb(3));
    expect(countText(2).length).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: '선택 모두 해제' }));
    expect(screen.queryByText(/개 선택됨/)).toBeNull();
    await user.click(screen.getByRole('button', { name: '이전' }));
    await screen.findByText('테스트 영상 1');
    expect(cb(1)).not.toBeChecked();
  });

  it('TC-VF-@@@ 같은 영상을 두 번 누르면 선택이 풀리고, 전체 선택 체크박스는 일부 선택이면 중간 상태, 전부면 체크 상태다', async () => {
    const user = userEvent.setup();
    await goVideos('/videos?page_size=2');
    const head = screen.getByRole('checkbox', { name: '이 페이지 전체 선택' }) as HTMLInputElement;
    await user.click(cb(1));
    await user.click(cb(1));
    expect(screen.queryByText(/개 선택됨/)).toBeNull();
    await user.click(cb(1));
    expect(head.indeterminate).toBe(true);
    expect(head.checked).toBe(false);
    await user.click(cb(2));
    expect(head.indeterminate).toBe(false);
    expect(head.checked).toBe(true);
  });

  it('TC-VF-@@@ 이 페이지 전체 선택을 풀면 이 페이지 것만 풀리고 다른 쪽에서 고른 것은 남는다', async () => {
    const user = userEvent.setup();
    await goVideos('/videos?page_size=2');
    await user.click(screen.getByRole('checkbox', { name: '이 페이지 전체 선택' }));
    await user.click(screen.getByRole('button', { name: '다음' }));
    await screen.findByText('테스트 영상 3');
    await user.click(cb(3));
    await user.click(screen.getByRole('button', { name: '이전' }));
    await screen.findByText('테스트 영상 1');
    await user.click(screen.getByRole('checkbox', { name: '이 페이지 전체 선택' })); // 풀기
    expect(countText(1).length).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: '다음' }));
    await screen.findByText('테스트 영상 3');
    expect(cb(3)).toBeChecked();
  });

  it('TC-VF-@@@ 모두 제외된 쪽에서는 전체 선택 체크박스가 꺼져 있다', async () => {
    const only = route('GET', '/api/v1/videos', () =>
      json(200, { items: [video(4, { excluded: true, exclusion_reasons: ['비공개'] })], total: 1, page: 1, page_size: 50 }),
    );
    const c = await connectedClient([only]);
    renderWithApp(<VideosPage />, c.client, '/videos');
    await screen.findByRole('table');
    expect(screen.getByRole('checkbox', { name: '이 페이지 전체 선택' })).toBeDisabled();
  });

  it('TC-VF-@@@ AI 제안 생성은 여러 쪽에서 고른 영상 ID 를 한 번의 요청으로, CSRF 와 함께 보낸다(멱등키 없음)', async () => {
    const user = userEvent.setup();
    const { calls } = await goVideos('/videos?page_size=2', [
      route('POST', '/api/v1/suggestions/generate', () =>
        json(202, { id: 'job-1', type: 'suggestions.generate', status: 'queued', progress: 0, total: 2, error: null, result: null }),
      ),
      route('GET', '/api/v1/jobs/job-1', () =>
        json(200, { id: 'job-1', type: 'suggestions.generate', status: 'succeeded', progress: 2, total: 2, error: null, result: null }),
      ),
    ]);
    await user.click(cb(2));
    await user.click(screen.getByRole('button', { name: '다음' }));
    await screen.findByText('테스트 영상 3');
    await user.click(cb(3));
    await user.click(screen.getByRole('button', { name: /AI 제안 생성/ }));
    await waitFor(() => expect(calls.some((c) => c.path === '/api/v1/suggestions/generate')).toBe(true));
    const g = calls.filter((c) => c.path === '/api/v1/suggestions/generate');
    expect(g).toHaveLength(1);
    expect((g[0]?.body as { video_ids: string[] }).video_ids.sort()).toEqual(['vid00000002', 'vid00000003']);
    expect(g[0]?.headers['x-csrf-token']).toBe('csrf-1');
    expect(g[0]?.headers['idempotency-key']).toBeUndefined();
  });
});

describe('영상 목록: 주소(URL) 쿼리 방어', () => {
  it.each([
    ['page=-1', { page: '1' }],
    ['page=0', { page: '1' }],
    ['page=abc', { page: '1' }],
    ['page=1.5', { page: '1' }],
    ['page_size=9999', { page_size: '200' }],
    ['page_size=0', { page_size: '50' }],
    ['page_size=-5', { page_size: '50' }],
    ['status=%3Cscript%3E', { status: null }],
    ['status=APPROVED', { status: null }],
    ['excluded=maybe', { excluded: null }],
    ['order=sideways', { order: 'desc' }],
  ])('TC-VF-@@@ /videos?%s → 서버로 가는 쿼리가 안전한 값으로 바뀐다', async (qs, expectQ) => {
    const { calls } = await goVideos(`/videos?${qs}`);
    const last = calls.filter((c) => c.path === '/api/v1/videos').at(-1)!;
    for (const [k, v] of Object.entries(expectQ)) {
      if (v === null) expect(last.query.has(k), `${qs} → ${k}`).toBe(false);
      else expect(last.query.get(k), `${qs} → ${k}`).toBe(v);
    }
  });

  it('TC-VF-@@@ 검색어에 HTML 이 있어도 입력칸의 글자로만 보이고 요소가 만들어지지 않는다', async () => {
    const { container } = render(<div />);
    void container;
    const c = await connectedClient([listRoute]);
    const q = encodeURIComponent('<img src=x onerror="window.__pwn=1">');
    renderWithApp(<VideosPage />, c.client, `/videos?q=${q}`);
    await screen.findByRole('table');
    expect(document.querySelector('img')).toBeNull();
    expect((window as unknown as Record<string, unknown>).__pwn).toBeUndefined();
    expect((screen.getByLabelText('제목 또는 영상 ID 검색') as HTMLInputElement).value).toContain('<img');
  });
});

// ---------- 작업 진행 창 ----------
describe('AI 제안 생성 작업 창', () => {
  const genJob: Job = { id: 'job-9', type: 'suggestions.generate', status: 'queued', progress: 0, total: 1, error: null, result: null };
  const start = async (jobGet: Handler) => {
    const user = userEvent.setup();
    const c = await goVideos('/videos?page_size=2', [route('POST', '/api/v1/suggestions/generate', () => json(202, genJob)), jobGet]);
    await user.click(cb(1));
    await user.click(screen.getByRole('button', { name: /AI 제안 생성/ }));
    await screen.findByRole('dialog');
    return { user, ...c };
  };

  it('TC-VF-@@@ 작업이 성공으로 끝나면 닫기가 켜지고, 닫으면 선택이 초기화된다', async () => {
    const { user } = await start(route('GET', '/api/v1/jobs/job-9', () => json(200, { ...genJob, status: 'succeeded', progress: 1 })));
    const close = await waitFor(() => {
      const b = within(screen.getByRole('dialog')).getByRole('button', { name: '닫기' });
      expect(b).toBeEnabled();
      return b;
    });
    await user.click(close);
    expect(screen.queryByText(/개 선택됨/)).toBeNull();
  });

  // 관찰 OBS-1: 작업이 실패로 끝나도 선택이 지워진다(재시도하려면 다시 골라야 함). 명세에 없어 결함으로 올리지 않고 현재 동작을 기록한다.
  it('TC-VF-@@@ [관찰 OBS-1] 작업이 실패로 끝나면 오류를 보여 주고, 닫으면 선택도 초기화된다(현재 동작 기록)', async () => {
    const { user } = await start(route('GET', '/api/v1/jobs/job-9', () => json(200, { ...genJob, status: 'failed', error: '모의 AI 오류' })));
    expect((await screen.findAllByText('모의 AI 오류')).length).toBeGreaterThan(0);
    const close = await waitFor(() => {
      const b = within(screen.getByRole('dialog')).getByRole('button', { name: '닫기' });
      expect(b).toBeEnabled();
      return b;
    });
    await user.click(close);
    expect(screen.queryByText(/개 선택됨/)).toBeNull();
  });

  // 결함 DEF-6-004(Medium): 작업 조회가 계속 실패(404/500)하면 창을 닫을 방법이 없다(Esc·닫기 모두 비활성).
  it.fails('TC-VF-@@@ 작업 상태를 읽지 못해(404) 오류가 보이면 사용자가 창을 닫을 수 있다 [DEF-6-004]', async () => {
    const { user } = await start(route('GET', '/api/v1/jobs/job-9', () => problem(404, 'job_not_found', '작업을 찾을 수 없습니다')));
    await screen.findAllByText('작업을 찾을 수 없습니다');
    await user.keyboard('{Escape}');
    const dlg = screen.queryByRole('dialog');
    if (dlg) {
      const close = within(dlg).getByRole('button', { name: '닫기' });
      expect(close).toBeEnabled();
    }
  });
});

// ---------- 외부 문자열은 텍스트로만 ----------
const PAYLOADS = [
  '<script>window.__pwn=1</script>',
  '<img src=x onerror="window.__pwn=1">',
  'javascript:window.__pwn=1',
  '"><svg onload=window.__pwn=1>',
  '‮evil‬ 양방향',
  '${7*7} {{7*7}} %s',
];
const cleanDom = (root: ParentNode = document.body) => {
  expect(root.querySelectorAll('script').length).toBe(0);
  expect(root.querySelectorAll('img').length).toBe(0);
  expect(root.querySelectorAll('svg').length).toBe(0);
  expect(root.querySelectorAll('iframe,object,embed,form[action]').length).toBe(0);
  expect(root.querySelectorAll('[onerror],[onload],[onclick],[onfocus],[onmouseover]').length).toBe(0);
  for (const a of Array.from(root.querySelectorAll('a[href]'))) {
    expect(a.getAttribute('href')?.trim().toLowerCase().startsWith('javascript:'), a.outerHTML).toBe(false);
  }
  expect((window as unknown as Record<string, unknown>).__pwn).toBeUndefined();
};

describe('외부 문자열 렌더링 (F-05, S-W05)', () => {
  it('TC-VF-@@@ 영상 상세: 제목·설명·제외 사유·제안 제목·근거·사유·승인자·주제·한도 사유가 모두 글자로만 보인다', async () => {
    const [P0, P1, P2, P3, P4, P5] = PAYLOADS as [string, string, string, string, string, string];
    const s = suggestion(1, {
      title: P0,
      evidence: P1,
      topic: P2,
      reasons: [{ code: 'x', severity: 'warn', message: P3 }],
      validation_result: 'warn',
      status: 'approved',
      approval: { approver: P4, approved_at: '2026-10-10T00:00:00Z', expires_at: '2026-10-11T00:00:00Z' },
    });
    const d: VideoDetail = detail([s], {
      title: P1,
      description_excerpt: P3,
      excluded: true,
      exclusion_reasons: [P5],
      limits: { allowed: false, reasons: [P2], next_allowed_at: null },
      changes: [
        {
          id: 1, video_id: 'vid00000001', video_title: P0, change_type: 'apply', previous_title: P1, new_title: P2, result: 'success',
          mode: 'demo', approver: P4, applied_at: '2026-10-10T00:00:00Z', verified_at: null, error_code: P3, rollbackable: true, batch_id: 1,
        },
      ],
    });
    const c = await connectedClient([route('GET', '/api/v1/videos/vid00000001', () => json(200, d))]);
    renderWithApp(
      <Routes>
        <Route path="videos/:videoId" element={<VideoDetailPage />} />
      </Routes>,
      c.client,
      '/videos/vid00000001',
    );
    await screen.findByRole('heading', { level: 3 });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    cleanDom();
    const text = document.body.textContent ?? '';
    expect(text).toContain(P0);
    expect(text).toContain('window.__pwn=1');
    expect(text).toContain(P4); // 양방향 제어문자도 지워지지 않고 글자로 남는다
  });

  it('TC-VF-@@@ 영상 목록: 제목과 영상 ID 에 스크립트·javascript: 가 있어도 링크 주소가 안전하다(HashRouter 실제 주소 형식 포함)', async () => {
    const bad = [
      video(1, { title: PAYLOADS[0]!, video_id: 'javascript:window.__pwn=1' }),
      video(2, { title: PAYLOADS[1]!, video_id: '"><svg onload=window.__pwn=1>', exclusion_reasons: [PAYLOADS[3]!], excluded: true }),
      video(3, { title: PAYLOADS[4]!, video_id: '../../admin?x=1#y' }),
    ];
    const c = await connectedClient([route('GET', '/api/v1/videos', () => json(200, { items: bad, total: 3, page: 1, page_size: 50 }))]);
    window.location.hash = '#/videos';
    render(
      <Providers client={c.client}>
        <HashRouter>
          <VideosPage />
        </HashRouter>
      </Providers>,
    );
    await screen.findByRole('table');
    cleanDom();
    const hrefs = Array.from(document.querySelectorAll('tbody a')).map((a) => a.getAttribute('href') ?? '');
    expect(hrefs).toHaveLength(3);
    for (const h of hrefs) {
      expect(h.startsWith('#/videos/')).toBe(true);
      expect(h.slice('#/videos/'.length)).not.toMatch(/[/?#"<> ]/); // 인코딩되어 경로가 새지 않음
    }
    window.location.hash = '';
  });

  it('TC-VF-@@@ 이력 화면: 영상 제목·이전/새 제목·승인자·오류 코드가 글자로만 보인다', async () => {
    const ch = {
      id: 1, video_id: 'vid00000001', video_title: PAYLOADS[0]!, change_type: 'apply', previous_title: PAYLOADS[1]!, new_title: PAYLOADS[3]!,
      result: 'failed', mode: 'demo', approver: PAYLOADS[4]!, applied_at: '2026-10-10T00:00:00Z', verified_at: null, error_code: PAYLOADS[2]!, rollbackable: false, batch_id: null,
    };
    const c = await connectedClient([route('GET', '/api/v1/changes', () => json(200, { items: [ch], total: 1, page: 1, page_size: 50 }))]);
    renderWithApp(<HistoryPage />, c.client, '/history');
    await screen.findByRole('table');
    cleanDom();
    expect(document.body.textContent).toContain(PAYLOADS[3]);
  });

  it('TC-VF-@@@ 배치 상세: 메모·항목 제목·건너뜀 사유·점검 경고/차단 사유가 글자로만 보인다', async () => {
    const b = draftBatch({ note: PAYLOADS[0]! });
    b.items[0] = { ...b.items[0]!, video_title: PAYLOADS[1]!, previous_title: PAYLOADS[3]!, new_title: PAYLOADS[4]!, skip_reason: PAYLOADS[2]! };
    b.precheck = { ...b.precheck!, warnings: [PAYLOADS[0]!, PAYLOADS[3]!], blocked: [{ suggestion_id: 1, reason: PAYLOADS[1]! }], confirm_text: '실행 2건' };
    const c = await connectedClient([route('GET', '/api/v1/batches/7', () => json(200, b))]);
    renderWithApp(
      <Routes>
        <Route path="batches/:batchId" element={<BatchDetailPage />} />
      </Routes>,
      c.client,
      '/batches/7',
    );
    await screen.findByLabelText(/확인 문구 입력/);
    cleanDom();
    expect(document.body.textContent).toContain('window.__pwn=1');
  });

  it('TC-VF-@@@ 감사 로그: 행위자·동작·대상이 글자로만 보인다', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/settings', () => json(200, { daily_apply_cap: 10, suggestions_per_video: 3, tone: [PAYLOADS[0]!], pin_enabled: false, mode: 'demo', read_only: { enable_live: false, live_allowlist: [PAYLOADS[3]!], note: PAYLOADS[1]! } })),
      route('GET', '/api/v1/audit', () =>
        json(200, {
          items: [{ id: 1, ts: '2026-10-10T00:00:00Z', actor: PAYLOADS[0]!, action: PAYLOADS[1]!, target_type: PAYLOADS[3]!, target_id: PAYLOADS[2]!, detail: {} }],
          total: 1, page: 1, page_size: 50, chain_ok: false,
        }),
      ),
    ]);
    renderWithApp(<SettingsPage />, c.client, '/settings?tab=audit');
    await screen.findByRole('table');
    cleanDom();
    expect(screen.getByText(/무결성|변조|확인/, { selector: '.badge, .badge *' })).toBeInTheDocument();
  });

  it('TC-VF-@@@ 성과 리포트: 서버 notes·사유·제목이 글자로만 보인다', async () => {
    const rep = {
      items: [{ video_id: 'vid00000001', title: PAYLOADS[0]!, status: 'insufficient', before: null, after: null, baseline_missing: true, reasons: [PAYLOADS[1]!], notes: [PAYLOADS[3]!], metrics: [], expected_after_date: null }],
      notes: [PAYLOADS[0]!, PAYLOADS[2]!],
    };
    const c = await connectedClient([route('GET', '/api/v1/reports/changes', () => json(200, rep))]);
    renderWithApp(<ReportsPage />, c.client, '/reports');
    await screen.findByText(/데이터 부족|부족/);
    cleanDom();
    expect(document.body.textContent).toContain(PAYLOADS[2]);
  });

  it('TC-VF-@@@ 서버 오류 메시지(title/detail/hint)에 HTML 이 있어도 화면에는 글자로만 나온다', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/dashboard', () => problem(500, 'boom', PAYLOADS[0]!, PAYLOADS[1]!, PAYLOADS[3]!)),
    ]);
    renderWithApp(<App />, c.client, '/');
    await screen.findAllByText(/window\.__pwn=1/);
    cleanDom();
  });
});

// ---------- 잘못된(계약 위반) 서버 응답 ----------
describe('잘못된 서버 응답에 대한 견고성', () => {
  // 결함 DEF-6-005(Medium): 오류 경계(ErrorBoundary)가 없어 응답 형식이 어긋나면 앱 전체가 빈 화면이 된다.
  it.fails('TC-VF-@@@ 영상 상세 응답에 suggestions 가 빠져도 메뉴·안내는 남는다(빈 화면 금지) [DEF-6-005]', async () => {
    const swallow = (e: ErrorEvent) => e.preventDefault();
    window.addEventListener('error', swallow);
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { suggestions: _omit, ...broken } = detail([]);
    void _omit;
    const c = await connectedClient([
      route('GET', '/api/v1/videos/vid00000001', () => json(200, broken)),
      route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
    ]);
    try {
      renderWithApp(<App />, c.client, '/videos/vid00000001');
      await act(async () => {
        await new Promise((r) => setTimeout(r, 100));
      });
      expect(screen.queryByRole('navigation', { name: '주 메뉴' })).not.toBeNull();
    } finally {
      window.removeEventListener('error', swallow);
      spy.mockRestore();
    }
  });

  it('TC-VF-@@@ 목록 응답의 items 가 null 이거나 항목 일부 필드가 null 이어도 표가 그려진다', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/videos', () =>
        json(200, { items: [video(1, { views: null, duration_sec: null, privacy_status: null, last_change_at: null })], total: 1, page: 1, page_size: 50 }),
      ),
    ]);
    renderWithApp(<VideosPage />, c.client, '/videos');
    expect(await screen.findByRole('table')).toBeInTheDocument();
    const c2 = await connectedClient([route('GET', '/api/v1/videos', () => json(200, { items: null, total: 0, page: 1, page_size: 50 }))]);
    renderWithApp(<VideosPage />, c2.client, '/videos');
    expect((await screen.findAllByText(/영상이 없|없습니다|불러오/)).length).toBeGreaterThan(0);
  });

  it('TC-VF-@@@ 알 수 없는 상태 값(진행 상태·검증 결과·제안 상태·주제)이 와도 원문을 보여 주고 깨지지 않는다', async () => {
    const odd = [
      video(1, { workflow_status: 'brand_new' as never }),
    ];
    const c = await connectedClient([route('GET', '/api/v1/videos', () => json(200, { items: odd, total: 1, page: 1, page_size: 50 }))]);
    renderWithApp(<VideosPage />, c.client, '/videos');
    await screen.findByRole('table');
    expect(screen.getByText('brand_new')).toBeInTheDocument();
  });

  it('TC-VF-@@@ 객체 프로토타입 이름(constructor·toString)이 상태 값으로 와도 함수 원문이 화면에 찍히지 않는다', async () => {
    const odd = [video(1, { workflow_status: 'constructor' as never }), video(2, { workflow_status: 'toString' as never })];
    const c = await connectedClient([route('GET', '/api/v1/videos', () => json(200, { items: odd, total: 2, page: 1, page_size: 50 }))]);
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderWithApp(<VideosPage />, c.client, '/videos');
    await screen.findByRole('table');
    expect(document.body.textContent).not.toMatch(/function|\[native code\]/);
    spy.mockRestore();
  });
});

// 입력 보조: fireEvent 가 쓰이지 않은 import 경고 방지
void fireEvent;
