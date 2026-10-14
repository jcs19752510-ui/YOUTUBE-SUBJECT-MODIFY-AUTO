import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { connectedClient, json, renderWithApp, route, type Req } from '../test/utils';
import { ReportsPage } from './ReportsPage';

const rep = (vid: string, title: string, kind: 'long' | 'short' | null) => ({
  video_id: vid, video_kind: kind, title, status: 'no_change', label: null, baseline_missing: false, reasons: [], notes: [], changes: [],
  target: null, before: null, after: null, metrics: [], expected_after_date: null,
});
const all = { items: [rep('fakeVid0001', '긴 영상 하나', 'long'), rep('fakeVid0002', '쇼츠 영상 둘', 'short'), rep('fakeVid0003', '길이 모르는 영상', null)], notes: [] };

describe('성과 리포트 영상 구분(롱폼/쇼츠) 조회·표시 (2026-10-14)', () => {
  it('TC-FE-RK-001 영상 카드 옆에 롱폼/쇼츠 배지가 보이고 길이 불명은 배지가 없다', async () => {
    const { client } = await connectedClient([route('GET', '/api/v1/reports/changes', () => json(200, all))]);
    renderWithApp(<ReportsPage />, client);
    const longCard = (await screen.findByText('긴 영상 하나')).closest('section, article, div')!;
    expect(longCard.parentElement!.textContent).toContain('롱폼');
    expect(screen.getAllByText('쇼츠').length).toBeGreaterThan(0);
    expect(screen.getAllByText('롱폼').length).toBe(2); // 선택 상자 옵션 1 + 배지 1
  });

  it('TC-FE-RK-002 구분 선택이 조회와 CSV 내보내기에 kind 로 전달된다', async () => {
    const user = userEvent.setup();
    const seen: Req[] = [];
    const csv: Req[] = [];
    const { client } = await connectedClient([
      route('GET', '/api/v1/reports/changes', (r) => {
        seen.push(r);
        return json(200, all);
      }),
      route('GET', '/api/v1/reports/export.csv', (r) => {
        csv.push(r);
        return new Response('a', { status: 200, headers: { 'Content-Type': 'text/csv' } });
      }),
    ]);
    URL.createObjectURL = () => 'blob:x';
    URL.revokeObjectURL = () => undefined;
    renderWithApp(<ReportsPage />, client);
    await screen.findByText('긴 영상 하나');
    const sel = screen.getByRole('combobox', { name: '영상 구분' });
    expect(sel).toHaveValue('');
    expect(seen.at(-1)!.query.get('kind')).toBeNull();
    await user.selectOptions(sel, 'short');
    await waitFor(() => expect(seen.at(-1)!.query.get('kind')).toBe('short'));
    expect(seen.at(-1)!.query.has('date_from')).toBe(true);
    await user.click(await screen.findByRole('button', { name: 'CSV 내보내기' }));
    await waitFor(() => expect(csv.length).toBe(1));
    expect(csv[0]!.query.get('kind')).toBe('short');
    expect(csv[0]!.query.has('date_from')).toBe(true);
  });

  it('TC-FE-RK-003 구분을 고르고 0건이면 기간 안내 대신 조건 안내가 나온다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([
      route('GET', '/api/v1/reports/changes', (r) => (r.query.get('kind') ? json(200, { items: [], notes: [] }) : json(200, all))),
    ]);
    renderWithApp(<ReportsPage />, client);
    await screen.findByText('긴 영상 하나');
    await user.selectOptions(screen.getByRole('combobox', { name: '영상 구분' }), 'long');
    await waitFor(() => expect(screen.queryByText('긴 영상 하나')).toBeNull());
    expect(await screen.findByText('비교할 리포트가 없습니다')).toBeInTheDocument();
    expect(screen.queryByText(/\[전체 기간\]을 눌러 보세요/)).toBeNull();
  });
});
