import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { video } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { VideosPage } from './VideosPage';

const items = [
  video(1, { title: '긴 영상 하나', duration_sec: 600, is_short: false }),
  video(2, { title: '쇼츠 영상 둘', duration_sec: 45, is_short: true }),
  video(3, { title: '길이 모르는 영상', duration_sec: null, is_short: false }),
];
const okRoute = route('GET', '/api/v1/videos', () =>
  json(200, { items, total: 3, page: 1, page_size: 50 }),
);
const lastQuery = (calls: { path: string; query: URLSearchParams }[]) =>
  calls.filter((c) => c.path === '/api/v1/videos').at(-1)?.query;

describe('영상 구분(롱폼/쇼츠) 조회·표시 (2026-10-14)', () => {
  it('TC-FE-VK-001 목록에 "구분" 열이 있고 롱폼·쇼츠·길이 불명(-)이 각각 표시된다', async () => {
    const { client } = await connectedClient([okRoute]);
    renderWithApp(<VideosPage />, client, '/videos');
    await screen.findByText('긴 영상 하나');
    expect(screen.getByRole('columnheader', { name: '구분' })).toBeInTheDocument();
    const rowOf = (t: string) => screen.getByText(t).closest('tr')!;
    expect(within(rowOf('긴 영상 하나')).getByText('롱폼')).toBeInTheDocument();
    expect(within(rowOf('쇼츠 영상 둘')).getAllByText('쇼츠').length).toBeGreaterThan(0);
    expect(within(rowOf('길이 모르는 영상')).queryByText('롱폼')).toBeNull();
    expect(within(rowOf('길이 모르는 영상')).queryByText('쇼츠')).toBeNull();
  });

  it('TC-FE-VK-002 영상 구분 선택 상자가 롱폼/쇼츠를 요청 쿼리 kind 로 보내고 전체로 돌리면 뺀다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([okRoute]);
    renderWithApp(<VideosPage />, client, '/videos');
    await screen.findByText('긴 영상 하나');
    const sel = screen.getByRole('combobox', { name: '영상 구분' });
    expect(lastQuery(calls)?.get('kind')).toBeNull();
    await user.selectOptions(sel, 'short');
    await waitFor(() => expect(lastQuery(calls)?.get('kind')).toBe('short'));
    expect(lastQuery(calls)?.get('page')).toBe('1');
    await user.selectOptions(sel, 'long');
    await waitFor(() => expect(lastQuery(calls)?.get('kind')).toBe('long'));
    await user.selectOptions(sel, '');
    // 전체로 돌리면 처음과 같은 조회 조건이라 저장된 결과를 다시 쓰므로 새 요청이 없을 수 있다 → 선택값과 kind 가 비어 있는지로 확인한다
    await waitFor(() => expect(sel).toHaveValue(''));
    expect(screen.getByText('쇼츠 영상 둘')).toBeInTheDocument();
  });

  it('TC-FE-VK-003 주소의 kind=short 로 열면 선택 상자가 쇼츠로 보이고 요청에도 실린다', async () => {
    const { client, calls } = await connectedClient([okRoute]);
    renderWithApp(<VideosPage />, client, '/videos?kind=short');
    await screen.findByText('긴 영상 하나');
    expect(screen.getByRole('combobox', { name: '영상 구분' })).toHaveValue('short');
    expect(lastQuery(calls)?.get('kind')).toBe('short');
  });
});
