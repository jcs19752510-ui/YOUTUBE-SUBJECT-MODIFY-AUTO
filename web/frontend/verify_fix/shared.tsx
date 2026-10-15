// 06단계 독립 검증(W-FIX-FE, TC-VWF) 공용 도우미 — 제품 소스는 건드리지 않는다.
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import type { Change, Suggestion } from '../src/api/types';
import { BatchDetailPage } from '../src/pages/BatchDetailPage';
import { BatchesPage } from '../src/pages/BatchesPage';
import { VideoDetailPage } from '../src/pages/VideoDetailPage';
import { detail, draftBatch, suggestion } from '../src/test/fixtures';
import { connectedClient, json, renderWithApp, route, type Handler } from '../src/test/utils';

export const REPO = resolve(process.cwd(), '..', '..');
export const readRepo = (p: string) => readFileSync(join(REPO, p), 'utf8');

/** 기획이 정한 면책 문장(서버 notices.py · CLI ui.py 와 같아야 한다). 시험이 파일에서 다시 읽어 대조한다. */
export const DISCLAIMER_LITERAL =
  '이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.';

export const page = (items: unknown[]) =>
  json(200, { items, total: items.length, page: 1, page_size: 20 });

export const videoUi = (
  <Routes>
    <Route path="videos/:videoId" element={<VideoDetailPage />} />
  </Routes>
);
export const batchUi = (
  <Routes>
    <Route path="batches" element={<BatchesPage />} />
    <Route path="batches/:batchId" element={<BatchDetailPage />} />
  </Routes>
);

export async function openVideo(suggestions: Suggestion[], extra: Handler[] = []) {
  const c = await connectedClient([
    route('GET', '/api/v1/videos/vid00000001', () => json(200, detail(suggestions))),
    route('PATCH', /^\/api\/v1\/suggestions\/\d+$/, (r) =>
      json(200, suggestion(1, { title: (r.body as { title: string }).title })),
    ),
    route('POST', /^\/api\/v1\/suggestions\/\d+\/reject$/, () =>
      json(200, suggestion(1, { status: 'rejected' })),
    ),
    ...extra,
  ]);
  const r = renderWithApp(videoUi, c.client, '/videos/vid00000001');
  return { ...c, ...r };
}

export const cardOf = (id: number) =>
  document.querySelector<HTMLElement>(`#sg-${id}`)!.closest('article') as HTMLElement;

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export const execOk = () =>
  json(202, {
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

export async function openBatch(
  extra: Handler[] = [],
  batch = draftBatch(),
  entry: string = '/batches/7',
) {
  const c = await connectedClient([
    route('GET', '/api/v1/batches/7', () => json(200, batch)),
    ...extra,
  ]);
  const r = renderWithApp(batchUi, c.client, entry);
  return { ...c, ...r };
}

export const abBox = () => screen.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ });

export const chg = (id: number, over: Partial<Change> = {}): Change => ({
  id,
  video_id: 'vid00000001',
  video_title: '테스트 영상 1',
  change_type: 'apply',
  previous_title: '이전',
  new_title: '새',
  result: 'success',
  mode: 'demo',
  approver: null,
  applied_at: '2026-10-10T00:00:00Z',
  verified_at: null,
  error_code: null,
  rollbackable: false,
  batch_id: null,
  ...over,
});

export const settingsBody = (cap = 10) => ({
  daily_apply_cap: cap,
  suggestions_per_video: 3,
  tone: [],
  pin_enabled: false,
  mode: 'demo',
  read_only: { enable_live: false, live_allowlist: [], note: '' },
});

export const HOSTILE = {
  script: '<script>window.__vwf=1</script><img src=x onerror="window.__vwf=2">',
  bidi: '진짜‮제목⁦숨김⁩',
  js: 'javascript:alert(1)',
};
