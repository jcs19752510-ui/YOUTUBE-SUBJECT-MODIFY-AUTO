import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { App } from './app/App';
import { BatchDetailPage } from './pages/BatchDetailPage';
import { VideoDetailPage } from './pages/VideoDetailPage';
import { dashboard, detail, draftBatch, suggestion, video } from './test/fixtures';
import {
  axeViolations,
  connectedClient,
  json,
  makeClient,
  renderWithApp,
  route,
  type Handler,
} from './test/utils';

const authed: Handler = route('GET', '/api/v1/auth/me', () =>
  json(200, { authenticated: true, pin_required: false, csrf_token: 'c' }),
);
const page = (items: unknown[]) =>
  json(200, { items, total: items.length, page: 1, page_size: 50 });

describe('접근성(axe) — 주요 화면', () => {
  it('TC-WF-086 홈에 접근성 위반이 없다', async () => {
    const { client } = makeClient([
      authed,
      route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
    ]);
    const { container } = renderWithApp(<App />, client);
    await screen.findByText('2 / 10건');
    expect(await axeViolations(container)).toEqual([]);
  });

  it('TC-WF-087 영상 목록에 접근성 위반이 없다', async () => {
    const { client } = makeClient([
      authed,
      route('GET', '/api/v1/videos', () =>
        page([video(1), video(2, { excluded: true, exclusion_reasons: ['비공개 영상'] })]),
      ),
    ]);
    const { container } = renderWithApp(<App />, client, '/videos');
    await screen.findByText('테스트 영상 1');
    expect(await axeViolations(container)).toEqual([]);
  });

  it('TC-WF-088 영상 상세(통과·경고·차단 카드)에 접근성 위반이 없다', async () => {
    const sugs = [
      suggestion(1),
      suggestion(2, {
        validation_result: 'warn',
        reasons: [{ code: 'r', severity: 'warn', message: '경고 사유' }],
      }),
      suggestion(3, {
        validation_result: 'block',
        reasons: [{ code: 'r', severity: 'block', message: '차단 사유' }],
      }),
    ];
    const c = await connectedClient([
      route('GET', '/api/v1/videos/vid00000001', () => json(200, detail(sugs))),
    ]);
    const { container } = renderWithApp(
      <Routes>
        <Route path="videos/:videoId" element={<VideoDetailPage />} />
      </Routes>,
      c.client,
      '/videos/vid00000001',
    );
    await screen.findByText('경고 사유');
    expect(await axeViolations(container)).toEqual([]);
  });

  it('TC-WF-089 배치 초안(사전 점검·확인 문구)에 접근성 위반이 없다', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
    ]);
    const { container } = renderWithApp(
      <Routes>
        <Route path="batches/:batchId" element={<BatchDetailPage />} />
      </Routes>,
      c.client,
      '/batches/7',
    );
    await screen.findByText('실행 확인');
    expect(await axeViolations(container)).toEqual([]);
  });

  it('TC-WF-090 이력·롤백 화면과 롤백 대화상자에 접근성 위반이 없다', async () => {
    const user = userEvent.setup();
    const ch = {
      id: 1,
      video_id: 'vid00000001',
      video_title: '영상',
      change_type: 'apply',
      previous_title: '이전',
      new_title: '새',
      result: 'success',
      mode: 'demo',
      approver: '홍',
      applied_at: '2026-10-09T00:00:00Z',
      verified_at: null,
      error_code: null,
      rollbackable: true,
      batch_id: 1,
    };
    const { client } = makeClient([authed, route('GET', '/api/v1/changes', () => page([ch]))]);
    const { container } = renderWithApp(<App />, client, '/history');
    await user.click(await screen.findByRole('button', { name: /롤백/ }));
    const dlg = await screen.findByRole('dialog');
    expect(await axeViolations(dlg)).toEqual([]);
    await user.keyboard('{Escape}');
    expect(await axeViolations(container)).toEqual([]);
  });

  it('TC-WF-091 성과 리포트에 접근성 위반이 없다', async () => {
    const { client } = makeClient([
      authed,
      route('GET', '/api/v1/reports/changes', () =>
        json(200, {
          notes: ['유의'],
          items: [
            {
              video_id: 'v2',
              title: '영상 B',
              status: 'ok',
              before: null,
              after: null,
              baseline_missing: false,
              reasons: [],
              notes: [],
              expected_after_date: null,
              metrics: [
                { key: 'views', label: '조회수', before: 100, after: 130, delta: 30, pct: 30 },
              ],
            },
          ],
        }),
      ),
    ]);
    const { container } = renderWithApp(<App />, client, '/reports');
    await screen.findByText('영상 B');
    expect(await axeViolations(container)).toEqual([]);
  });

  it('TC-WF-092 설정(안전 설정·PIN 탭)에 접근성 위반이 없다', async () => {
    const s = {
      daily_apply_cap: 10,
      suggestions_per_video: 3,
      tone: ['친근하게'],
      pin_enabled: false,
      mode: 'demo',
      read_only: { enable_live: false, live_allowlist: [], note: '' },
    };
    const user = userEvent.setup();
    const { client } = makeClient([authed, route('GET', '/api/v1/settings', () => json(200, s))]);
    const { container } = renderWithApp(<App />, client, '/settings');
    await screen.findByLabelText('하루 반영 건수 상한');
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole('tab', { name: 'PIN' }));
    await screen.findByLabelText('새 PIN');
    expect(await axeViolations(container)).toEqual([]);
  });

  it('TC-WF-093 PIN 입력 화면과 서버 연결 끊김 화면에 접근성 위반이 없다', async () => {
    const a = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, { authenticated: false, pin_required: true, csrf_token: null }),
      ),
    ]);
    const r1 = renderWithApp(<App />, a.client);
    await screen.findByRole('heading', { name: 'PIN 을 입력해 주세요' });
    expect(await axeViolations(r1.container)).toEqual([]);
    r1.unmount();
    const b = makeClient([
      () => {
        throw new TypeError('x');
      },
    ]);
    const r2 = renderWithApp(<App />, b.client);
    await screen.findByRole('heading', { name: '서버 연결이 끊겼습니다' });
    expect(await axeViolations(r2.container)).toEqual([]);
  });
});
