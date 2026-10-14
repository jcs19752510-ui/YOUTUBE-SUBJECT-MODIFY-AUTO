import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { dashboard } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { VideosPage } from './VideosPage';

const empty = route('GET', '/api/v1/videos', () =>
  json(200, { items: [], total: 0, page: 1, page_size: 50 }),
);
const noVideos = { videos: 0, excluded: 0, suggested: 0, approved: 0, queued: 0, applied: 0 };

describe('빈 영상 목록 안내 (DEF-LIVE-006 후속)', () => {
  it('구글에 연결된 상태에서는 데모 문구 대신 내 채널 영상 불러오기를 안내한다', async () => {
    const c = await connectedClient([
      empty,
      route('GET', '/api/v1/dashboard', () =>
        json(200, dashboard({ counts: noVideos, google: { mode: 'live', connected: true } })),
      ),
    ]);
    renderWithApp(<VideosPage />, c.client, '/videos');
    await userEvent.setup().click(await screen.findByRole('button', { name: '전체 기간' })); // 기본 기간(오늘) 해제
    expect(await screen.findByText(/내 채널 영상 목록을 불러오세요/)).toBeInTheDocument();
    expect(screen.queryByText(/데모 영상 불러오기/)).toBeNull();
  });
  it('데모 모드에서는 기존 데모 안내를 그대로 보여 준다', async () => {
    const c = await connectedClient([
      empty,
      route('GET', '/api/v1/dashboard', () => json(200, dashboard({ counts: noVideos }))),
    ]);
    renderWithApp(<VideosPage />, c.client, '/videos');
    await userEvent.setup().click(await screen.findByRole('button', { name: '전체 기간' })); // 기본 기간(오늘) 해제
    expect(await screen.findByText(/데모 영상 불러오기/)).toBeInTheDocument();
  });
});
