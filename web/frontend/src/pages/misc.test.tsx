import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { Change, SettingsData } from '../api/types';
import { dashboard } from '../test/fixtures';
import { connectedClient, json, problem, renderWithApp, route } from '../test/utils';
import { HistoryPage } from './HistoryPage';
import { HomePage } from './HomePage';
import { ReportsPage } from './ReportsPage';
import { SettingsPage } from './SettingsPage';

describe('홈', () => {
  it('TC-WF-056 오늘 반영 건수·남은 사용량·대기열·할 일을 보여 준다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/dashboard', () =>
        json(200, dashboard({ queue: { pending_items: 4, next_run_date: '2026-10-11' } })),
      ),
    ]);
    renderWithApp(<HomePage />, client);
    expect(await screen.findByText('2 / 10건')).toBeInTheDocument();
    expect(screen.getByText('4,800 단위 남음')).toBeInTheDocument();
    expect(screen.getByText('대기 4건')).toBeInTheDocument();
    expect(screen.getByText('다음 실행일 2026-10-11')).toBeInTheDocument();
    expect(screen.getByText('검토할 AI 제안이 3개 영상에 있습니다')).toBeInTheDocument();
    expect(screen.getByText(/승인된 제안 2건을 배치로 묶어/)).toBeInTheDocument();
    expect(screen.getByText(/구글 연결: 데모 모드/)).toBeInTheDocument();
    expect(screen.getByText('실제 반영(라이브): 꺼짐')).toBeInTheDocument();
  });

  it('TC-WF-057 사용량이 80%를 넘으면 경고를 보여 준다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/dashboard', () =>
        json(
          200,
          dashboard({ quota: { used: 5000, limit: 6000, remaining: 1000, pt_date: '2026-10-10' } }),
        ),
      ),
    ]);
    renderWithApp(<HomePage />, client);
    expect(await screen.findByText(/사용량이 80%를 넘었습니다/)).toBeInTheDocument();
  });

  it('TC-WF-058 영상이 없으면 데모 영상 불러오기 버튼을 보여 주고 누르면 요청한다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      route('GET', '/api/v1/dashboard', () =>
        json(
          200,
          dashboard({
            counts: { videos: 0, excluded: 0, suggested: 0, approved: 0, queued: 0, applied: 0 },
          }),
        ),
      ),
      route('POST', '/api/v1/videos/sync', () =>
        json(202, {
          id: 'sj',
          type: 'videos.sync',
          status: 'queued',
          progress: 0,
          total: 4,
          error: null,
          result: null,
        }),
      ),
      route('GET', '/api/v1/jobs/sj', () =>
        json(200, {
          id: 'sj',
          type: 'videos.sync',
          status: 'running',
          progress: 1,
          total: 4,
          error: null,
          result: null,
        }),
      ),
    ]);
    renderWithApp(<HomePage />, client);
    await user.click(await screen.findByRole('button', { name: '데모 영상 불러오기' }));
    await waitFor(() => expect(calls.some((c) => c.path === '/api/v1/videos/sync')).toBe(true));
    expect(await screen.findByText(/1 \/ 4 처리됨/)).toBeInTheDocument();
  });

  it('TC-WF-059 홈 오류(서버 연결 끊김)는 연결 문제로 구분해 보여 준다', async () => {
    const { client } = await connectedClient([
      () => {
        throw new TypeError('Failed to fetch');
      },
    ]);
    renderWithApp(<HomePage />, client);
    expect(
      await screen.findByText('서버 연결이 끊겼습니다', {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.getByText('network_error')).toBeInTheDocument();
  });
});

const chg = (id: number, over: Partial<Change> = {}): Change => ({
  id,
  video_id: 'vid00000001',
  video_title: '테스트 영상 1',
  change_type: 'apply',
  previous_title: '이전 제목',
  new_title: '새 제목',
  result: 'success',
  mode: 'demo',
  approver: '홍',
  applied_at: '2026-10-09T00:00:00Z',
  verified_at: '2026-10-09T00:01:00Z',
  error_code: null,
  rollbackable: true,
  batch_id: 1,
  ...over,
});

describe('이력·롤백', () => {
  const list = (items: Change[]) =>
    route('GET', '/api/v1/changes', () =>
      json(200, { items, total: items.length, page: 1, page_size: 50 }),
    );

  it('TC-WF-060 롤백은 영상 ID 를 직접 입력해 일치할 때만 실행되고, 같은 확인값으로 멱등키를 보낸다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      list([chg(5)]),
      route('POST', '/api/v1/changes/5/rollback', () =>
        json(201, chg(6, { change_type: 'rollback' })),
      ),
    ]);
    renderWithApp(<HistoryPage />, client);
    await user.click(await screen.findByRole('button', { name: /롤백/ }));
    const dlg = await screen.findByRole('dialog', { name: '이 변경을 되돌릴까요?' });
    const submit = within(dlg).getByRole('button', { name: '롤백 실행' });
    expect(submit).toBeDisabled();
    await user.type(within(dlg).getByLabelText(/영상 ID 를 그대로 입력하세요/), 'vid0000000');
    expect(submit).toBeDisabled();
    expect(within(dlg).getByText('문구가 일치하지 않습니다.')).toBeInTheDocument();
    await user.type(within(dlg).getByLabelText(/영상 ID 를 그대로/), '1');
    expect(submit).toBeDisabled(); // 승인자 이름이 아직 비어 있음
    await user.type(within(dlg).getByLabelText('승인자 이름'), '홍길동');
    expect(submit).toBeEnabled();
    await user.click(submit);
    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/rollback'))).toBe(true));
    const c = calls.find((x) => x.path.endsWith('/rollback'))!;
    expect(c.body).toEqual({ typed_video_id: 'vid00000001', approver: '홍길동' });
    expect(c.headers['idempotency-key']).toBeTruthy();
    expect(await screen.findByText('롤백했습니다.')).toBeInTheDocument();
  });

  it('TC-WF-061 되돌릴 수 없는 변경은 롤백 버튼 대신 이유를 보여 준다', async () => {
    const { client } = await connectedClient([list([chg(5, { rollbackable: false })])]);
    renderWithApp(<HistoryPage />, client);
    expect(await screen.findByText('되돌릴 수 없음')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /롤백/ })).toBeNull();
  });

  it('TC-WF-062 이력이 없으면 빈 상태, 롤백이 서버에서 거절되면 사유를 보여 준다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([
      list([chg(5)]),
      route('POST', '/api/v1/changes/5/rollback', () =>
        problem(
          409,
          'not_rollbackable',
          '되돌릴 수 없는 변경입니다',
          '이후에 다른 변경이 있습니다.',
        ),
      ),
    ]);
    renderWithApp(<HistoryPage />, client);
    await user.click(await screen.findByRole('button', { name: /롤백/ }));
    const dlg = await screen.findByRole('dialog');
    await user.type(within(dlg).getByLabelText(/영상 ID 를 그대로/), 'vid00000001');
    await user.type(within(dlg).getByLabelText('승인자 이름'), '홍');
    await user.click(within(dlg).getByRole('button', { name: '롤백 실행' }));
    expect(await within(dlg).findByText('이후에 다른 변경이 있습니다.')).toBeInTheDocument();
  });

  it('TC-WF-063 변경 이력이 없으면 다음 행동을 안내한다', async () => {
    const { client } = await connectedClient([list([])]);
    renderWithApp(<HistoryPage />, client);
    expect(await screen.findByText('아직 변경 이력이 없습니다')).toBeInTheDocument();
    expect(screen.getByText('배치를 실행하면 여기에 기록됩니다.')).toBeInTheDocument();
  });
});

describe('성과 리포트', () => {
  it('TC-WF-064 "데이터 부족"과 서버의 원인 단정 금지 문구를 그대로 노출하고 숫자는 표로 보여 준다', async () => {
    const note = '순차 비교는 다른 요인(시기·노출 차이)의 영향을 받아 원인을 단정할 수 없습니다.';
    const { client } = await connectedClient([
      route('GET', '/api/v1/reports/changes', () =>
        json(200, {
          notes: [note],
          items: [
            {
              video_id: 'v1',
              title: '영상 A',
              status: 'insufficient',
              before: null,
              after: null,
              baseline_missing: true,
              reasons: ['변경 후 집계 기간이 짧습니다.'],
              notes: [],
              metrics: [],
              expected_after_date: '2026-10-25',
            },
            {
              video_id: 'v2',
              title: '영상 B',
              status: 'ok',
              before: null,
              after: null,
              baseline_missing: false,
              reasons: [],
              notes: [],
              expected_after_date: null,
              metrics: [
                { key: 'views', label: '조회수', before: 100, after: 130, delta: 30, pct: 30 },
              ],
            },
          ],
        }),
      ),
    ]);
    renderWithApp(<ReportsPage />, client);
    expect(await screen.findByText(note)).toBeInTheDocument();
    expect(screen.getByText('데이터 부족')).toBeInTheDocument();
    expect(screen.getByText('변경 후 집계 기간이 짧습니다.')).toBeInTheDocument();
    expect(screen.getByText('변경 후 지표 수집 예정일: 2026-10-25')).toBeInTheDocument();
    expect(screen.getByText('+30.0%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'CSV 내보내기' })).toBeInTheDocument();
  });

  it('TC-WF-065 서버가 문구를 주지 않아도 원인 단정 금지 문구를 항상 보여 준다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/reports/changes', () => json(200, { items: [], notes: [] })),
    ]);
    renderWithApp(<ReportsPage />, client);
    expect(await screen.findByText(/원인을 단정할 수 없습니다/)).toBeInTheDocument();
    expect(screen.getByText('비교할 리포트가 없습니다')).toBeInTheDocument();
  });

  it('TC-WF-066 CSV 내보내기 오류는 화면에 알린다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([
      route('GET', '/api/v1/reports/changes', () => json(200, { items: [], notes: [] })),
      route('GET', '/api/v1/reports/export.csv', () =>
        problem(500, 'internal_error', '내보내기에 실패했습니다'),
      ),
    ]);
    renderWithApp(<ReportsPage />, client);
    await user.click(await screen.findByRole('button', { name: 'CSV 내보내기' }));
    expect(await screen.findByText('내보내기에 실패했습니다')).toBeInTheDocument();
  });
});

describe('설정', () => {
  const data: SettingsData = {
    daily_apply_cap: 10,
    suggestions_per_video: 3,
    tone: ['친근하게'],
    pin_enabled: false,
    mode: 'demo',
    read_only: {
      enable_live: false,
      live_allowlist: ['abcdefghijk'],
      note: '화면에서 바꿀 수 없습니다.',
    },
  };

  it('TC-WF-067 라이브 허용과 허용 영상 목록은 읽기 전용으로만 보이고 "이 화면에서는 켤 수 없습니다"를 안내한다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/settings', () => json(200, data)),
    ]);
    renderWithApp(<SettingsPage />, client);
    expect(await screen.findByText('이 화면에서는 켤 수 없는 설정')).toBeInTheDocument();
    expect(screen.getAllByText('이 화면에서는 켤 수 없습니다.').length).toBe(2);
    expect(screen.getByText('꺼짐')).toBeInTheDocument();
    expect(screen.getByText('abcdefghijk')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).toBeNull();
    expect(screen.queryByRole('checkbox', { name: /라이브/ })).toBeNull();
    expect(screen.queryByRole('textbox', { name: /허용/ })).toBeNull();
  });

  it('TC-WF-068 범위를 벗어난 값은 오류 문구와 함께 저장을 막는다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([
      route('GET', '/api/v1/settings', () => json(200, data)),
    ]);
    renderWithApp(<SettingsPage />, client);
    const cap = await screen.findByLabelText('하루 반영 건수 상한');
    await user.clear(cap);
    await user.type(cap, '25');
    expect(screen.getByText('1~20 사이의 숫자를 입력해 주세요.')).toBeInTheDocument();
    expect(cap).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
  });

  it('TC-WF-069 허용된 안전 설정만 PATCH 로 보낸다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      route('GET', '/api/v1/settings', () => json(200, data)),
      route('PATCH', '/api/v1/settings', (r) => json(200, { ...data, ...(r.body as object) })),
    ]);
    renderWithApp(<SettingsPage />, client);
    const cap = await screen.findByLabelText('하루 반영 건수 상한');
    await user.clear(cap);
    await user.type(cap, '5');
    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      daily_apply_cap: 5,
      suggestions_per_video: 3,
      tone: ['친근하게'],
    });
    expect(await screen.findByText('설정을 저장했습니다.')).toBeInTheDocument();
  });

  it('TC-WF-070 PIN 은 숫자 4~12자리·재입력 일치·현재 PIN 입력 시에만 변경되고, 해제는 현재 PIN 확인 대화상자를 거친다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      route('GET', '/api/v1/settings', () => json(200, { ...data, pin_enabled: true })),
      route('PATCH', '/api/v1/settings', () => json(200, { ...data, pin_enabled: true })),
    ]);
    renderWithApp(<SettingsPage />, client, '/settings?tab=pin');
    await screen.findByText('현재 PIN 이 설정되어 있습니다.');
    const submit = screen.getByRole('button', { name: 'PIN 변경' });
    await user.type(screen.getByLabelText('새 PIN'), '12ab');
    expect(screen.getByText('PIN 은 숫자 4~12자리여야 합니다.')).toBeInTheDocument();
    await user.clear(screen.getByLabelText('새 PIN'));
    await user.type(screen.getByLabelText('새 PIN'), '1234');
    await user.type(screen.getByLabelText('PIN 한 번 더 입력'), '12');
    expect(screen.getByText('PIN 이 서로 다릅니다.')).toBeInTheDocument();
    await user.type(screen.getByLabelText('PIN 한 번 더 입력'), '34');
    expect(submit).toBeDisabled(); // 현재 PIN 이 비어 있음
    await user.type(screen.getByLabelText('현재 PIN'), '9999');
    expect(submit).toBeEnabled();
    await user.click(submit);
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
        pin: { action: 'set', new_pin: '1234', current_pin: '9999' },
      }),
    );
    await user.click(await screen.findByRole('button', { name: 'PIN 해제' }));
    const dlg = await screen.findByRole('dialog', { name: 'PIN 을 해제할까요?' });
    expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(1);
    const del = within(dlg).getByRole('button', { name: 'PIN 해제' });
    expect(del).toBeDisabled();
    await user.type(within(dlg).getByLabelText('현재 PIN'), '1234');
    await user.click(del);
    await waitFor(() =>
      expect(calls.filter((c) => c.method === 'PATCH').at(-1)?.body).toEqual({
        pin: { action: 'clear', current_pin: '1234' },
      }),
    );
  });

  it('TC-WF-094 PIN 이 없을 때 새 PIN 설정은 현재 PIN 없이 보낸다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      route('GET', '/api/v1/settings', () => json(200, data)),
      route('PATCH', '/api/v1/settings', () => json(200, { ...data, pin_enabled: true })),
    ]);
    renderWithApp(<SettingsPage />, client, '/settings?tab=pin');
    await screen.findByText('현재 PIN 이 설정되어 있지 않습니다.');
    expect(screen.queryByLabelText('현재 PIN')).toBeNull();
    await user.type(screen.getByLabelText('새 PIN'), '246810');
    await user.type(screen.getByLabelText('PIN 한 번 더 입력'), '246810');
    await user.click(screen.getByRole('button', { name: 'PIN 설정' }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
        pin: { action: 'set', new_pin: '246810' },
      }),
    );
  });

  it('TC-WF-095 말투는 쉼표로 구분한 목록(최대 5개, 각 20자)으로 보내고 규칙을 어기면 저장을 막는다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      route('GET', '/api/v1/settings', () => json(200, data)),
      route('PATCH', '/api/v1/settings', (r) => json(200, { ...data, ...(r.body as object) })),
    ]);
    renderWithApp(<SettingsPage />, client);
    const tone = await screen.findByLabelText('제목 말투');
    await user.clear(tone);
    await user.type(tone, '가,나,다,라,마,바');
    expect(screen.getByText('말투는 최대 5개까지입니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
    await user.clear(tone);
    await user.type(tone, '차분하게, 정보 전달');
    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.body).toMatchObject({
        tone: ['차분하게', '정보 전달'],
      }),
    );
  });

  it('TC-WF-071 감사 로그 탭은 읽기 전용이며 무결성 결과를 글자로 알린다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/audit', () =>
        json(200, {
          items: [
            {
              id: 1,
              ts: '2026-10-10T00:00:00Z',
              actor: 'local-user',
              action: 'session.create',
              target_type: 'session',
              target_id: 'ab',
              detail: {},
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
          chain_ok: true,
        }),
      ),
    ]);
    renderWithApp(<SettingsPage />, client, '/settings?tab=audit');
    expect(await screen.findByText('session.create')).toBeInTheDocument();
    expect(screen.getByText('기록 무결성 확인됨')).toBeInTheDocument();
  });
});
