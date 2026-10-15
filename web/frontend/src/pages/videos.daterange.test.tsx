import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { kstDateOffset } from '../lib/format';
import { video } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { VideosPage } from './VideosPage';

const okRoute = route('GET', '/api/v1/videos', () =>
  json(200, { items: [video(1)], total: 1, page: 1, page_size: 50 }),
);
const emptyRoute = route('GET', '/api/v1/videos', () =>
  json(200, { items: [], total: 0, page: 1, page_size: 50 }),
);
const lastQuery = (calls: { path: string; query: URLSearchParams }[]) =>
  calls.filter((c) => c.path === '/api/v1/videos').at(-1)?.query;

describe('영상 목록 조회 기간', () => {
  it('기본값은 오늘(한국 시간)이고 요청에 date_from/date_to로 실린다', async () => {
    const { client, calls } = await connectedClient([okRoute]);
    renderWithApp(<VideosPage />, client, '/videos');
    await screen.findByText('테스트 영상 1');
    const today = kstDateOffset(0);
    expect(screen.getByLabelText('조회 시작일')).toHaveValue(today);
    expect(screen.getByLabelText('조회 종료일')).toHaveValue(today);
    expect(lastQuery(calls)?.get('date_from')).toBe(today);
    expect(lastQuery(calls)?.get('date_to')).toBe(today);
  });

  it('날짜를 바꾸면 요청 쿼리에 반영되고 1쪽으로 돌아간다', async () => {
    const { client, calls } = await connectedClient([okRoute]);
    renderWithApp(<VideosPage />, client, '/videos?page=3');
    await screen.findByText('테스트 영상 1');
    const from = screen.getByLabelText('조회 시작일');
    await userEvent.setup().clear(from);
    await userEvent.setup().type(from, '2026-01-02');
    await waitFor(() => {
      expect(lastQuery(calls)?.get('date_from')).toBe('2026-01-02');
      expect(lastQuery(calls)?.get('page')).toBe('1');
    });
  });

  it('[전체 기간] 버튼은 날짜 조건을 빼고 조회한다', async () => {
    const { client, calls } = await connectedClient([okRoute]);
    renderWithApp(<VideosPage />, client, '/videos');
    await screen.findByText('테스트 영상 1');
    await userEvent.setup().click(screen.getByRole('button', { name: '전체 기간' }));
    await waitFor(() => {
      const q = lastQuery(calls);
      expect(q?.has('date_from')).toBe(false);
      expect(q?.has('date_to')).toBe(false);
    });
  });

  it('시작일이 종료일보다 뒤면 안내만 보이고 조회하지 않는다', async () => {
    const { client, calls } = await connectedClient([okRoute]);
    renderWithApp(<VideosPage />, client, '/videos');
    await screen.findByText('테스트 영상 1');
    const before = calls.filter((c) => c.path === '/api/v1/videos').length;
    const from = screen.getByLabelText('조회 시작일');
    await userEvent.setup().clear(from);
    await userEvent.setup().type(from, '2099-12-31');
    expect(await screen.findByText(/시작일이 종료일보다 뒤입니다/)).toBeInTheDocument();
    const after = calls.filter((c) => c.path === '/api/v1/videos');
    expect(after.every((c) => c.query.get('date_from') !== '2099-12-31')).toBe(true);
    expect(after.length).toBeGreaterThanOrEqual(before);
  });

  it('결과가 0건이면 기간 안내를 보여 준다', async () => {
    const { client } = await connectedClient([emptyRoute]);
    renderWithApp(<VideosPage />, client, '/videos');
    expect(await screen.findByText(/선택한 기간에 해당하는 항목이 없습니다/)).toBeInTheDocument();
  });
});
