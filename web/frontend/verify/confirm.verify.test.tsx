// 06단계 독립 검증(TC-VF) — 위험 동작 확인 단계: 배치 실행 확인 문구, 롤백 영상 ID, 승인 규칙, 제목 수정
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { Change, Suggestion, VideoDetail } from '../src/api/types';
import { BatchDetailPage } from '../src/pages/BatchDetailPage';
import { HistoryPage } from '../src/pages/HistoryPage';
import { VideoDetailPage } from '../src/pages/VideoDetailPage';
import { detail, draftBatch, suggestion } from '../src/test/fixtures';
import { connectedClient, json, problem, renderWithApp, route, type Handler } from '../src/test/utils';

// ---------- 배치 실행 확인 문구 ----------
const batchUi = (
  <Routes>
    <Route path="batches/:batchId" element={<BatchDetailPage />} />
  </Routes>
);
async function goBatch(batch = draftBatch(), extra: Handler[] = []) {
  const c = await connectedClient([
    // 실행 요청이 지나간 뒤에는 서버가 running 으로 답하는 것처럼 흉내 낸다
    (req) =>
      req.method === 'GET' && req.path === '/api/v1/batches/7'
        ? json(200, executed ? draftBatch({ status: 'running' }) : batch)
        : undefined,
    ...extra,
  ]);
  executed = false;
  renderWithApp(batchUi, c.client, '/batches/7');
  await screen.findByLabelText(/확인 문구 입력/);
  return c;
}
let executed = false;
const execBtn = () => screen.getByRole('button', { name: '실행' });
const phraseBox = () => screen.getByLabelText(/확인 문구 입력/);

describe('배치 실행 확인 문구 (F-06, W-009)', () => {
  it.each([
    ['뒤 공백', '실행 2건 '],
    ['앞 공백', ' 실행 2건'],
    ['공백 없음', '실행2건'],
    ['공백 두 칸', '실행  2건'],
    ['건수 불일치', '실행 3건'],
    ['건수 불일치(1)', '실행 1건'],
    ['전각 숫자', '실행 ２건'],
    ['전각(표의) 공백', '실행　2건'],
    ['마침표 덧붙임', '실행 2건.'],
    ['일부만', '실행'],
    ['숫자만', '2건'],
    ['두 번 붙여넣기', '실행 2건실행 2건'],
    ['NFD(자모 분해) 입력', '실행 2건'.normalize('NFD')],
    ['제로폭 공백 삽입', '실행​ 2건'],
    ['영문 흉내', 'Run 2'],
  ])('TC-VF-@@@ 확인 문구가 정확히 같지 않으면(%s) 실행 버튼이 꺼져 있고 눌러도 요청이 가지 않는다', async (_n, typed) => {
    const { calls } = await goBatch();
    fireEvent.change(phraseBox(), { target: { value: typed } });
    expect(execBtn()).toBeDisabled();
    fireEvent.click(execBtn());
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(calls.some((c) => c.path.endsWith('/execute'))).toBe(false);
  });

  it('TC-VF-@@@ 정확히 "실행 2건" 을 입력하면 켜지고, 한 번 누르면 문구 그대로 + Idempotency-Key 와 함께 한 번만 전송된다', async () => {
    const user = userEvent.setup();
    const { calls } = await goBatch(draftBatch(), [
      route('POST', '/api/v1/batches/7/execute', () => {
        executed = true;
        return json(202, {
          batch: draftBatch({ status: 'running' }),
          job: { id: 'j', type: 'batch.execute', status: 'queued', progress: 0, total: 2, error: null, result: null },
        });
      }),
    ]);
    await user.type(phraseBox(), '실행 2건');
    expect(execBtn()).toBeEnabled();
    await user.click(execBtn());
    await screen.findByText(/처리됨/);
    const ex = calls.filter((c) => c.path === '/api/v1/batches/7/execute');
    expect(ex).toHaveLength(1);
    expect(ex[0]?.body).toEqual({ confirm_text: '실행 2건' });
    expect(ex[0]?.headers['idempotency-key']).toBeTruthy();
    expect(ex[0]?.headers['x-csrf-token']).toBe('csrf-1');
  });

  it('TC-VF-@@@ 빠른 더블클릭·연타에도 실행 요청은 한 번만 간다(중복 클릭 방지)', async () => {
    const user = userEvent.setup();
    let release: (() => void) | undefined;
    const gate = new Promise<void>((r) => (release = r));
    const { calls } = await goBatch(draftBatch(), [
      route('POST', '/api/v1/batches/7/execute', async () => {
        await gate;
        executed = true;
        return json(202, { batch: draftBatch({ status: 'running' }), job: { id: 'j', type: 't', status: 'queued', progress: 0, total: 2, error: null, result: null } });
      }),
    ]);
    await user.type(phraseBox(), '실행 2건');
    const b = execBtn();
    await user.dblClick(b);
    fireEvent.click(b);
    fireEvent.click(b);
    await waitFor(() => expect(b).toBeDisabled());
    release?.();
    await screen.findByText(/처리됨/);
    expect(calls.filter((c) => c.path === '/api/v1/batches/7/execute')).toHaveLength(1);
  });

  it('TC-VF-@@@ 확인 문구 입력칸에서 Enter 를 눌러도 실행되지 않는다(버튼만이 실행 경로)', async () => {
    const user = userEvent.setup();
    const { calls } = await goBatch();
    await user.type(phraseBox(), '실행 2건{Enter}');
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(calls.some((c) => c.path.endsWith('/execute'))).toBe(false);
  });

  it('TC-VF-@@@ 서버가 준 확인 문구(실행 5건)를 기준으로 하며, 화면의 항목 수(2건)를 임의로 쓰지 않는다', async () => {
    const b = draftBatch();
    b.precheck = { ...b.precheck!, item_count: 5, confirm_text: '실행 5건' };
    await goBatch(b);
    fireEvent.change(phraseBox(), { target: { value: '실행 2건' } });
    expect(execBtn()).toBeDisabled();
    fireEvent.change(phraseBox(), { target: { value: '실행 5건' } });
    expect(execBtn()).toBeEnabled();
  });

  it('TC-VF-@@@ 일치 안내는 글자(✓/✕)로 나오고, 고쳐 쓰면 다시 꺼진다', async () => {
    const user = userEvent.setup();
    await goBatch();
    await user.type(phraseBox(), '실행 2건');
    expect(screen.getByText('✓ 문구가 일치합니다.')).toBeInTheDocument();
    await user.type(phraseBox(), 'x');
    expect(screen.getByText('✕ 문구가 일치하지 않습니다.')).toBeInTheDocument();
    expect(execBtn()).toBeDisabled();
  });

  it('TC-VF-@@@ 서버가 확인 문구 불일치(422/409)를 돌려주면 사유를 보여 주고 버튼은 다시 쓸 수 있다', async () => {
    const user = userEvent.setup();
    await goBatch(draftBatch(), [
      route('POST', '/api/v1/batches/7/execute', () => problem(409, 'confirm_text_mismatch', '확인 문구가 다릅니다', '서버가 기대한 문구와 다릅니다', '화면을 새로고침하세요')),
    ]);
    await user.type(phraseBox(), '실행 2건');
    await user.click(execBtn());
    expect((await screen.findAllByText('확인 문구가 다릅니다')).length).toBeGreaterThan(0);
    expect(screen.getByText('confirm_text_mismatch')).toBeInTheDocument();
    expect(execBtn()).toBeEnabled();
  });

  it('TC-VF-@@@ 실행이 실패한 뒤 그대로 다시 눌러 재시도하면 같은 Idempotency-Key 를 쓴다(이중 실행 방지)', async () => {
    const user = userEvent.setup();
    const { calls } = await goBatch(draftBatch(), [
      route('POST', '/api/v1/batches/7/execute', () => problem(500, 'boom', '서버 오류')),
    ]);
    await user.type(phraseBox(), '실행 2건');
    await user.click(execBtn());
    await screen.findByText('boom');
    await user.click(execBtn());
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/execute'))).toHaveLength(2));
    await user.click(execBtn());
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/execute'))).toHaveLength(3));
    const keys = calls.filter((c) => c.path.endsWith('/execute')).map((c) => c.headers['idempotency-key']);
    expect(new Set(keys).size).toBe(1);
    expect(keys[0]).toBeTruthy();
  });

  it('TC-VF-@@@ 반영할 항목이 0건이면 확인 문구 입력칸 자체가 없다', async () => {
    const b = draftBatch({ items: [] });
    b.precheck = { ...b.precheck!, item_count: 0, confirm_text: '실행 0건' };
    const c = await connectedClient([route('GET', '/api/v1/batches/7', () => json(200, b))]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByText(/사전 점검/);
    expect(screen.queryByLabelText(/확인 문구 입력/)).toBeNull();
    expect(screen.queryByRole('button', { name: '실행' })).toBeNull();
  });

  it('TC-VF-@@@ 이미 실행 중/끝난 배치에는 실행 입력이 없고, 숫자 id 가 아닌 주소는 "없음" 안내로 간다', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch({ status: 'completed', counts: { pending: 0, running: 0, success: 2, failed: 0, skipped: 0, cancelled: 0 } }))),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByText('이 배치는 끝났습니다.');
    expect(screen.queryByLabelText(/확인 문구 입력/)).toBeNull();
    const c2 = await connectedClient([]);
    const { unmount } = renderWithApp(batchUi, c2.client, '/batches/abc');
    expect(await screen.findAllByText(/찾을 수 없|없습니다/)).not.toHaveLength(0);
    expect(c2.calls.some((x) => x.path.startsWith('/api/v1/batches/'))).toBe(false);
    unmount();
  });
});

// ---------- 롤백 영상 ID 확인 ----------
const VID = 'AbC_123-xyZ';
const change = (over: Partial<Change> = {}): Change => ({
  id: 5,
  video_id: VID,
  video_title: '롤백 대상 영상',
  change_type: 'apply',
  previous_title: '이전 제목',
  new_title: '바뀐 제목',
  result: 'success',
  mode: 'demo',
  approver: '홍길동',
  applied_at: '2026-10-10T00:00:00Z',
  verified_at: '2026-10-10T00:01:00Z',
  error_code: null,
  rollbackable: true,
  batch_id: 7,
  ...over,
});
async function goHistory(extra: Handler[] = [], ch: Change[] = [change()]) {
  const c = await connectedClient([
    route('GET', '/api/v1/changes', () => json(200, { items: ch, total: ch.length, page: 1, page_size: 50 })),
    ...extra,
  ]);
  renderWithApp(<HistoryPage />, c.client, '/history');
  await screen.findByRole('link', { name: '롤백 대상 영상' });
  return c;
}
const openRb = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByRole('button', { name: /롤백/ }));
  return await screen.findByRole('dialog');
};
const rbSubmit = () => screen.getByRole('button', { name: '롤백 실행' });
const typedBox = (d: HTMLElement) => within(d).getByLabelText(/영상 ID 를 그대로 입력/);
const approverBox = (d: HTMLElement) => within(d).getByLabelText('승인자 이름');

describe('롤백 영상 ID 직접 입력 (F-06, W-011)', () => {
  it.each([
    ['소문자로 바꿈', VID.toLowerCase()],
    ['대문자로 바꿈', VID.toUpperCase()],
    ['뒤 공백', `${VID} `],
    ['앞 공백', ` ${VID}`],
    ['전각 문자', 'ＡｂＣ＿１２３－ｘｙＺ'],
    ['일부만', VID.slice(0, 5)],
    ['한 글자 더', `${VID}x`],
    ['하이픈을 전각 대시로', VID.replace('-', '–')],
    ['제로폭 공백 삽입', `AbC​_123-xyZ`],
    ['빈 값', ''],
    ['다른 영상 ID', 'ZzZ_999-abC'],
  ])('TC-VF-@@@ 영상 ID 가 정확히 같지 않으면(%s) 롤백 실행이 꺼져 있고 요청이 가지 않는다', async (_n, typed) => {
    const user = userEvent.setup();
    const { calls } = await goHistory();
    const d = await openRb(user);
    fireEvent.change(approverBox(d), { target: { value: '홍길동' } });
    fireEvent.change(typedBox(d), { target: { value: typed } });
    expect(rbSubmit()).toBeDisabled();
    fireEvent.click(rbSubmit());
    fireEvent.submit(d.querySelector('form')!); // 엔터 키 제출 경로
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(calls.some((c) => c.path.endsWith('/rollback'))).toBe(false);
  });

  it('TC-VF-@@@ ID 가 정확히 같아도 승인자가 비었거나 공백뿐이면 실행할 수 없다', async () => {
    const user = userEvent.setup();
    const { calls } = await goHistory();
    const d = await openRb(user);
    fireEvent.change(typedBox(d), { target: { value: VID } });
    fireEvent.change(approverBox(d), { target: { value: '' } });
    expect(rbSubmit()).toBeDisabled();
    fireEvent.change(approverBox(d), { target: { value: '   ' } });
    expect(rbSubmit()).toBeDisabled();
    fireEvent.submit(d.querySelector('form')!);
    expect(calls.some((c) => c.path.endsWith('/rollback'))).toBe(false);
  });

  it('TC-VF-@@@ 정상 입력이면 입력한 ID·공백을 다듬은 승인자·멱등키·CSRF 와 함께 한 번 전송된다', async () => {
    const user = userEvent.setup();
    const { calls } = await goHistory([route('POST', '/api/v1/changes/5/rollback', () => json(201, change({ id: 6, change_type: 'rollback' })))]);
    const d = await openRb(user);
    await user.type(typedBox(d), VID);
    fireEvent.change(approverBox(d), { target: { value: '  홍길동  ' } });
    expect(rbSubmit()).toBeEnabled();
    await user.click(rbSubmit());
    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/rollback'))).toBe(true));
    const rb = calls.filter((c) => c.path === '/api/v1/changes/5/rollback');
    expect(rb).toHaveLength(1);
    expect(rb[0]?.body).toEqual({ typed_video_id: VID, approver: '홍길동' });
    expect(rb[0]?.headers['idempotency-key']).toBeTruthy();
    expect(rb[0]?.headers['x-csrf-token']).toBe('csrf-1');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('TC-VF-@@@ 서버가 거절(409 later_change_exists)하면 대화상자를 닫지 않고 사유를 보여 준다', async () => {
    const user = userEvent.setup();
    await goHistory([route('POST', '/api/v1/changes/5/rollback', () => problem(409, 'later_change_exists', '이후 변경이 있어 되돌릴 수 없습니다', '', '최근 변경부터 되돌리세요'))]);
    const d = await openRb(user);
    await user.type(typedBox(d), VID);
    fireEvent.change(approverBox(d), { target: { value: '나' } });
    await user.click(rbSubmit());
    expect(await within(d).findByText('이후 변경이 있어 되돌릴 수 없습니다')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(rbSubmit()).toBeEnabled();
  });

  it('TC-VF-@@@ 실패 후 같은 입력으로 재시도하면 같은 멱등키, 승인자 이름을 바꾸면 새 키를 쓴다', async () => {
    const user = userEvent.setup();
    const { calls } = await goHistory([route('POST', '/api/v1/changes/5/rollback', () => problem(500, 'boom', '서버 오류'))]);
    const d = await openRb(user);
    await user.type(typedBox(d), VID);
    fireEvent.change(approverBox(d), { target: { value: '나' } });
    await user.click(rbSubmit());
    await within(d).findByRole('alert');
    await user.click(rbSubmit());
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/rollback'))).toHaveLength(2));
    fireEvent.change(approverBox(d), { target: { value: '나2' } });
    await user.click(rbSubmit());
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/rollback'))).toHaveLength(3));
    const k = calls.filter((c) => c.path.endsWith('/rollback')).map((c) => c.headers['idempotency-key']);
    expect(k[1]).toBe(k[0]);
    expect(k[2]).not.toBe(k[0]);
  });

  it('TC-VF-@@@ 더블클릭해도 롤백 요청은 한 번이고, 처리 중에는 Esc 로 닫히지 않는다', async () => {
    const user = userEvent.setup();
    let release: (() => void) | undefined;
    const gate = new Promise<void>((r) => (release = r));
    const { calls } = await goHistory([
      route('POST', '/api/v1/changes/5/rollback', async () => {
        await gate;
        return json(201, change({ id: 6 }));
      }),
    ]);
    const d = await openRb(user);
    await user.type(typedBox(d), VID);
    fireEvent.change(approverBox(d), { target: { value: '나' } });
    await user.dblClick(rbSubmit());
    await user.keyboard('{Escape}');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    release?.();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(calls.filter((c) => c.path.endsWith('/rollback'))).toHaveLength(1);
  });

  it('TC-VF-@@@ Esc 로 닫으면 롤백 버튼으로 포커스가 돌아가고, 다시 열면 이전에 입력한 ID 가 비어 있다', async () => {
    const user = userEvent.setup();
    await goHistory();
    const opener = screen.getByRole('button', { name: /롤백/ });
    const d = await openRb(user);
    await user.type(typedBox(d), VID);
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(opener).toHaveFocus();
    const d2 = await openRb(user);
    expect(typedBox(d2)).toHaveValue('');
  });

  it('TC-VF-@@@ 되돌릴 수 없는 항목(rollbackable=false)에는 롤백 버튼이 없다', async () => {
    await goHistory([], [change({ rollbackable: false })]);
    expect(screen.queryByRole('button', { name: /롤백/ })).toBeNull();
  });
});

// ---------- 승인·반려·제목 수정 ----------
const ui = (
  <Routes>
    <Route path="videos/:videoId" element={<VideoDetailPage />} />
  </Routes>
);
async function goDetail(list: Suggestion[], extra: Handler[] = [], over: Partial<VideoDetail> = {}) {
  const c = await connectedClient([route('GET', '/api/v1/videos/vid00000001', () => json(200, detail(list, over))), ...extra]);
  renderWithApp(ui, c.client, '/videos/vid00000001');
  await screen.findByText(list[0]!.title, { selector: 'h3' });
  return c;
}
const warnS = suggestion(2, {
  title: '경고 제목 후보',
  validation_result: 'warn',
  reasons: [{ code: 'risky', severity: 'warn', message: '과장 표현 가능' }],
});
const blockS = suggestion(3, {
  title: '차단 제목 후보',
  validation_result: 'block',
  reasons: [{ code: 'banned', severity: 'block', message: '금칙어 포함' }],
});
const passS = suggestion(1, { title: '통과 제목 후보' });
const cardOf = (title: string) => screen.getByRole('heading', { name: title, level: 3 }).closest('article') as HTMLElement;

describe('승인 규칙 (W-005, W-007)', () => {
  it.each([
    ['검토 대기', 'candidate'],
    ['승인 만료', 'expired'],
  ])('TC-VF-@@@ 차단 판정 제안은 상태가 %s 여도 승인 버튼이 꺼져 있고 눌러도 대화상자·요청이 없다', async (_n, status) => {
    const user = userEvent.setup();
    const { calls } = await goDetail([{ ...blockS, status }]);
    const btn = within(cardOf('차단 제목 후보')).getByRole('button', { name: '승인' });
    expect(btn).toBeDisabled();
    await user.click(btn);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false);
  });

  it('TC-VF-@@@ 경고 제안: 사유 확인 체크 전에는 승인할 수 없고(버튼·Enter 모두), 체크를 풀면 다시 막힌다', async () => {
    const user = userEvent.setup();
    const { calls } = await goDetail([warnS]);
    await user.click(within(cardOf('경고 제목 후보')).getByRole('button', { name: '승인' }));
    const d = await screen.findByRole('dialog');
    const submit = within(d).getByRole('button', { name: '승인' });
    fireEvent.change(within(d).getByLabelText(/승인자/), { target: { value: '나' } });
    fireEvent.submit(d.querySelector('form')!);
    expect(submit).toBeDisabled();
    expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false);
    const chk = within(d).getByRole('checkbox');
    await user.click(chk);
    expect(submit).toBeEnabled();
    await user.click(chk);
    expect(submit).toBeDisabled();
  });

  it('TC-VF-@@@ 경고 제안도 확인·승인자 입력 뒤에는 승인되고, 승인자 이름은 공백을 다듬어 보낸다', async () => {
    const user = userEvent.setup();
    const { calls } = await goDetail([warnS], [route('POST', '/api/v1/suggestions/2/approve', () => json(200, { ...warnS, status: 'approved' }))]);
    await user.click(within(cardOf('경고 제목 후보')).getByRole('button', { name: '승인' }));
    const d = await screen.findByRole('dialog');
    fireEvent.change(within(d).getByLabelText(/승인자/), { target: { value: '  김검토  ' } });
    await user.click(within(d).getByRole('checkbox'));
    await user.click(within(d).getByRole('button', { name: '승인' }));
    await waitFor(() => expect(calls.some((c) => c.path === '/api/v1/suggestions/2/approve')).toBe(true));
    expect(calls.find((c) => c.path === '/api/v1/suggestions/2/approve')?.body).toEqual({ approver: '김검토' });
  });

  it('TC-VF-@@@ 통과 제안이라도 승인자가 비었거나 공백뿐이면 승인할 수 없다', async () => {
    const user = userEvent.setup();
    const { calls } = await goDetail([passS]);
    await user.click(within(cardOf('통과 제목 후보')).getByRole('button', { name: '승인' }));
    const d = await screen.findByRole('dialog');
    const submit = within(d).getByRole('button', { name: '승인' });
    fireEvent.change(within(d).getByLabelText(/승인자/), { target: { value: '' } });
    expect(submit).toBeDisabled();
    fireEvent.change(within(d).getByLabelText(/승인자/), { target: { value: '   ' } });
    fireEvent.submit(d.querySelector('form')!);
    expect(submit).toBeDisabled();
    expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false);
  });

  it('TC-VF-@@@ 이미 승인/반려된 제안에는 알맞은 버튼만 보인다(승인됨: 승인 없음·반려 있음, 반려됨: 둘 다 없음)', async () => {
    await goDetail([
      { ...passS, id: 11, title: '승인된 후보', status: 'approved', approval: { approver: '나', approved_at: '2026-10-10T00:00:00Z', expires_at: '2026-10-11T00:00:00Z' } },
      { ...passS, id: 12, title: '반려된 후보', status: 'rejected' },
    ]);
    const a = within(cardOf('승인된 후보'));
    expect(a.queryByRole('button', { name: '승인' })).toBeNull();
    expect(a.getByRole('button', { name: '반려' })).toBeInTheDocument();
    const r = within(cardOf('반려된 후보'));
    expect(r.queryByRole('button', { name: '승인' })).toBeNull();
    expect(r.queryByRole('button', { name: '반려' })).toBeNull();
    expect(r.queryByRole('button', { name: /수정/ })).toBeNull();
  });

  it('TC-VF-@@@ 반려: 확인 대화상자에서 취소하면 요청이 없고, 확인해야만 전송된다', async () => {
    const user = userEvent.setup();
    const { calls } = await goDetail([passS], [route('POST', '/api/v1/suggestions/1/reject', () => json(200, { ...passS, status: 'rejected' }))]);
    await user.click(within(cardOf('통과 제목 후보')).getByRole('button', { name: '반려' }));
    let d = await screen.findByRole('dialog');
    await user.click(within(d).getByRole('button', { name: '취소' }));
    expect(calls.some((c) => c.path.endsWith('/reject'))).toBe(false);
    await user.click(within(cardOf('통과 제목 후보')).getByRole('button', { name: '반려' }));
    d = await screen.findByRole('dialog');
    await user.click(within(d).getByRole('button', { name: '반려' }));
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/reject'))).toHaveLength(1));
  });

  it('TC-VF-@@@ 서버가 승인을 409 suggestion_blocked 로 거절해도 화면이 깨지지 않고 사유를 보여 준다', async () => {
    const user = userEvent.setup();
    await goDetail([passS], [route('POST', '/api/v1/suggestions/1/approve', () => problem(409, 'suggestion_blocked', '차단된 제안입니다'))]);
    await user.click(within(cardOf('통과 제목 후보')).getByRole('button', { name: '승인' }));
    const d = await screen.findByRole('dialog');
    fireEvent.change(within(d).getByLabelText(/승인자/), { target: { value: '나' } });
    await user.click(within(d).getByRole('button', { name: '승인' }));
    expect(await within(d).findByText('차단된 제안입니다')).toBeInTheDocument();
  });
});

describe('제목 수정 경계값 (100자)', () => {
  const editOpen = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(within(cardOf('통과 제목 후보')).getByRole('button', { name: /수정/ }));
    const d = await screen.findByRole('dialog');
    return { d, input: within(d).getByRole('textbox'), save: within(d).getByRole('button', { name: '저장' }) };
  };
  it.each([
    ['100자(경계 안)', '가'.repeat(100), true],
    ['101자(경계 밖)', '가'.repeat(101), false],
    ['이모지 100개(UTF-16 200 단위, 코드포인트 100)', '😀'.repeat(100), true],
    ['이모지 101개', '😀'.repeat(101), false],
    ['공백뿐', '     ', false],
    ['앞뒤 공백 포함 원래와 같은 제목', '  통과 제목 후보  ', false],
    ['앞뒤 공백 포함 100자', ` ${'나'.repeat(100)} `, true],
  ])('TC-VF-@@@ 제목 길이/내용 경계: %s', async (_n, text, enabled) => {
    const user = userEvent.setup();
    await goDetail([passS]);
    const { input, save } = await editOpen(user);
    fireEvent.change(input, { target: { value: text } });
    if (enabled) expect(save).toBeEnabled();
    else expect(save).toBeDisabled();
  });

  it('TC-VF-@@@ 저장하면 공백을 다듬은 제목을 PATCH 로 보낸다', async () => {
    const user = userEvent.setup();
    const { calls } = await goDetail([passS], [route('PATCH', '/api/v1/suggestions/1', () => json(200, { ...passS, title: '새 제목' }))]);
    const { input, save } = await editOpen(user);
    fireEvent.change(input, { target: { value: '  새 제목  ' } });
    await user.click(save);
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')).toBeTruthy());
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ title: '새 제목' });
  });
});
