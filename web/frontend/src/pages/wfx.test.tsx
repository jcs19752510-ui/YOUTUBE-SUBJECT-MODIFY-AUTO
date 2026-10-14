// 수정 단위 W-FIX-FE(2026-10-11): 면책·AI 고지(DEF-9-007·008, DEF-7-011), 차단 카드(C-1), 초안 버리기(C-2),
// 이력 결과 값·영어 오류(DEF-7-010), 토스트·감사 로그·체크박스·제외 항목 제목·홈 새로고침(Low 묶음)
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/client';
import type { Batch, Change, Suggestion } from '../api/types';
import { App } from '../app/App';
import { ToastProvider, useToast } from '../components';
import { describeError } from '../components/ErrorPanel';
import { ko } from '../i18n/ko';
import { dashboard, detail, draftBatch, suggestion, video } from '../test/fixtures';
import { connectedClient, json, problem, renderWithApp, route } from '../test/utils';
import { BatchDetailPage } from './BatchDetailPage';
import { BatchesPage } from './BatchesPage';
import { HistoryPage } from './HistoryPage';
import { HomePage } from './HomePage';
import { ReportsPage } from './ReportsPage';
import { SettingsPage } from './SettingsPage';
import { VideoDetailPage } from './VideoDetailPage';
import { VideosPage } from './VideosPage';

const CLI_DISCLAIMER = '이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.';
const AB_BOX = () => screen.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ });
const page = (items: unknown[]) =>
  json(200, { items, total: items.length, page: 1, page_size: 20 });

const videoUi = (
  <Routes>
    <Route path="videos/:videoId" element={<VideoDetailPage />} />
  </Routes>
);
const batchUi = (
  <Routes>
    <Route path="batches" element={<BatchesPage />} />
    <Route path="batches/:batchId" element={<BatchDetailPage />} />
  </Routes>
);
const openVideo = async (suggestions: Suggestion[]) => {
  const c = await connectedClient([
    route('GET', '/api/v1/videos/vid00000001', () => json(200, detail(suggestions))),
    route('PATCH', /^\/api\/v1\/suggestions\/\d+$/, (r) =>
      json(200, suggestion(1, { title: (r.body as { title: string }).title })),
    ),
    route('POST', /^\/api\/v1\/suggestions\/\d+\/reject$/, () =>
      json(200, suggestion(1, { status: 'rejected' })),
    ),
  ]);
  renderWithApp(videoUi, c.client, '/videos/vid00000001');
  return c;
};
const cardOf = (id: number) =>
  document.querySelector<HTMLElement>(`#sg-${id}`)!.closest('article') as HTMLElement;

describe('면책·AI 고지 문구 (DEF-9-007·008, POL-002·006·008·013)', () => {
  it('TC-WFX-001 문구는 ko.ts 한 곳에 있고 면책 문장은 CLI·서버와 한 글자도 다르지 않다', () => {
    expect(ko.legal.disclaimer).toBe(CLI_DISCLAIMER);
    expect(ko.legal.aiNotice).toMatch(/AI가 생성한 제안/);
    expect(ko.legal.aiLimit).toMatch(/표시·광고/);
    expect(ko.legal.aiLimit).toMatch(/보장하지/);
    expect(ko.legal.abConfirm).toMatch(/A\/B 테스트 중이 아님/);
  });

  it('TC-WFX-002 모든 화면 아래에 면책·AI 안내 푸터가 항상 있다(홈, 없는 주소)', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
    ]);
    renderWithApp(<App />, client, '/');
    await screen.findByRole('heading', { name: '홈' });
    const foot = screen.getByRole('contentinfo', { name: ko.legal.footerLabel });
    expect(within(foot).getByText(CLI_DISCLAIMER)).toBeInTheDocument();
    expect(within(foot).getByText(ko.legal.aiNotice)).toBeInTheDocument();
  });

  it('TC-WFX-003 AI 제안 카드에는 AI 생성 고지와 한계·표시광고 안내가 있고, 직접 수정한 제안은 AI 고지가 빠진다', async () => {
    await openVideo([
      suggestion(1, { source: 'ai:mock' }),
      suggestion(2, { source: 'manual', title: '직접 고친 제목' }),
    ]);
    await screen.findByText('직접 고친 제목');
    expect(within(cardOf(1)).getByText(ko.legal.aiNotice)).toBeInTheDocument();
    expect(within(cardOf(1)).getByText(ko.legal.aiLimit)).toBeInTheDocument();
    expect(within(cardOf(2)).queryByText(ko.legal.aiNotice)).toBeNull();
    expect(within(cardOf(2)).getByText(ko.legal.aiLimit)).toBeInTheDocument();
  });

  it('TC-WFX-004 건강·금융(엄격 모드) 카드에만 눈에 띄는 주의 문구가 붙는다', async () => {
    await openVideo([
      suggestion(1, { strict: false }),
      suggestion(2, { strict: true, validation_result: 'pass', title: '금융 제목' }),
    ]);
    await screen.findByText('금융 제목');
    expect(within(cardOf(1)).queryByText(ko.legal.strictCaution)).toBeNull();
    expect(within(cardOf(2)).getByText(ko.legal.strictCaution)).toBeInTheDocument();
    expect(within(cardOf(2)).getByText(ko.suggestion.strictHint)).toBeInTheDocument();
  });

  it('TC-WFX-005 승인 대화상자에 AI 고지·한계·면책이 함께 보인다', async () => {
    const user = userEvent.setup();
    await openVideo([suggestion(1, { strict: true })]);
    await user.click(
      await within(await screen.findByRole('article')).findByRole('button', { name: '승인' }),
    );
    const dlg = await screen.findByRole('dialog', { name: ko.suggestion.approveTitle });
    expect(within(dlg).getByText(ko.legal.aiNotice)).toBeInTheDocument();
    expect(within(dlg).getByText(ko.legal.aiLimit)).toBeInTheDocument();
    expect(within(dlg).getByText(ko.legal.strictCaution)).toBeInTheDocument();
    expect(within(dlg).getByText(CLI_DISCLAIMER)).toBeInTheDocument();
  });

  it('TC-WFX-006 영상 상세의 제안 구역 위에 면책과 "통과의 의미" 안내가 있다', async () => {
    await openVideo([suggestion(1)]);
    await screen.findByText('제안 목록');
    expect(screen.getByText(ko.legal.validationNote)).toBeInTheDocument();
    expect(screen.getAllByText(CLI_DISCLAIMER).length).toBeGreaterThanOrEqual(1);
  });

  it('TC-WFX-007 배치 사전 점검 카드에 한계 안내와 면책이 있고, 서버가 notice 를 주면 그 문장을 쓴다', async () => {
    const b = draftBatch();
    b.precheck = { ...b.precheck!, notice: '서버 면책: 법률 자문이 아닙니다.' };
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, b)),
      route('GET', '/api/v1/suggestions', () => page([])),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    const card = (await screen.findByText(ko.batches.precheckTitle)).closest('section, div.card')!;
    expect(within(card as HTMLElement).getByText(ko.legal.aiLimit)).toBeInTheDocument();
    expect(
      within(card as HTMLElement).getByText('서버 면책: 법률 자문이 아닙니다.'),
    ).toBeInTheDocument();
  });

  it('TC-WFX-008 A/B 확인란을 선택하지 않으면 확인 문구가 맞아도 실행 버튼이 꺼져 있고, 요청 본문은 그대로다', async () => {
    const user = userEvent.setup();
    let body: unknown;
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
      route('POST', '/api/v1/batches/7/execute', (r) => {
        body = r.body;
        return json(202, {
          batch: draftBatch({ status: 'running', executed_at: '2026-10-10T00:00:00Z' }),
          job: {
            id: 'j',
            type: 'batch.execute',
            status: 'queued',
            progress: 0,
            total: 2,
            error: null,
            result: null,
          },
        });
      }),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByText('실행 확인');
    const exec = screen.getByRole('button', { name: '실행' });
    expect(AB_BOX()).not.toBeChecked();
    expect(screen.getByText(ko.legal.abHint)).toBeInTheDocument();
    await user.type(screen.getByRole('textbox'), '실행 2건');
    expect(exec).toBeDisabled();
    expect(AB_BOX()).toHaveAccessibleDescription(ko.legal.abNeeded);
    await user.click(AB_BOX());
    expect(exec).toBeEnabled();
    expect(screen.queryByText(ko.legal.abNeeded)).toBeNull();
    await user.click(AB_BOX());
    expect(exec).toBeDisabled();
    await user.click(AB_BOX());
    await user.click(exec);
    await waitFor(() => expect(body).toEqual({ confirm_text: '실행 2건' }));
  });

  it('TC-WFX-009 성과 리포트: 서버 notes 에 면책이 없으면 화면 문구를 보태고, 이미 있으면 두 번 보이지 않는다', async () => {
    const mk = (notes: string[]) =>
      connectedClient([
        route('GET', '/api/v1/reports/changes', () => json(200, { items: [], notes })),
      ]);
    const a = await mk(['참고용입니다.']);
    const r1 = renderWithApp(<ReportsPage />, a.client);
    await screen.findByText('참고용입니다.');
    expect(screen.getAllByText(CLI_DISCLAIMER)).toHaveLength(1);
    expect(screen.getByText(ko.legal.reportsNote)).toBeInTheDocument();
    r1.unmount();
    const b = await mk([CLI_DISCLAIMER, '참고용입니다.']);
    renderWithApp(<ReportsPage />, b.client);
    await screen.findByText('참고용입니다.');
    expect(screen.getAllByText(CLI_DISCLAIMER)).toHaveLength(1);
  });

  it('TC-WFX-010 이력 화면 위에도 AI 생성 고지가 있다', async () => {
    const { client } = await connectedClient([route('GET', '/api/v1/changes', () => page([]))]);
    renderWithApp(<HistoryPage />, client);
    await userEvent.setup().click(await screen.findByRole('button', { name: '전체 기간' })); // 기간 기본값=오늘 → 전체 기간으로
    await screen.findByText(ko.history.emptyTitle);
    expect(screen.getByText(ko.legal.aiNotice)).toBeInTheDocument();
  });
});

describe('차단 제안 카드 (C-1, DEF-7-008)', () => {
  const blockedSug = suggestion(3, {
    title: '테스트 100% 무조건',
    status: 'blocked',
    validation_result: 'block',
    reasons: [{ code: 'banned', severity: 'block', message: '근거 없는 100% 단정' }],
  });

  it('TC-WFX-011 영문 상태 대신 "차단됨"과 승인할 수 없는 이유를 보이고, 승인만 막고 수정·반려는 가능하다', async () => {
    await openVideo([blockedSug]);
    await screen.findByText('테스트 100% 무조건');
    const c = within(cardOf(3));
    expect(c.getByText('차단됨')).toBeInTheDocument();
    expect(cardOf(3).textContent).not.toContain('blocked');
    expect(c.getByText(ko.suggestion.cannotApproveTitle)).toBeInTheDocument();
    expect(c.getByRole('button', { name: '승인' })).toBeDisabled();
    expect(c.getByRole('button', { name: '제목 수정' })).toBeEnabled();
    expect(c.getByRole('button', { name: '반려' })).toBeEnabled();
    expect(c.getByRole('button', { name: '승인' })).toHaveAccessibleDescription(
      /승인할 수 없는 이유.*근거 없는 100% 단정/,
    );
  });

  it('TC-WFX-012 차단 카드에서 제목을 고치면 PATCH 가 가고, 반려하면 reject 가 간다(확인 단계 포함)', async () => {
    const user = userEvent.setup();
    const { calls } = await openVideo([blockedSug]);
    await screen.findByText('테스트 100% 무조건');
    await user.click(within(cardOf(3)).getByRole('button', { name: '제목 수정' }));
    const dlg = await screen.findByRole('dialog', { name: ko.suggestion.editTitle });
    const input = within(dlg).getByLabelText('새 제목');
    await user.clear(input);
    await user.type(input, '테스트 영상 쉽게 정리');
    await user.click(within(dlg).getByRole('button', { name: '저장' }));
    await waitFor(() =>
      expect(calls.find((x) => x.method === 'PATCH')?.body).toEqual({
        title: '테스트 영상 쉽게 정리',
      }),
    );
    await user.click(within(cardOf(3)).getByRole('button', { name: '반려' }));
    expect(calls.some((x) => x.path.endsWith('/reject'))).toBe(false);
    const rj = await screen.findByRole('dialog', { name: ko.suggestion.rejectTitle });
    await user.click(within(rj).getByRole('button', { name: '반려' }));
    await waitFor(() =>
      expect(calls.some((x) => x.path === '/api/v1/suggestions/3/reject')).toBe(true),
    );
  });

  it('TC-WFX-013 엄격 모드에서 경고인 제안은 승인할 수 없는 이유로 엄격 모드 규칙을 알려 준다', async () => {
    await openVideo([
      suggestion(4, {
        title: '건강 제안',
        strict: true,
        validation_result: 'warn',
        reasons: [{ code: 'w', severity: 'warn', message: '효능을 단정하는 표현' }],
      }),
    ]);
    await screen.findByText('건강 제안');
    const c = within(cardOf(4));
    expect(c.getByRole('button', { name: '승인' })).toBeDisabled();
    expect(c.getByText(ko.suggestion.cannotApproveStrict)).toBeInTheDocument();
    expect(c.getAllByText('효능을 단정하는 표현').length).toBeGreaterThanOrEqual(2);
  });
});

describe('초안 배치 버리기 (C-2, DEF-7-009)', () => {
  it('TC-WFX-014 초안 상세의 [초안 버리기]는 확인 단계를 거쳐 POST cancel 을 한 번 보내고 "버려진 초안"으로 바뀐다', async () => {
    const user = userEvent.setup();
    let cancelled = false;
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () =>
        json(
          200,
          cancelled
            ? draftBatch({
                status: 'cancelled',
                counts: { pending: 0, running: 0, success: 0, failed: 0, skipped: 0, cancelled: 2 },
              })
            : draftBatch(),
        ),
      ),
      route('POST', '/api/v1/batches/7/cancel', () => {
        cancelled = true;
        return json(200, draftBatch({ status: 'cancelled' }));
      }),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await user.click(await screen.findByRole('button', { name: /초안 버리기/ }));
    expect(c.calls.some((x) => x.path.endsWith('/cancel'))).toBe(false);
    const dlg = await screen.findByRole('dialog', { name: ko.batches.discardTitle });
    expect(within(dlg).getByText(/제목은 그대로/)).toBeInTheDocument();
    await user.click(within(dlg).getByRole('button', { name: '버리기' }));
    await waitFor(() =>
      expect(c.calls.filter((x) => x.path === '/api/v1/batches/7/cancel')).toHaveLength(1),
    );
    expect(c.calls.find((x) => x.path.endsWith('/cancel'))!.headers['x-csrf-token']).toBe('csrf-1');
    expect(await screen.findByText(ko.batches.discardedBody)).toBeInTheDocument();
    expect(screen.getByText(ko.batches.discardedLabel)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /초안 버리기/ })).toBeNull();
    expect(screen.queryByText('실행 확인')).toBeNull();
  });

  it('TC-WFX-015 확인 대화상자에서 취소하면 서버 호출이 없다', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await user.click(await screen.findByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog', { name: ko.batches.discardTitle });
    await user.click(within(dlg).getByRole('button', { name: '취소' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(c.calls.some((x) => x.path.endsWith('/cancel'))).toBe(false);
  });

  it('TC-WFX-016 버리기가 서버에서 거절되면 한국어 오류를 대화상자 안에 보여 주고 대화상자는 열려 있다', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
      route('POST', '/api/v1/batches/7/cancel', () =>
        problem(
          409,
          'batch_not_cancellable',
          '이미 끝났거나 취소된 배치입니다',
          '',
          '목록을 새로고침하세요',
        ),
      ),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await user.click(await screen.findByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog', { name: ko.batches.discardTitle });
    await user.click(within(dlg).getByRole('button', { name: '버리기' }));
    expect(await within(dlg).findByText('이미 끝났거나 취소된 배치입니다')).toBeInTheDocument();
  });

  const sug = (n: number): Suggestion =>
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
  const listed = (b: Batch) => ({ ...b, items: [] });

  it('TC-WFX-017 초안에 이미 담긴 제안은 사유와 열기 링크를 보이고 선택·일괄 선택에서 빠지며, 버리면 다시 선택할 수 있다', async () => {
    const user = userEvent.setup();
    let discarded = false;
    const draft = draftBatch();
    const gone = draftBatch({
      status: 'cancelled',
      counts: { pending: 0, running: 0, success: 0, failed: 0, skipped: 0, cancelled: 2 },
      items: draftBatch().items.map((i) => ({ ...i, status: 'cancelled' })),
    });
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', () => page([sug(1), sug(2), sug(3)])),
      route('GET', '/api/v1/batches', () => page([listed(discarded ? gone : draft)])),
      route('GET', '/api/v1/batches/7', () => json(200, discarded ? gone : draft)),
      route('POST', '/api/v1/batches/7/cancel', () => {
        discarded = true;
        return json(200, gone);
      }),
    ]);
    renderWithApp(batchUi, c.client, '/batches');
    await screen.findByText('승인된 제목 3');
    await waitFor(() => expect(screen.getAllByText(/초안 배치 #7에 있음/)).toHaveLength(2));
    expect(screen.getAllByRole('link', { name: '초안 배치 #7 열기' })).toHaveLength(2);
    expect(screen.getByRole('checkbox', { name: '승인된 제목 1 선택' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: '승인된 제목 3 선택' })).toBeEnabled();
    await user.click(screen.getByRole('checkbox', { name: '전체 선택' }));
    expect(screen.getByText(/1개 선택됨/)).toBeInTheDocument();

    // 목록의 [초안 버리기]
    await user.click(await screen.findByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog', { name: ko.batches.discardTitle });
    await user.click(within(dlg).getByRole('button', { name: '버리기' }));
    await waitFor(() => expect(screen.queryByText(/초안 배치 #7에 있음/)).toBeNull());
    expect(screen.getByRole('checkbox', { name: '승인된 제목 1 선택' })).toBeEnabled();
    expect(screen.getAllByText(ko.batches.discardedLabel).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /초안 버리기/ })).toBeNull();
  });

  it('TC-WFX-018 지난 배치 목록에서 완료된 배치에는 [초안 버리기]가 없다', async () => {
    const done = { ...listed(draftBatch({ id: 5, status: 'completed' })) };
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', () => page([])),
      route('GET', '/api/v1/batches', () => page([done])),
    ]);
    renderWithApp(batchUi, c.client, '/batches');
    await screen.findByText('#5');
    expect(screen.queryByRole('button', { name: /초안 버리기/ })).toBeNull();
  });

  it('TC-WFX-019 사전 점검의 제외 항목에 영상 제목이 보인다(서버 video_title 우선, 없으면 제안→영상 상세로 찾음)', async () => {
    const b = draftBatch();
    b.precheck = {
      ...b.precheck!,
      blocked: [
        {
          suggestion_id: 8,
          reason: '다른 배치에 이미 담겨 있습니다.',
          video_id: 'vid00000008',
          video_title: '서버가 준 제목',
        },
        { suggestion_id: 9, reason: '72시간 안에 다시 바꿀 수 없습니다.' },
        { suggestion_id: 77, reason: '존재하지 않는 제안입니다.' },
      ],
    };
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, b)),
      route('GET', '/api/v1/suggestions', () => page([sug(9)])),
      route('GET', '/api/v1/videos/vid00000009', () =>
        json(200, detail([], { ...video(9), video_id: 'vid00000009', title: '찾아낸 영상 제목' })),
      ),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    expect(await screen.findByRole('link', { name: '서버가 준 제목' })).toHaveAttribute(
      'href',
      '/videos/vid00000008',
    );
    expect(await screen.findByRole('link', { name: '찾아낸 영상 제목' })).toBeInTheDocument();
    expect(screen.getByText('제안 77: 존재하지 않는 제안입니다.')).toBeInTheDocument();
  });
});

describe('이력 결과 값·영어 오류 (DEF-7-010)', () => {
  const chg = (id: number): Change => ({
    id,
    video_id: 'vid00000001',
    video_title: '테스트 영상 1',
    change_type: 'apply',
    previous_title: '이전',
    new_title: '새',
    result: 'aborted',
    mode: 'demo',
    approver: null,
    applied_at: '2026-10-10T00:00:00Z',
    verified_at: null,
    error_code: null,
    rollbackable: false,
    batch_id: null,
  });

  it('TC-WFX-020 "결과" 선택지는 서버가 받는 4가지뿐이고 aborted 는 한국어("중단됨")로 보인다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      route('GET', '/api/v1/changes', () => page([chg(1)])),
    ]);
    renderWithApp(<HistoryPage />, client);
    const sel = await screen.findByLabelText(ko.history.filterResult);
    const opts = within(sel)
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value);
    expect(opts).toEqual(['', 'planned', 'success', 'failed', 'aborted']);
    expect(await screen.findAllByText('중단됨')).not.toHaveLength(0);
    await user.selectOptions(sel, 'aborted');
    await waitFor(() => expect(calls.some((c) => c.query.get('result') === 'aborted')).toBe(true));
  });

  it('TC-WFX-021 서버가 영어 검증 오류(422)를 주어도 화면에는 한국어 문구만 보인다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/changes', (r) =>
        r.query.get('result')
          ? problem(
              422,
              'validation_error',
              'Unprocessable Entity',
              "query.result: Input should be 'planned', 'success'",
            )
          : page([]),
      ),
    ]);
    renderWithApp(<HistoryPage />, client);
    const sel = await screen.findByLabelText(ko.history.filterResult);
    fireEvent.change(sel, { target: { value: 'success' } });
    await screen.findByText(ko.errors.validation_error!);
    expect(document.body.textContent).not.toMatch(/Input should be|Unprocessable/);
  });

  it('TC-WFX-022 describeError: 코드별 한국어 문구가 있을 때만 영어 원문을 바꾸고, 한국어·알 수 없는 코드는 그대로 둔다', () => {
    const e = (code: string, title: string, detail: string, hint = '') =>
      describeError(new ApiError({ status: 422, code, title, detail, hint }));
    const a = e('validation_error', 'Unprocessable Entity', 'Field required', 'Fix the input');
    expect(a.title).toBe(ko.state.errorTitle);
    expect(a.detail).toBe(ko.errors.validation_error);
    expect(a.hint).toBe(ko.errorHints.validation_error);
    const b = e(
      'validation_error',
      '요청 값이 올바르지 않습니다.',
      '제안 번호가 올바르지 않습니다.',
    );
    expect(b.title).toBe('요청 값이 올바르지 않습니다.');
    expect(b.detail).toBe('제안 번호가 올바르지 않습니다.');
    const c = e('custom_code', 'Custom failure', 'Something happened');
    expect(c.title).toBe('Custom failure');
    expect(c.detail).toBe('Something happened');
  });
});

describe('토스트 (DEF-7-017)', () => {
  afterEach(() => vi.useRealTimers());
  function Pusher() {
    const t = useToast();
    return (
      <>
        <button onClick={() => t.push('success', '성공 알림')}>성공</button>
        <button onClick={() => t.push('error', '오류 알림')}>오류</button>
        <button onClick={() => t.clearTransient()}>정리</button>
      </>
    );
  }
  const mount = () =>
    render(
      <ToastProvider>
        <Pusher />
      </ToastProvider>,
    );

  it('TC-WFX-023 성공 알림은 약 5초 뒤 사라지고 오류 알림은 남는다', () => {
    vi.useFakeTimers();
    mount();
    fireEvent.click(screen.getByText('성공'));
    fireEvent.click(screen.getByText('오류'));
    expect(screen.getByText('성공 알림')).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(4900));
    expect(screen.getByText('성공 알림')).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(200));
    expect(screen.queryByText('성공 알림')).toBeNull();
    act(() => void vi.advanceTimersByTime(60_000));
    expect(screen.getByText('오류 알림')).toBeInTheDocument();
  });

  it('TC-WFX-024 clearTransient 는 성공·안내 알림만 치우고 오류 알림은 남긴다', () => {
    mount();
    fireEvent.click(screen.getByText('성공'));
    fireEvent.click(screen.getByText('오류'));
    fireEvent.click(screen.getByText('정리'));
    expect(screen.queryByText('성공 알림')).toBeNull();
    expect(screen.getByText('오류 알림')).toBeInTheDocument();
  });

  it('TC-WFX-025 화면(메뉴)을 옮기면 남아 있던 성공 알림이 사라진다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([
      route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
      route('GET', '/api/v1/settings', () =>
        json(200, {
          daily_apply_cap: 10,
          suggestions_per_video: 3,
          tone: [],
          pin_enabled: false,
          mode: 'demo',
          read_only: { enable_live: false, live_allowlist: [], note: '' },
        }),
      ),
      route('PATCH', '/api/v1/settings', () =>
        json(200, {
          daily_apply_cap: 9,
          suggestions_per_video: 3,
          tone: [],
          pin_enabled: false,
          mode: 'demo',
          read_only: { enable_live: false, live_allowlist: [], note: '' },
        }),
      ),
    ]);
    renderWithApp(<App />, client, '/settings');
    const cap = await screen.findByLabelText(ko.settings.dailyCap);
    await user.clear(cap);
    await user.type(cap, '9');
    await user.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText(ko.settings.saved)).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: '홈' }));
    await screen.findByRole('heading', { name: '홈' });
    await waitFor(() => expect(screen.queryByText(ko.settings.saved)).toBeNull());
  });
});

describe('Low 묶음', () => {
  it('TC-WFX-026 감사 로그는 행위자·동작·대상을 한국어로 보이고 원래 코드는 보조로 남긴다(모르는 값은 그대로)', async () => {
    const row = (
      id: number,
      actor: string,
      action: string,
      tt: string | null,
      tid: string | null,
    ) => ({
      id,
      ts: '2026-10-10T00:00:00Z',
      actor,
      action,
      target_type: tt,
      target_id: tid,
      detail: {},
    });
    const { client } = await connectedClient([
      route('GET', '/api/v1/audit', () =>
        json(200, {
          items: [
            row(1, 'owner', 'settings.update', 'settings', null),
            row(2, 'worker', 'batch.item.failed', 'batch_item', '12'),
            row(3, 'alien', 'brand.new_action', 'weird', '5'),
          ],
          total: 3,
          page: 1,
          page_size: 50,
          chain_ok: true,
        }),
      ),
    ]);
    renderWithApp(<SettingsPage />, client, '/settings?tab=audit');
    const table = await screen.findByRole('table');
    const rows = within(table).getAllByRole('row');
    expect(within(rows[1]!).getByText('소유자')).toBeInTheDocument();
    expect(within(rows[1]!).getByText('설정 변경')).toBeInTheDocument();
    expect(within(rows[1]!).getByText('settings.update')).toBeInTheDocument();
    expect(within(rows[2]!).getByText('작업 처리기')).toBeInTheDocument();
    expect(within(rows[2]!).getByText('배치 항목 실패')).toBeInTheDocument();
    expect(rows[2]!.textContent).toContain('배치 항목 12');
    expect(rows[3]!.textContent).toContain('brand.new_action');
    expect(rows[3]!.textContent).toContain('alien');
  });

  it('TC-WFX-027 홈의 [새로고침]은 대시보드를 서버에서 다시 읽는다(영상이 이미 있어도 항상 보인다)', async () => {
    const user = userEvent.setup();
    let n = 0;
    const { client } = await connectedClient([
      route('GET', '/api/v1/dashboard', () => {
        n++;
        return json(200, dashboard({ today: { applied: n, cap: 10 } }));
      }),
    ]);
    renderWithApp(<HomePage />, client);
    expect(await screen.findByText('1 / 10건')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: ko.home.refresh }));
    expect(await screen.findByText('2 / 10건')).toBeInTheDocument();
  });

  it('TC-WFX-028 영상 목록 체크박스는 라벨 영역(44px 이상 칸) 안에 있어 칸을 눌러도 선택된다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([
      route('GET', '/api/v1/videos', () => page([video(1), video(2)])),
    ]);
    renderWithApp(<VideosPage />, client);
    const box = await screen.findByRole('checkbox', { name: '테스트 영상 1 선택' });
    const hit = box.closest('label.check-hit') as HTMLElement;
    expect(hit).not.toBeNull();
    await user.click(hit);
    expect(box).toBeChecked();
    expect(
      screen.getByRole('checkbox', { name: ko.videos.selectPage }).closest('label.check-hit'),
    ).not.toBeNull();
  });
});
