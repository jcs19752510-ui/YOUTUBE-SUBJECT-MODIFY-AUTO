// 06단계 독립 검증(M2 단위4·M3 단위3) — 구글 연결 카드(GoogleCard). 사용자(비개발자 채널 소유자) 관점.
// 제품 소스는 건드리지 않는다. 기대값은 화면 문구가 사용자에게 사실인지(거짓 안내가 없는지)에서 도출한다.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { GoogleStatus } from '../src/api/types';
import { ko } from '../src/i18n/ko';
import { GoogleCard } from '../src/pages/GoogleCard';
import { axeViolations, connectedClient, json, problem, renderWithApp, route } from '../src/test/utils';
import type { Handler } from '../src/test/utils';

vi.mock('../src/lib/navigate', () => ({ navigateTo: vi.fn() }));
import { navigateTo } from '../src/lib/navigate';

const base: GoogleStatus = {
  mode: 'read',
  connected: false,
  client_ready: true,
  last_error: null,
  message: '구글 연결 준비가 됐습니다.',
  write_connected: false,
  live_write_enabled: false,
  live_allowed_count: 0,
  live_write_ready: false,
};
const st = (o: Partial<GoogleStatus>): GoogleStatus => ({ ...base, ...o });
const statusRoute = (s: GoogleStatus | (() => GoogleStatus)): Handler =>
  route('GET', '/api/v1/google/status', () => json(200, typeof s === 'function' ? s() : s));

async function card(s: GoogleStatus, extra: Handler[] = []) {
  const c = await connectedClient([statusRoute(s), ...extra]);
  const r = renderWithApp(<GoogleCard />, c.client);
  await screen.findByRole('heading', { name: ko.google.title });
  await screen.findByText(s.message);
  return { ...c, ...r };
}
const text = () => document.body.textContent ?? '';
const btn = (name: string | RegExp) => screen.queryByRole('button', { name });

beforeEach(() => vi.mocked(navigateTo).mockClear());

describe('M2 단위4: 연결 전 상태', () => {
  it('TC-VMF-001 클라이언트 파일 없음: 준비 방법 안내, 어떤 버튼도 없고 쓰기 구역도 없다', async () => {
    await card(st({ client_ready: false, mode: 'demo', message: '데모 모드입니다.' }));
    expect(screen.getByText(ko.google.needFile)).toBeInTheDocument();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryByText(ko.google.writeTitle)).toBeNull();
    expect(screen.queryByText(ko.google.readOnly)).toBeNull();
  });

  it('TC-VMF-002 준비됨·미연결: [구글 계정 연결]만 보이고 불러오기·해제·쓰기 구역은 없으며 "읽기 전용" 안내가 있다', async () => {
    await card(base);
    expect(btn(ko.google.connect)).toBeInTheDocument();
    expect(btn(ko.google.syncReal)).toBeNull();
    expect(btn(ko.google.disconnect)).toBeNull();
    expect(btn(ko.google.writeConnect)).toBeNull();
    expect(screen.queryByText(ko.google.writeTitle)).toBeNull();
    expect(screen.getByText(ko.google.readOnly)).toBeInTheDocument();
    expect(screen.queryByText(ko.google.needFile)).toBeNull();
  });

  it('TC-VMF-003 [구글 계정 연결]은 POST /google/connect 후 받은 주소로 이동하고, 중복 클릭해도 요청은 1번', async () => {
    const user = userEvent.setup();
    const { calls } = await card(base, [
      route('POST', '/api/v1/google/connect', () => json(200, { auth_url: 'https://accounts.google.com/x?y=1' })),
    ]);
    await user.dblClick(btn(ko.google.connect)!);
    await waitFor(() => expect(navigateTo).toHaveBeenCalledWith('https://accounts.google.com/x?y=1'));
    expect(calls.filter((c) => c.path === '/api/v1/google/connect')).toHaveLength(1);
    expect(calls.find((c) => c.path === '/api/v1/google/connect')!.headers['x-csrf-token']).toBe('csrf-1');
  });

  it('TC-VMF-004 연결 시작이 409(연결 파일 문제)로 실패하면 이동하지 않고 한국어 오류 안내가 보인다', async () => {
    const user = userEvent.setup();
    await card(base, [
      route('POST', '/api/v1/google/connect', () =>
        problem(409, 'google_client_invalid', '구글 연결 파일 문제', '파일 형식이 맞지 않습니다.', '파일을 다시 받아 저장하세요.'),
      ),
    ]);
    await user.click(btn(ko.google.connect)!);
    expect(await screen.findByText('구글 연결 파일 문제')).toBeInTheDocument();
    expect(navigateTo).not.toHaveBeenCalled();
    expect(btn(ko.google.connect)).toBeEnabled();
  });
});

describe('M2 단위4: 연결 후(읽기)', () => {
  const connected = st({ connected: true, message: '구글에 연결돼 있습니다.' });

  it('TC-VMF-010 연결됨: [내 영상 불러오기]와 [연결 해제]가 보이고 [구글 계정 연결]은 사라진다', async () => {
    await card(connected);
    expect(btn(ko.google.syncReal)).toBeInTheDocument();
    expect(btn(ko.google.disconnect)).toBeInTheDocument();
    expect(btn(ko.google.connect)).toBeNull();
  });

  it('TC-VMF-011 [내 영상 불러오기]는 POST /videos/sync 를 1번 보내고 시작 안내를 보인다', async () => {
    const user = userEvent.setup();
    const { calls } = await card(connected, [
      route('POST', '/api/v1/videos/sync', () =>
        json(202, { id: 'j1', type: 'videos.sync', status: 'queued', progress: 0, total: 0, error: null, result: null }),
      ),
    ]);
    await user.click(btn(ko.google.syncReal)!);
    expect(await screen.findByText(ko.google.syncStarted)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === 'POST' && c.path === '/api/v1/videos/sync')).toHaveLength(1);
  });

  it('TC-VMF-012 불러오기 실패(예: 할당량 초과 429)는 오류 안내가 보이고 시작 안내는 없다', async () => {
    const user = userEvent.setup();
    await card(connected, [
      route('POST', '/api/v1/videos/sync', () => problem(429, 'quota_exceeded', '오늘 사용량을 모두 썼습니다', '내일 다시 시도하세요.')),
    ]);
    await user.click(btn(ko.google.syncReal)!);
    expect(await screen.findByText('오늘 사용량을 모두 썼습니다')).toBeInTheDocument();
    expect(screen.queryByText(ko.google.syncStarted)).toBeNull();
  });

  it('TC-VMF-013 연결 해제는 확인을 한 번 더 묻고, 취소하면 요청이 없으며, 확인하면 POST /disconnect 후 상태를 다시 읽는다', async () => {
    const user = userEvent.setup();
    let isConnected = true;
    const c = await connectedClient([
      statusRoute(() => (isConnected ? connected : base)),
      route('POST', '/api/v1/google/disconnect', () => {
        isConnected = false;
        return json(200, { connected: false });
      }),
    ]);
    renderWithApp(<GoogleCard />, c.client);
    await user.click(await screen.findByRole('button', { name: ko.google.disconnect }));
    expect(screen.getByText(ko.google.disconnectAsk)).toBeInTheDocument();
    expect(btn(ko.google.disconnect)).toBeNull(); // 확인창이 떠 있는 동안 중복 진입 버튼은 숨는다
    await user.click(screen.getByRole('button', { name: ko.google.disconnectNo }));
    expect(screen.queryByText(ko.google.disconnectAsk)).toBeNull();
    expect(c.calls.some((x) => x.path.endsWith('/disconnect'))).toBe(false);
    await user.click(screen.getByRole('button', { name: ko.google.disconnect }));
    await user.click(screen.getByRole('button', { name: ko.google.disconnectYes }));
    expect(await screen.findByText(ko.google.disconnected)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: ko.google.connect })).toBeInTheDocument();
    expect(c.calls.filter((x) => x.path.endsWith('/disconnect'))).toHaveLength(1);
    expect(screen.queryByText(ko.google.writeTitle)).toBeNull();
  });

  it('TC-VMF-014 연결 해제 실패(500)면 확인창이 유지되고 오류가 보이며 "해제했습니다" 안내는 없다', async () => {
    const user = userEvent.setup();
    await card(connected, [
      route('POST', '/api/v1/google/disconnect', () => problem(500, 'internal', '서버 오류', '잠시 후 다시 시도하세요.')),
    ]);
    await user.click(btn(ko.google.disconnect)!);
    await user.click(btn(ko.google.disconnectYes)!);
    expect(await screen.findByText('서버 오류')).toBeInTheDocument();
    expect(screen.queryByText(ko.google.disconnected)).toBeNull();
    expect(screen.getByText(ko.google.disconnectAsk)).toBeInTheDocument();
  });

  it('TC-VMF-015 마지막 오류가 있으면 경고 안내(role=alert)로 보이고, "데모" 단어가 있을 때만 초기화 힌트가 붙는다', async () => {
    const a = await card(st({ last_error: '구글 로그인이 취소되었습니다.' }));
    const alert = screen.getAllByRole('alert')[0]!;
    expect(within(alert).getByText(ko.google.errorTitle)).toBeInTheDocument();
    expect(within(alert).getByText('구글 로그인이 취소되었습니다.')).toBeInTheDocument();
    expect(screen.queryByText(ko.google.resetHint)).toBeNull();
    a.unmount();
    await card(st({ last_error: '데모 기록이 남아 있어 불러올 수 없습니다.' }));
    expect(screen.getByText(ko.google.resetHint)).toBeInTheDocument();
  });

  it('TC-VMF-016 last_error 가 null/빈 문자열이면 오류 안내 칸이 나오지 않는다', async () => {
    const a = await card(st({ last_error: null }));
    expect(screen.queryByText(ko.google.errorTitle)).toBeNull();
    a.unmount();
    await card(st({ last_error: '' }));
    expect(screen.queryByText(ko.google.errorTitle)).toBeNull();
  });

  it('TC-VMF-017 상태 조회 실패는 "확인하지 못했습니다"를 보이고 버튼은 만들지 않는다(거짓으로 연결됨 표시 금지)', async () => {
    const c = await connectedClient([route('GET', '/api/v1/google/status', () => problem(500, 'internal', '서버 오류'))]);
    renderWithApp(<GoogleCard />, c.client);
    expect(await screen.findByText(ko.google.checkFail)).toBeInTheDocument();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryByText(ko.google.writeTitle)).toBeNull();
  });
});

describe('M3 단위3: 제목 수정 권한 구역', () => {
  const rc = (o: Partial<GoogleStatus>) => st({ connected: true, message: '구글에 연결돼 있습니다.', ...o });

  it('TC-VMF-020 쓰기 미연결: 설명과 [제목 수정 권한 연결]이 있고, 설명은 "권한만으로 제목이 바뀌지 않는다"를 알린다', async () => {
    await card(rc({}));
    expect(screen.getByRole('heading', { name: ko.google.writeTitle })).toBeInTheDocument();
    expect(screen.getByText(ko.google.writeExplain)).toBeInTheDocument();
    expect(ko.google.writeExplain).toMatch(/이 권한만으로는 제목이 바뀌지 않습니다/);
    expect(btn(ko.google.writeConnect)).toBeEnabled();
    expect(screen.queryByText(ko.google.writeConnected)).toBeNull();
    expect(screen.queryByText(ko.google.liveWarnTitle)).toBeNull();
    expect(screen.getByText(ko.google.readOnly)).toBeInTheDocument(); // 아직 읽기 전용이 사실
  });

  it('TC-VMF-021 [제목 수정 권한 연결]은 POST /google/connect-write(읽기용 connect 와 다른 경로) 후 이동한다', async () => {
    const user = userEvent.setup();
    const { calls } = await card(rc({}), [
      route('POST', '/api/v1/google/connect-write', () => json(200, { auth_url: 'https://accounts.google.com/w?scope=youtube' })),
    ]);
    await user.click(btn(ko.google.writeConnect)!);
    await waitFor(() => expect(navigateTo).toHaveBeenCalledWith('https://accounts.google.com/w?scope=youtube'));
    expect(calls.some((c) => c.path === '/api/v1/google/connect-write' && c.method === 'POST')).toBe(true);
    expect(calls.some((c) => c.path === '/api/v1/google/connect')).toBe(false);
  });

  it('TC-VMF-022 쓰기 연결 요청이 실패하면 이동하지 않고 오류가 보이며 다시 누를 수 있다', async () => {
    const user = userEvent.setup();
    await card(rc({}), [
      route('POST', '/api/v1/google/connect-write', () => problem(409, 'google_client_missing', '구글 연결 파일 문제', '파일이 없습니다.')),
    ]);
    await user.click(btn(ko.google.writeConnect)!);
    expect(await screen.findByText('구글 연결 파일 문제')).toBeInTheDocument();
    expect(navigateTo).not.toHaveBeenCalled();
    expect(btn(ko.google.writeConnect)).toBeEnabled();
  });

  it('TC-VMF-023 쓰기 연결됨·실제 수정 꺼짐: "연결돼 있습니다"+"아직 꺼져 있습니다"+허용 영상 수, 연결 버튼은 사라지고, 거짓 안내("제목을 바꾸지 않습니다")는 없다', async () => {
    await card(rc({ write_connected: true, live_allowed_count: 0 }));
    expect(screen.getByText(ko.google.writeConnected)).toBeInTheDocument();
    expect(screen.getByText(ko.google.writeNotReady(0))).toBeInTheDocument();
    expect(btn(ko.google.writeConnect)).toBeNull();
    expect(screen.queryByText(ko.google.liveWarnTitle)).toBeNull();
    expect(screen.queryByText(ko.google.readOnly)).toBeNull();
    expect(text()).not.toMatch(/영상 제목을 바꾸지 않습니다/);
  });

  it.each([0, 1, 3, 200])('TC-VMF-024 쓰기 연결·꺼짐 상태의 허용 영상 수 %i개가 문구에 그대로 나온다', async (n) => {
    await card(rc({ write_connected: true, live_allowed_count: n }));
    expect(screen.getByText(new RegExp(`수정 허용 영상 ${n}개`))).toBeInTheDocument();
  });

  it('TC-VMF-025 live_allowed_count 가 응답에 없어도(undefined) "undefined"/NaN 대신 0개로 보인다', async () => {
    const s = rc({ write_connected: true });
    delete (s as { live_allowed_count?: number }).live_allowed_count;
    await card(s);
    expect(screen.getByText(/수정 허용 영상 0개/)).toBeInTheDocument();
    expect(text()).not.toMatch(/undefined|NaN|null/);
  });

  it('TC-VMF-026 실제 수정 가능: 경고 제목+허용 영상 수+되돌리기 한계, role=alert, 이전 안내("꺼져 있습니다"·"읽기 전용"·연결 버튼)는 없다', async () => {
    await card(rc({ write_connected: true, live_write_enabled: true, live_allowed_count: 2, live_write_ready: true }));
    const alert = screen.getByText(ko.google.liveWarnTitle).closest('[role="alert"]') as HTMLElement;
    expect(alert).not.toBeNull();
    expect(within(alert).getByText(/수정 허용 영상 2개의 제목이 실제 유튜브에서 바뀝니다/)).toBeInTheDocument();
    expect(within(alert).getByText(/되돌리기를 거부하면 직접 고쳐야 할 수 있습니다/)).toBeInTheDocument();
    expect(text()).not.toMatch(/아직 꺼져 있습니다/);
    expect(text()).not.toMatch(/제목을 바꾸지 않습니다/);
    expect(screen.queryByText(ko.google.writeConnected)).toBeNull();
    expect(btn(ko.google.writeConnect)).toBeNull();
  });

  it('TC-VMF-027 실제 수정 가능이지만 연결 해제는 여전히 가능하고(확인 2단계), 불러오기도 가능하다', async () => {
    await card(rc({ write_connected: true, live_write_enabled: true, live_allowed_count: 1, live_write_ready: true }));
    expect(btn(ko.google.disconnect)).toBeEnabled();
    expect(btn(ko.google.syncReal)).toBeEnabled();
  });

  it('TC-VMF-028 모든 상태 조합(연결·쓰기연결·수정켜짐·허용수·ready)에서 화면 문구가 사실과 모순되지 않는다(속성 시험 64조합)', async () => {
    let n = 0;
    for (const connected of [false, true])
      for (const write of [false, true])
        for (const enabled of [false, true])
          for (const allowed of [0, 2])
            for (const ready of [false, true]) {
              // 서버가 만들 수 있는 조합만: ready = enabled && allowed>0 && write
              if (ready !== (enabled && allowed > 0 && write)) continue;
              n++;
              const s = st({
                connected,
                write_connected: write,
                live_write_enabled: enabled,
                live_allowed_count: allowed,
                live_write_ready: ready,
                message: `조합-${n}`,
              });
              const c = await connectedClient([statusRoute(s)]);
              const r = renderWithApp(<GoogleCard />, c.client);
              await screen.findByText(`조합-${n}`);
              const t = text();
              const label = JSON.stringify({ connected, write, enabled, allowed, ready });
              // 쓰기 연결이 되어 있으면 "읽기 전용(제목을 바꾸지 않음)" 안내가 나오면 거짓
              if (write) expect(t, label).not.toMatch(/영상 제목을 바꾸지 않습니다/);
              // 실제 수정 가능이면 "꺼져 있습니다" 가 나오면 거짓
              if (ready) expect(t, label).not.toMatch(/아직 꺼져 있습니다/);
              // 실제 수정이 가능한데 경고가 안 보이면(읽기 연결이 없는 경우 포함) 안전 결함
              if (ready) expect(screen.queryByText(ko.google.liveWarnTitle), `경고 누락 ${label}`).toBeInTheDocument();
              // 수정이 불가능한데 경고가 보이면 거짓 경고
              if (!ready) expect(screen.queryByText(ko.google.liveWarnTitle), label).toBeNull();
              r.unmount();
            }
    expect(n).toBeGreaterThanOrEqual(10);
  });

  it('TC-VMF-029 실제 수정은 서버에서 켜졌지만(live_write_enabled) 허용 영상이 0개면 "꺼져 있습니다"가 사실인가 — 켜려면 안내가 현재 상태와 맞아야 한다', async () => {
    await card(rc({ write_connected: true, live_write_enabled: true, live_allowed_count: 0, live_write_ready: false }));
    // 사용자는 "수정 켜기"는 이미 했다. 안내가 "YTWEB_LIVE_WRITE=1 이 필요"라고만 하면 이미 한 일을 또 시키는 안내다.
    const t = text();
    const tellsToEnableAgain = /YTWEB_LIVE_WRITE=1/.test(t);
    expect(tellsToEnableAgain, '이미 켜진 설정을 켜라고 안내함').toBe(false);
  });

  it('TC-VMF-030 쓰기 구역 제목·안내에 개발자용 설정 이름이 있으면 비개발자가 실행할 방법도 함께 안내돼야 한다(조작 가능성)', async () => {
    await card(rc({ write_connected: true, live_allowed_count: 0 }));
    const t = text();
    if (/YTWEB_[A-Z_]+/.test(t)) {
      // 설정 파일/스크립트 위치 또는 문서 안내가 같이 있어야 한다
      expect(t, '환경변수 이름만 있고 어디에서 설정하는지 없음').toMatch(/web[\\/]|\.env|start\.ps1|설정 파일|문서|WEB_/);
    }
  });
});

describe('접근성·반응', () => {
  it('TC-VMF-040 모든 대표 상태에서 axe 위반이 없다(미연결/연결/쓰기연결/수정가능)', async () => {
    for (const s of [
      base,
      st({ connected: true }),
      st({ connected: true, write_connected: true }),
      st({ connected: true, write_connected: true, live_write_enabled: true, live_allowed_count: 1, live_write_ready: true }),
    ]) {
      const c = await connectedClient([statusRoute(s)]);
      const r = renderWithApp(<GoogleCard />, c.client);
      await screen.findByText(s.message);
      expect(await axeViolations(r.container)).toEqual([]);
      r.unmount();
    }
  });

  it('TC-VMF-041 상태 확인 중에는 "확인하는 중" 안내만 있고 버튼이 없다', async () => {
    const c = await connectedClient([route('GET', '/api/v1/google/status', () => new Promise<Response>(() => {}))]);
    renderWithApp(<GoogleCard />, c.client);
    expect(await screen.findByText(ko.google.checking)).toBeInTheDocument();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('TC-VMF-042 읽기 전용 문구와 수정 가능 경고가 동시에 보이는 일은 없다(상호 배타)', async () => {
    for (const o of [{}, { write_connected: true }, { write_connected: true, live_write_enabled: true, live_allowed_count: 1, live_write_ready: true }]) {
      const c = await connectedClient([statusRoute(st({ connected: true, ...o }))]);
      const r = renderWithApp(<GoogleCard />, c.client);
      await screen.findByText(base.message);
      const ro = screen.queryByText(ko.google.readOnly) !== null;
      const warn = screen.queryByText(ko.google.liveWarnTitle) !== null;
      expect(ro && warn).toBe(false);
      r.unmount();
    }
  });
});
