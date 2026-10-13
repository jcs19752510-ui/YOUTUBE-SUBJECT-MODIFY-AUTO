import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import type { SettingsData } from '../api/types';
import { draftBatch, suggestion, video } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { BatchDetailPage } from './BatchDetailPage';
import { BatchesPage } from './BatchesPage';
import { HistoryPage } from './HistoryPage';
import { ReportsPage } from './ReportsPage';
import { SettingsPage } from './SettingsPage';
import { VideosPage } from './VideosPage';

// F12 이슈 "A form field element should have an id or name attribute" 방지:
// 렌더된 모든 입력칸(input·select·textarea)에 id 또는 name 이 있고, id 가 겹치지 않아야 한다.
function audit(): string[] {
  const bad: string[] = [];
  const ids = new Map<string, number>();
  document.querySelectorAll('input, select, textarea').forEach((el) => {
    const id = el.getAttribute('id');
    const name = el.getAttribute('name');
    if (!id && !name)
      bad.push(
        `${el.tagName.toLowerCase()}[${el.getAttribute('type') ?? ''}] aria-label=${el.getAttribute('aria-label') ?? ''}`,
      );
    if (id) ids.set(id, (ids.get(id) ?? 0) + 1);
  });
  ids.forEach((n, id) => {
    if (n > 1) bad.push(`중복 id: ${id}`);
  });
  return bad;
}

const page = (items: unknown[]) =>
  json(200, { items, total: items.length, page: 1, page_size: 20 });
const approved = (n: number) =>
  suggestion(n, {
    video_id: `vid0000000${n}`,
    status: 'approved',
    approval: {
      approver: '홍',
      approved_at: '2026-10-10T00:00:00Z',
      expires_at: '2026-10-11T00:00:00Z',
    },
  });
const settings: SettingsData = {
  daily_apply_cap: 10,
  suggestions_per_video: 3,
  tone: ['친근하게'],
  pin_enabled: true,
  mode: 'demo',
  read_only: { enable_live: false, live_allowlist: [], note: '' },
};

describe('입력칸 id/name', () => {
  it('영상 목록: 모든 입력칸에 id 또는 name 이 있다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/videos', () => page([video(1), video(2)])),
    ]);
    renderWithApp(<VideosPage />, client, '/videos');
    await screen.findByText('테스트 영상 1');
    expect(document.querySelectorAll('input, select').length).toBeGreaterThan(5);
    expect(audit()).toEqual([]);
  });

  it('배치 목록: 모든 입력칸에 id 또는 name 이 있다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/suggestions', () => page([approved(1), approved(2)])),
      route('GET', '/api/v1/batches', () => page([])),
    ]);
    renderWithApp(<BatchesPage />, client, '/batches');
    await screen.findAllByRole('checkbox');
    expect(audit()).toEqual([]);
  });

  it('배치 상세(초안): 모든 입력칸에 id 또는 name 이 있다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
    ]);
    renderWithApp(
      <Routes>
        <Route path="batches/:batchId" element={<BatchDetailPage />} />
      </Routes>,
      client,
      '/batches/7',
    );
    await screen.findByText('실행 확인');
    expect(document.querySelectorAll('input').length).toBe(2);
    expect(audit()).toEqual([]);
  });

  it('이력·리포트·설정: 모든 입력칸에 id 또는 name 이 있다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/changes', () => page([])),
      route('GET', '/api/v1/reports/changes', () => json(200, { items: [], notes: [] })),
      route('GET', '/api/v1/settings', () => json(200, settings)),
    ]);
    const h = renderWithApp(<HistoryPage />, client, '/history');
    await screen.findByRole('combobox');
    expect(audit()).toEqual([]);
    h.unmount();
    const r = renderWithApp(<ReportsPage />, client, '/reports');
    await screen.findByRole('button', { name: 'CSV 내보내기' });
    expect(audit()).toEqual([]);
    r.unmount();
    renderWithApp(<SettingsPage />, client, '/settings');
    await screen.findByText(/상한/);
    expect(audit()).toEqual([]);
  });
});
