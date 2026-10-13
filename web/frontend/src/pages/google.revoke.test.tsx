import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { dashboard } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { HomePage } from './HomePage';

vi.mock('../lib/navigate', () => ({ navigateTo: vi.fn() }));

const base = { mode: 'read', connected: true, client_ready: true, last_error: null, message: '연결돼 있습니다.' };

async function disconnectWith(body: Record<string, unknown>) {
  const user = userEvent.setup();
  const { client, calls } = await connectedClient([
    route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
    route('GET', '/api/v1/google/status', () => json(200, base)),
    route('POST', '/api/v1/google/disconnect', () => json(200, body)),
  ]);
  renderWithApp(<HomePage />, client);
  await user.click(await screen.findByRole('button', { name: '연결 해제' }));
  await user.click(screen.getByRole('button', { name: '해제' }));
  await waitFor(() => expect(calls.some((c) => c.path === '/api/v1/google/disconnect')).toBe(true));
}

describe('연결 해제 후 구글 폐기 안내', () => {
  it('revoked=true 면 폐기를 요청했다고 안내한다', async () => {
    await disconnectWith({ connected: false, revoked: true });
    expect(await screen.findByText('구글에도 접근 권한 폐기를 요청했습니다.')).toBeInTheDocument();
  });
  it('revoked=false 면 PC 로그인 정보는 지웠고 구글 폐기는 못 했다는 것과 직접 제거 방법을 안내한다', async () => {
    await disconnectWith({ connected: false, revoked: false });
    expect(await screen.findByText(/이 PC의 로그인 정보는 지웠습니다\. 구글 쪽 폐기는 하지 못했습니다/)).toBeInTheDocument();
    expect(screen.getByText(/보안 > 타사 앱 액세스/)).toBeInTheDocument();
  });
  it('revoked=null 이면 추가 안내가 없다(기존 문구만)', async () => {
    await disconnectWith({ connected: false, revoked: null });
    expect(await screen.findByText('구글 연결을 해제했습니다.')).toBeInTheDocument();
    expect(screen.queryByText(/폐기/)).not.toBeInTheDocument();
  });
});
