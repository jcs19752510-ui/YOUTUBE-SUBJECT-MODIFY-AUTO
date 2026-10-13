import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { dashboard } from '../test/fixtures';
import { json, makeClient, problem, renderWithApp, route, type Handler } from '../test/utils';
import { App } from './App';

const dash = route('GET', '/api/v1/dashboard', () => json(200, dashboard()));
const authed = (csrf = 'c1'): Handler =>
  route('GET', '/api/v1/auth/me', () =>
    json(200, { authenticated: true, pin_required: false, csrf_token: csrf }),
  );

describe('시작·세션 화면', () => {
  it('TC-WF-072 PIN 이 필요하면 PIN 화면을 보여 주고, 틀리면 안내, 맞으면 본 화면으로 간다', async () => {
    const user = userEvent.setup();
    let ok = false;
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(200, { authenticated: ok, pin_required: !ok, csrf_token: ok ? 'c' : null }),
      ),
      route('POST', '/api/v1/auth/session', (r) => {
        if ((r.body as { pin?: string }).pin !== '1234')
          return problem(401, 'pin_invalid', 'PIN 이 맞지 않습니다');
        ok = true;
        return json(200, { csrf_token: 'c' });
      }),
      dash,
    ]);
    renderWithApp(<App />, client);
    expect(
      await screen.findByRole('heading', { name: 'PIN 을 입력해 주세요' }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText('PIN'), '0000');
    await user.click(screen.getByRole('button', { name: '확인' }));
    expect(
      await screen.findByText('PIN 이 맞지 않습니다. 다시 확인해 주세요.'),
    ).toBeInTheDocument();
    await user.clear(screen.getByLabelText('PIN'));
    await user.type(screen.getByLabelText('PIN'), '1234');
    await user.click(screen.getByRole('button', { name: '확인' }));
    expect(await screen.findByRole('heading', { name: '홈' })).toBeInTheDocument();
  });

  it('TC-WF-073 처음부터 서버에 연결할 수 없으면 "서버 연결이 끊겼습니다" 화면과 다시 연결 버튼을 보여 주고, 서버가 켜지면 복구된다', async () => {
    const user = userEvent.setup();
    let down = true;
    const { client } = makeClient([
      () => {
        if (down) throw new TypeError('Failed to fetch');
        return undefined;
      },
      authed(),
      dash,
    ]);
    renderWithApp(<App />, client);
    expect(
      await screen.findByRole('heading', { name: '서버 연결이 끊겼습니다' }),
    ).toBeInTheDocument();
    down = false;
    await user.click(screen.getByRole('button', { name: '다시 연결' }));
    expect(await screen.findByRole('heading', { name: '홈' })).toBeInTheDocument();
  });

  it('TC-WF-074 상단에 "데모 모드 — 유튜브에 아무것도 전송되지 않습니다" 배지와 연결 상태가 항상 보인다', async () => {
    const { client } = makeClient([
      authed(),
      dash,
      route('GET', '/api/v1/videos', () =>
        json(200, { items: [], total: 0, page: 1, page_size: 50 }),
      ),
    ]);
    renderWithApp(<App />, client, '/videos');
    await screen.findByRole('heading', { name: '영상 목록' });
    expect(screen.getByText('데모 모드 — 유튜브에 아무것도 전송되지 않습니다')).toBeInTheDocument();
    expect(screen.getByText('서버 연결됨')).toBeInTheDocument();
    expect(
      within(screen.getByRole('navigation', { name: '주 메뉴' })).getAllByRole('link'),
    ).toHaveLength(7);
  });

  it('TC-WF-075 메뉴로 이동하면 새 화면 제목으로 포커스가 이동한다', async () => {
    const user = userEvent.setup();
    const { client } = makeClient([
      authed(),
      dash,
      route('GET', '/api/v1/changes', () =>
        json(200, { items: [], total: 0, page: 1, page_size: 50 }),
      ),
    ]);
    renderWithApp(<App />, client);
    await screen.findByRole('heading', { name: '홈' });
    await user.click(screen.getByRole('link', { name: '이력·롤백' }));
    const h = await screen.findByRole('heading', { name: '이력·롤백' });
    await waitFor(() => expect(h).toHaveFocus());
    expect(screen.getByRole('link', { name: '이력·롤백' })).toHaveAttribute('aria-current', 'page');
  });

  it('TC-WF-076 사용 중 세션이 만료되면 화면을 유지한 채 PIN 재입력 창을 띄우고, 입력하면 이어서 쓴다', async () => {
    const user = userEvent.setup();
    let phase: 'ok' | 'expired' | 'renewed' = 'ok';
    const { client } = makeClient([
      route('GET', '/api/v1/auth/me', () =>
        json(
          200,
          phase === 'ok'
            ? { authenticated: true, pin_required: false, csrf_token: 'c' }
            : phase === 'expired'
              ? { authenticated: false, pin_required: true, csrf_token: null }
              : { authenticated: true, pin_required: false, csrf_token: 'c2' },
        ),
      ),
      route('POST', '/api/v1/auth/session', () => {
        phase = 'renewed';
        return json(200, { csrf_token: 'c2' });
      }),
      route('GET', '/api/v1/dashboard', () =>
        phase === 'expired'
          ? problem(401, 'unauthenticated', '로그인 필요')
          : json(200, dashboard()),
      ),
      route('GET', '/api/v1/changes', () =>
        phase === 'ok'
          ? ((phase = 'expired'), problem(401, 'unauthenticated', '로그인 필요'))
          : json(200, { items: [], total: 0, page: 1, page_size: 50 }),
      ),
    ]);
    renderWithApp(<App />, client);
    await screen.findByText('2 / 10건');
    await user.click(screen.getByRole('link', { name: '이력·롤백' }));
    const dlg = await screen.findByRole('dialog', { name: '세션이 만료되었습니다' });
    expect(screen.getByText('데모 모드 — 유튜브에 아무것도 전송되지 않습니다')).toBeInTheDocument();
    await user.type(within(dlg).getByLabelText('PIN'), '1234');
    await user.click(within(dlg).getByRole('button', { name: '확인' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByText('아직 변경 이력이 없습니다')).toBeInTheDocument();
  });

  it('TC-WF-077 로그아웃하면 안내 화면이 나오고 다시 연결할 수 있다', async () => {
    const user = userEvent.setup();
    const { client } = makeClient([
      authed(),
      dash,
      route('DELETE', '/api/v1/auth/session', () => json(204, null)),
    ]);
    renderWithApp(<App />, client);
    await screen.findByRole('heading', { name: '홈' });
    await user.click(screen.getByRole('button', { name: '로그아웃' }));
    expect(await screen.findByRole('heading', { name: '로그아웃되었습니다' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '다시 연결' }));
    expect(await screen.findByRole('heading', { name: '홈' })).toBeInTheDocument();
  });

  it('TC-WF-078 서버 연결이 도중에 끊기면 화면은 유지하고 경고 배너를 띄운다', async () => {
    const user = userEvent.setup();
    let down = false;
    const { client } = makeClient([
      () => {
        if (down) throw new TypeError('Failed to fetch');
        return undefined;
      },
      authed(),
      dash,
    ]);
    renderWithApp(<App />, client);
    await screen.findByText('2 / 10건');
    down = true;
    await user.click(screen.getByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(screen.getAllByText('서버 연결 끊김').length).toBeGreaterThan(0));
    expect(screen.getByText('2 / 10건')).toBeInTheDocument();
  });

  it('TC-WF-079 없는 주소는 안내 화면과 홈 링크를 보여 준다', async () => {
    const { client } = makeClient([authed(), dash]);
    renderWithApp(<App />, client, '/없는-주소');
    expect(
      await screen.findByRole('heading', { name: '페이지를 찾을 수 없습니다' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '홈으로' })).toBeInTheDocument();
  });
});
