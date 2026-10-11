import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { Batch } from '../api/types';
import { draftBatch, suggestion } from '../test/fixtures';
import { connectedClient, json, problem, renderWithApp, route, type Handler } from '../test/utils';
import { BatchDetailPage } from './BatchDetailPage';
import { BatchesPage } from './BatchesPage';

const routes = (
  <Routes>
    <Route path="batches" element={<BatchesPage />} />
    <Route path="batches/:batchId" element={<BatchDetailPage />} />
  </Routes>
);
const approvedSug = (n: number) =>
  suggestion(n, {
    video_id: `vid0000000${n}`,
    title: `승인된 제목 ${n}`,
    status: 'approved',
    approval: {
      approver: '홍',
      approved_at: '2026-10-10T00:00:00Z',
      expires_at: '2026-10-11T00:00:00Z',
    },
  });
const page = (items: unknown[]) =>
  json(200, { items, total: items.length, page: 1, page_size: 20 });
const emptyBatches = route('GET', '/api/v1/batches', () => page([]));

describe('배치 목록·초안', () => {
  it('TC-WF-045 승인 항목을 골라 사전 점검 초안을 만들고, 초안 화면으로 이동한다', async () => {
    const user = userEvent.setup();
    const b = draftBatch();
    const { client, calls } = await connectedClient([
      route('GET', '/api/v1/suggestions', () => page([approvedSug(1), approvedSug(2)])),
      emptyBatches,
      route('POST', '/api/v1/batches', () => json(201, { batch: b, precheck: b.precheck })),
      route('GET', '/api/v1/batches/7', () => json(200, { ...b, precheck: undefined })),
    ]);
    renderWithApp(routes, client, '/batches');
    await screen.findByText('승인된 제목 1');
    const create = screen.getByRole('button', { name: '사전 점검 만들기' });
    expect(create).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: '전체 선택' }));
    await user.click(create);
    const post = await waitFor(() => {
      const c = calls.find((x) => x.method === 'POST' && x.path === '/api/v1/batches');
      expect(c).toBeTruthy();
      return c!;
    });
    expect(post.body).toEqual({ suggestion_ids: [1, 2] });
    expect(post.headers['idempotency-key']).toBeTruthy();
    expect(await screen.findByText('사전 점검(미리보기)')).toBeInTheDocument();
    expect(screen.getByText('실행 2건')).toBeInTheDocument();
  });

  it('TC-WF-046 초안 생성이 실패한 뒤 같은 선택으로 다시 누르면 같은 멱등키를, 선택을 바꾸면 새 키를 쓴다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      route('GET', '/api/v1/suggestions', () => page([approvedSug(1), approvedSug(2)])),
      emptyBatches,
      route('POST', '/api/v1/batches', () => problem(500, 'internal_error', '서버 오류')),
    ]);
    renderWithApp(routes, client, '/batches');
    await screen.findByText('승인된 제목 1');
    await user.click(screen.getByRole('checkbox', { name: '승인된 제목 1 선택' }));
    await user.click(screen.getByRole('button', { name: '사전 점검 만들기' }));
    await screen.findByText('서버 오류');
    await user.click(screen.getByRole('button', { name: '사전 점검 만들기' }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST')).toHaveLength(2));
    await user.click(screen.getByRole('checkbox', { name: '승인된 제목 2 선택' }));
    await user.click(screen.getByRole('button', { name: '사전 점검 만들기' }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST')).toHaveLength(3));
    const k = calls.filter((c) => c.method === 'POST').map((c) => c.headers['idempotency-key']);
    expect(k[0]).toBe(k[1]);
    expect(k[2]).not.toBe(k[0]);
  });

  it('TC-WF-047 한 배치 최대 50건을 넘기면 만들기가 막히고 이유를 알려 준다', async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 51 }, (_, i) => approvedSug(i + 1));
    const { client } = await connectedClient([
      route('GET', '/api/v1/suggestions', () => page(many)),
      emptyBatches,
    ]);
    renderWithApp(routes, client, '/batches');
    await screen.findByText('승인된 제목 1');
    await user.click(screen.getByRole('checkbox', { name: '전체 선택' }));
    expect(screen.getByText(/최대 50건까지입니다. 선택을 줄여 주세요/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '사전 점검 만들기' })).toBeDisabled();
  });

  it('TC-WF-048 승인 항목이 없으면 빈 상태와 다음 행동을 안내한다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/suggestions', () => page([])),
      emptyBatches,
    ]);
    renderWithApp(routes, client, '/batches');
    expect(
      await screen.findByText('배치에 넣을 수 있는 승인된 제안이 없습니다.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/영상 목록에서 제안을 만들고 승인한 뒤/)).toBeInTheDocument();
  });
});

describe('배치 초안 점검·실행', () => {
  const open = async (b: Batch, extra: Handler[] = [], after?: Batch) => {
    let executed = false;
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, executed && after ? after : b)),
      (req) => {
        if (req.method === 'POST' && req.path.endsWith('/execute')) executed = true;
        return undefined;
      },
      ...extra,
    ]);
    renderWithApp(routes, c.client, '/batches/7');
    return c;
  };

  it('TC-WF-049 사전 점검 표에 항목 수·예상 사용량·남은 한도·날짜별 일정·경고·제외 항목이 나온다', async () => {
    const b = draftBatch();
    b.precheck = {
      ...b.precheck!,
      schedule: [
        { date: '2026-10-10', count: 1 },
        { date: '2026-10-11', count: 1 },
      ],
      warnings: ['하루 상한을 넘는 항목은 다음 날로 예약됩니다.'],
      blocked: [{ suggestion_id: 9, reason: '승인이 만료되었습니다.' }],
    };
    await open(b);
    await screen.findByText('사전 점검(미리보기)');
    expect(screen.getByText('반영 대상').nextElementSibling).toHaveTextContent('2건');
    expect(screen.getByText('예상 사용량').nextElementSibling).toHaveTextContent('100 단위');
    expect(screen.getByText('하루 반영 상한').nextElementSibling).toHaveTextContent('10건');
    expect(screen.getByText('남은 API 한도').nextElementSibling).toHaveTextContent('4,800 단위');
    expect(screen.getByText('2026-10-11')).toBeInTheDocument();
    expect(
      screen.getAllByText(/하루 상한을 넘는 항목은 다음 날로 예약됩니다./).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText('제안 9: 승인이 만료되었습니다.')).toBeInTheDocument();
  });

  it('TC-WF-050 확인 문구가 다르면 실행 버튼이 꺼져 있고, 일치하면 켜져서 문구와 멱등키를 보낸다', async () => {
    const user = userEvent.setup();
    const running = draftBatch({ status: 'running' });
    const { calls } = await open(
      draftBatch(),
      [
        route('POST', '/api/v1/batches/7/execute', () =>
          json(202, {
            batch: running,
            job: {
              id: 'j',
              type: 'batch.execute',
              status: 'running',
              progress: 0,
              total: 2,
              error: null,
              result: null,
            },
          }),
        ),
      ],
      running,
    );
    await screen.findByText('실행 확인');
    const exec = screen.getByRole('button', { name: '실행' });
    expect(exec).toBeDisabled();
    const input = screen.getByRole('textbox');
    await user.type(input, '실행 1건');
    expect(exec).toBeDisabled();
    await user.clear(input);
    await user.type(input, '실행 2건');
    expect(exec).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ }));
    expect(exec).toBeEnabled();
    await user.click(exec);
    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/execute'))).toBe(true));
    const c = calls.find((x) => x.path.endsWith('/execute'))!;
    expect(c.body).toEqual({ confirm_text: '실행 2건' });
    expect(c.headers['idempotency-key']).toBeTruthy();
    expect(await screen.findByText('진행 상황')).toBeInTheDocument();
  });

  it('TC-WF-051 실행이 실패한 뒤 다시 눌러도 같은 멱등키를 쓰고 오류를 보여 준다', async () => {
    const user = userEvent.setup();
    const { calls } = await open(draftBatch(), [
      route('POST', '/api/v1/batches/7/execute', () =>
        problem(429, 'daily_cap_exceeded', '오늘 한도에 도달했습니다', '', '내일 다시 실행하세요'),
      ),
    ]);
    await screen.findByText('실행 확인');
    await user.type(screen.getByRole('textbox'), '실행 2건');
    await user.click(screen.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ }));
    await user.click(screen.getByRole('button', { name: '실행' }));
    expect(await screen.findByText('한도에 도달했습니다')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '실행' }));
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/execute'))).toHaveLength(2));
    const keys = calls
      .filter((c) => c.path.endsWith('/execute'))
      .map((c) => c.headers['idempotency-key']);
    expect(keys[0]).toBe(keys[1]);
  });

  it('TC-WF-052 새로고침으로 점검 정보를 잃어도(precheck 없음) 안내하고 항목 수 기준 문구를 쓴다', async () => {
    const b = draftBatch();
    delete b.precheck;
    await open(b);
    expect(
      await screen.findByText('사전 점검 내용을 다시 불러오지 못했습니다'),
    ).toBeInTheDocument();
    expect(screen.getByText('실행 2건')).toBeInTheDocument();
  });

  it('TC-WF-053 반영할 항목이 하나도 없으면 실행 입력 대신 안내만 보여 준다', async () => {
    const b = draftBatch();
    b.precheck = { ...b.precheck!, item_count: 0, confirm_text: '실행 0건' };
    await open(b);
    expect(await screen.findByText(/반영할 수 있는 항목이 없습니다/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '실행' })).toBeNull();
  });
});

describe('배치 진행·중지', () => {
  const running = (success: number): Batch => {
    const b = draftBatch({ status: 'running', precheck: null });
    b.counts = { pending: 2 - success, running: 0, success, failed: 0, skipped: 0, cancelled: 0 };
    b.items.forEach((it, i) => (it.status = i < success ? 'success' : 'pending'));
    return b;
  };

  it('TC-WF-054 새로고침 후에도 서버 상태를 다시 읽어 진행률을 보여 주고, 끝나면 폴링이 멈춘다', async () => {
    let n = 0;
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => {
        n++;
        return json(200, n === 1 ? running(0) : { ...running(2), status: 'completed' });
      }),
    ]);
    renderWithApp(routes, c.client, '/batches/7');
    expect(await screen.findByText('0 / 2건 처리됨')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: '배치 진행률' })).toBeInTheDocument();
    expect(screen.getByText(/2초마다 자동으로 새로 고칩니다/)).toBeInTheDocument();
    expect(await screen.findByText('2 / 2건 처리됨', {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/이 배치는 끝났습니다/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '중지' })).toBeNull();
    const seen = n;
    await new Promise((r) => setTimeout(r, 2300));
    expect(n).toBe(seen);
  }, 15000);

  it('TC-WF-055 중지는 확인 대화상자를 거친 뒤 취소 요청을 보낸다', async () => {
    const user = userEvent.setup();
    const { calls } = await (async () => {
      const c = await connectedClient([
        route('GET', '/api/v1/batches/7', () => json(200, running(1))),
        route('POST', '/api/v1/batches/7/cancel', () =>
          json(200, { ...running(1), status: 'cancelled' }),
        ),
      ]);
      renderWithApp(routes, c.client, '/batches/7');
      return c;
    })();
    await user.click(await screen.findByRole('button', { name: '중지' }));
    expect(calls.some((c) => c.path.endsWith('/cancel'))).toBe(false);
    const dlg = await screen.findByRole('dialog', { name: '배치를 중지할까요?' });
    expect(dlg).toHaveTextContent('진행 중인 항목은 끝까지 처리됩니다');
    await user.click(within(dlg).getByRole('button', { name: '중지하기' }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/cancel'))).toBe(true));
    expect(await screen.findByText('중지했습니다.')).toBeInTheDocument();
  });
});
