import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { HistoryPage } from './HistoryPage';

const row = (id: number, vid: string, title: string, kind: 'long' | 'short' | null) => ({
  id, video_id: vid, video_title: title, video_kind: kind, change_type: 'apply', previous_title: '이전', new_title: `새 ${title}`,
  result: 'success', mode: 'demo', approver: '홍', applied_at: '2026-10-14T01:00:00Z', verified_at: null, error_code: null, rollbackable: false, batch_id: 1,
});
const items = [row(1, 'fakeVid0001', '긴 영상 하나', 'long'), row(2, 'fakeVid0002', '쇼츠 영상 둘', 'short'), row(3, 'fakeVid0003', '길이 모르는 영상', null)];
const okRoute = route('GET', '/api/v1/changes', () => json(200, { items, total: 3, page: 1, page_size: 50 }));
const lastQuery = (calls: { path: string; query: URLSearchParams }[]) => calls.filter((c) => c.path === '/api/v1/changes').at(-1)?.query;

describe('이력 영상 구분(롱폼/쇼츠) 조회·표시 (2026-10-14)', () => {
  it('TC-FE-HK-001 표에 "영상 구분" 열과 롱폼·쇼츠·길이 불명(-)이 표시된다', async () => {
    const { client } = await connectedClient([okRoute]);
    renderWithApp(<HistoryPage />, client, '/history');
    await screen.findByText('긴 영상 하나');
    expect(screen.getByRole('columnheader', { name: '영상 구분' })).toBeInTheDocument();
    const rowOf = (t: string) => screen.getByText(t).closest('tr')!;
    expect(within(rowOf('긴 영상 하나')).getByText('롱폼')).toBeInTheDocument();
    expect(within(rowOf('쇼츠 영상 둘')).getByText('쇼츠')).toBeInTheDocument();
    expect(within(rowOf('길이 모르는 영상')).queryByText('롱폼')).toBeNull();
    expect(within(rowOf('길이 모르는 영상')).queryByText('쇼츠')).toBeNull();
  });

  it('TC-FE-HK-002 구분 선택이 kind 쿼리로 가고 1쪽으로 돌아가며 전체는 kind 를 뺀다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([okRoute]);
    renderWithApp(<HistoryPage />, client, '/history');
    await screen.findByText('긴 영상 하나');
    const sel = screen.getByRole('combobox', { name: '영상 구분' });
    expect(sel).toHaveValue('');
    expect(lastQuery(calls)?.get('kind')).toBeNull();
    await user.selectOptions(sel, 'short');
    await waitFor(() => expect(lastQuery(calls)?.get('kind')).toBe('short'));
    expect(lastQuery(calls)?.get('page')).toBe('1');
    expect(lastQuery(calls)?.has('date_from')).toBe(true); // 기간 조건과 함께
    await user.selectOptions(sel, 'long');
    await waitFor(() => expect(lastQuery(calls)?.get('kind')).toBe('long'));
    await user.selectOptions(sel, '');
    await waitFor(() => expect(sel).toHaveValue(''));
  });

  it('TC-FE-HK-003 구분을 고르고 0건이면 "조건에 맞는 항목 없음" 안내가 나온다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([
      route('GET', '/api/v1/changes', (r) =>
        r.query.get('kind') === 'short' ? json(200, { items: [], total: 0, page: 1, page_size: 50 }) : json(200, { items, total: 3, page: 1, page_size: 50 }),
      ),
    ]);
    renderWithApp(<HistoryPage />, client, '/history');
    await screen.findByText('긴 영상 하나');
    await user.selectOptions(screen.getByRole('combobox', { name: '영상 구분' }), 'short');
    expect(await screen.findByText('조건에 맞는 영상이 없습니다')).toBeInTheDocument();
  });
});
