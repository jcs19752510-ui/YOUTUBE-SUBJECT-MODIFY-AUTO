import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { dashboard } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { HomePage } from './HomePage';

vi.mock('../lib/navigate', () => ({ navigateTo: vi.fn() }));
import { navigateTo } from '../lib/navigate';

const base = {
  mode: 'read',
  connected: false,
  client_ready: true,
  last_error: null,
  message: '구글 연결 준비가 됐습니다.',
};
const dash = route('GET', '/api/v1/dashboard', () => json(200, dashboard()));

beforeEach(() => vi.mocked(navigateTo).mockClear());

describe('구글 연결 카드', () => {
  it('TC-WF-200 연결 파일이 없으면 준비 방법을 안내하고 연결 버튼은 없다', async () => {
    const { client } = await connectedClient([
      dash,
      route('GET', '/api/v1/google/status', () =>
        json(200, { ...base, mode: 'demo', client_ready: false, message: '데모 모드입니다.' }),
      ),
    ]);
    renderWithApp(<HomePage />, client);
    expect(await screen.findByText(/google_client\.json 을 저장한 뒤/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '구글 계정 연결' })).not.toBeInTheDocument();
  });

  it('TC-WF-201 준비됐으면 [구글 계정 연결]이 보이고 누르면 구글 로그인 주소로 이동한다(읽기 전용 안내 포함)', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      dash,
      route('GET', '/api/v1/google/status', () => json(200, base)),
      route('POST', '/api/v1/google/connect', () =>
        json(200, { auth_url: 'https://accounts.google.com/o/oauth2/v2/auth?x=1' }),
      ),
    ]);
    renderWithApp(<HomePage />, client);
    expect(await screen.findByText(/읽기 전용입니다/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '구글 계정 연결' }));
    await waitFor(() =>
      expect(navigateTo).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?x=1'),
    );
    expect(calls.some((c) => c.method === 'POST' && c.path === '/api/v1/google/connect')).toBe(
      true,
    );
  });

  it('TC-WF-202 연결됐으면 [내 영상 불러오기]와 [연결 해제]가 보이고, 해제는 한 번 더 확인한다', async () => {
    const user = userEvent.setup();
    let connected = true;
    const { client, calls } = await connectedClient([
      dash,
      route('GET', '/api/v1/google/status', () =>
        json(200, { ...base, connected, message: '구글(유튜브)에 읽기 전용으로 연결돼 있습니다.' }),
      ),
      route('POST', '/api/v1/videos/sync', () =>
        json(202, { id: 'j1', type: 'videos.sync', status: 'queued', progress: 0, total: 0 }),
      ),
      route('POST', '/api/v1/google/disconnect', () => {
        connected = false;
        return json(200, { connected: false });
      }),
    ]);
    renderWithApp(<HomePage />, client);
    await user.click(await screen.findByRole('button', { name: '내 영상 불러오기' }));
    await waitFor(() => expect(calls.some((c) => c.path === '/api/v1/videos/sync')).toBe(true));
    await user.click(screen.getByRole('button', { name: '연결 해제' }));
    expect(screen.getByText(/저장된 로그인 정보가 지워집니다/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === '/api/v1/google/disconnect')).toBe(false); // 확인 전에는 호출하지 않음
    await user.click(screen.getByRole('button', { name: '해제' }));
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/api/v1/google/disconnect')).toBe(true),
    );
  });

  it('TC-WF-203 구글에서 온 오류 안내를 사용자에게 보여 준다', async () => {
    const { client } = await connectedClient([
      dash,
      route('GET', '/api/v1/google/status', () =>
        json(200, {
          ...base,
          last_error: '로그인 요청이 만료됐거나 올바르지 않습니다. 처음부터 다시 시도해 주세요.',
        }),
      ),
    ]);
    renderWithApp(<HomePage />, client);
    expect(await screen.findByText(/로그인 요청이 만료됐거나/)).toBeInTheDocument();
  });
  it('TC-WF-210 읽기만 연결됐으면 [제목 수정 권한 연결]이 보이고 누르면 쓰기 로그인 주소로 이동한다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      dash,
      route('GET', '/api/v1/google/status', () =>
        json(200, { ...base, connected: true, write_connected: false }),
      ),
      route('POST', '/api/v1/google/connect-write', () =>
        json(200, { auth_url: 'https://accounts.google.com/o/oauth2/v2/auth?w=1' }),
      ),
    ]);
    renderWithApp(<HomePage />, client);
    expect(await screen.findByText(/이 권한만으로는 제목이 바뀌지 않습니다/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '제목 수정 권한 연결' }));
    await waitFor(() =>
      expect(navigateTo).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?w=1'),
    );
    expect(calls.some((c) => c.path === '/api/v1/google/connect-write')).toBe(true);
  });

  it('TC-WF-211 쓰기 권한은 연결됐지만 실제 수정이 꺼져 있으면 "아직 꺼져 있음"을 알리고 경고는 없다', async () => {
    const { client } = await connectedClient([
      dash,
      route('GET', '/api/v1/google/status', () =>
        json(200, {
          ...base,
          connected: true,
          write_connected: true,
          live_write_ready: false,
          live_allowed_count: 0,
        }),
      ),
    ]);
    renderWithApp(<HomePage />, client);
    expect(
      await screen.findByText(/실제 수정은 아직 꺼져 있습니다\(수정 허용 영상 0개\)/),
    ).toBeInTheDocument();
    expect(screen.queryByText('실제 수정 모드가 켜져 있습니다')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '제목 수정 권한 연결' })).not.toBeInTheDocument();
  });

  it('TC-WF-212 실제 수정이 가능한 상태면 허용 영상 수와 되돌리기 한계를 담은 경고를 보여 준다', async () => {
    const { client } = await connectedClient([
      dash,
      route('GET', '/api/v1/google/status', () =>
        json(200, {
          ...base,
          connected: true,
          write_connected: true,
          live_write_ready: true,
          live_allowed_count: 1,
        }),
      ),
    ]);
    renderWithApp(<HomePage />, client);
    expect(await screen.findByText('실제 수정 모드가 켜져 있습니다')).toBeInTheDocument();
    expect(
      screen.getByText(/수정 허용 영상 1개의 제목이 실제 유튜브에서 바뀝니다/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/읽기 전용입니다/)).not.toBeInTheDocument();
  });
  it('TC-WF-213 홈 상태 카드: 연결 파일만 있고 로그인 전이면 "구글 연결 안 됨", 실제 수정 가능 상태면 "라이브: 켜짐"이 보인다', async () => {
    const mk = (over: object) =>
      route('GET', '/api/v1/dashboard', () => json(200, { ...dashboard(), ...over }));
    const a = await connectedClient([
      mk({ mode: 'demo', live_enabled: false, google: { mode: 'read', connected: false } }),
      route('GET', '/api/v1/google/status', () => json(200, base)),
    ]);
    const r1 = renderWithApp(<HomePage />, a.client);
    expect(await screen.findByText('구글 연결 안 됨', { selector: 'li' })).toBeInTheDocument();
    expect(screen.queryByText('구글 연결됨', { selector: '.badge' })).not.toBeInTheDocument();
    r1.unmount();
    const b = await connectedClient([
      mk({ mode: 'live', live_enabled: true, google: { mode: 'read', connected: true } }),
      route('GET', '/api/v1/google/status', () => json(200, { ...base, connected: true })),
    ]);
    renderWithApp(<HomePage />, b.client);
    expect(await screen.findByText('실제 반영(라이브): 켜짐')).toBeInTheDocument();
  });
});
