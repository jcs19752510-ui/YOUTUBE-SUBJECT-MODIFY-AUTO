import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { draftBatch } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { BatchDetailPage } from './BatchDetailPage';
import { BatchesPage } from './BatchesPage';

const sugEmpty = route('GET', '/api/v1/suggestions', () =>
  json(200, { items: [], total: 0, page: 1, page_size: 200 }),
);
const mk = (id: number, kc: { long: number; short: number; unknown: number }) =>
  draftBatch({ id, status: 'done', kind_counts: kc, items: [] });
const list = route('GET', '/api/v1/batches', () =>
  json(200, {
    items: [mk(11, { long: 2, short: 1, unknown: 0 }), mk(12, { long: 1, short: 0, unknown: 3 })],
    total: 2,
    page: 1,
    page_size: 20,
  }),
);
const listCalls = (calls: { method: string; path: string; query: URLSearchParams }[]) =>
  calls.filter((c) => c.method === 'GET' && c.path === '/api/v1/batches' && c.query.get('page_size') === '20');

describe('배치 영상 구분(롱폼/쇼츠)', () => {
  it('TC-FE-BK-001 목록에 "구분" 열과 롱폼·쇼츠 개수가 보이고, 불명이 있으면 같이 보인다', async () => {
    const { client } = await connectedClient([sugEmpty, list]);
    renderWithApp(<BatchesPage />, client, '/batches');
    await screen.findByText('#11');
    expect(screen.getByRole('columnheader', { name: '구분' })).toBeInTheDocument();
    expect(within(screen.getByText('#11').closest('tr')!).getByText('롱폼 2 · 쇼츠 1')).toBeInTheDocument();
    expect(within(screen.getByText('#12').closest('tr')!).getByText(/롱폼 1 · 쇼츠 0 · 불명 3/)).toBeInTheDocument();
  });

  it('TC-FE-BK-002 구분 선택 상자는 kind 를 요청에 싣고 1쪽으로 가며 전체로 돌리면 뺀다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([sugEmpty, list]);
    renderWithApp(<BatchesPage />, client, '/batches');
    await screen.findByText('#11');
    const sel = screen.getByRole('combobox', { name: '영상 구분' });
    expect(sel).toHaveValue('');
    expect(listCalls(calls).at(-1)?.query.get('kind')).toBeNull();
    await user.selectOptions(sel, 'short');
    await waitFor(() => expect(listCalls(calls).at(-1)?.query.get('kind')).toBe('short'));
    expect(listCalls(calls).at(-1)?.query.get('page')).toBe('1');
    expect(listCalls(calls).at(-1)?.query.get('date_from')).toBeTruthy(); // 기간과 함께 간다
    await user.selectOptions(sel, '');
    await waitFor(() => expect(sel).toHaveValue(''));
  });

  it('TC-FE-BK-003 구분 조건으로 0건이면 "처음부터 없음"이 아니라 조건 안내를 보인다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([
      sugEmpty,
      route('GET', '/api/v1/batches', ({ query }) =>
        json(200, {
          items: query.get('kind') && query.get('page_size') === '20' ? [] : [mk(11, { long: 1, short: 0, unknown: 0 })],
          total: 0,
          page: 1,
          page_size: 20,
        }),
      ),
    ]);
    renderWithApp(<BatchesPage />, client, '/batches');
    await screen.findByText('#11');
    await user.selectOptions(screen.getByRole('combobox', { name: '영상 구분' }), 'short');
    await waitFor(() => expect(screen.queryByText('#11')).toBeNull());
    expect(screen.queryByText('아직 실행한 배치가 없습니다.')).toBeNull();
    expect(screen.getByText(/선택한 기간에 해당하는 항목이 없습니다/)).toBeInTheDocument();
  });

  it('TC-FE-BK-004 배치 상세 항목 표에 구분 열이 있고 항목마다 롱폼/쇼츠/불명이 보인다', async () => {
    const b = draftBatch();
    const items = [
      { ...b.items[0]!, video_kind: 'long' as const },
      { ...b.items[1]!, video_kind: 'short' as const },
      { ...b.items[1]!, id: 3, seq: 3, video_title: '길이 모름', video_kind: null },
    ];
    const { client } = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, { ...b, items })),
    ]);
    renderWithApp(
      <Routes>
        <Route path="batches/:batchId" element={<BatchDetailPage />} />
      </Routes>,
      client,
      '/batches/7',
    );
    await screen.findByText('테스트 영상 1');
    expect(screen.getAllByRole('columnheader', { name: '구분' }).length).toBeGreaterThan(0);
    const row = (t: string) => screen.getByText(t).closest('tr')!;
    expect(within(row('테스트 영상 1')).getByText('롱폼')).toBeInTheDocument();
    expect(within(row('테스트 영상 2')).getByText('쇼츠')).toBeInTheDocument();
    const unk = row('길이 모름');
    expect(within(unk).queryByText('롱폼')).toBeNull();
    expect(within(unk).queryByText('쇼츠')).toBeNull();
  });
});
