// 06단계 독립 검증(W-FIX-FE 재검증) — 차단 제안 카드(C-1), 초안 버리기(C-2), A/B 확인, 면책 위치, 상단 모드 배지 진실성.
// 사용자(비개발자 채널 소유자) 관점. 제품 소스는 건드리지 않는다.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { Suggestion } from '../src/api/types';
import { App } from '../src/app/App';
import { ko } from '../src/i18n/ko';
import { BatchDetailPage } from '../src/pages/BatchDetailPage';
import { BatchesPage } from '../src/pages/BatchesPage';
import { VideoDetailPage } from '../src/pages/VideoDetailPage';
import { dashboard, detail, draftBatch, suggestion } from '../src/test/fixtures';
import { connectedClient, json, problem, renderWithApp, route } from '../src/test/utils';
import type { Handler } from '../src/test/utils';

const D = '이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.';
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
const blockedReason = {
  code: 'banned',
  severity: 'error' as const,
  message: '금칙어가 들어 있습니다.',
};

async function openVideo(sg: Suggestion[], extra: Handler[] = []) {
  const c = await connectedClient([
    route('GET', '/api/v1/videos/vid00000001', () => json(200, detail(sg))),
    ...extra,
  ]);
  const r = renderWithApp(videoUi, c.client, '/videos/vid00000001');
  await screen.findByText(ko.legal.validationNote);
  return { ...c, ...r };
}
const cardOf = (id: number) =>
  document.querySelector<HTMLElement>(`#sg-${id}`)!.closest('article') as HTMLElement;

describe('C-1 차단 제안 카드 (DEF-7-008)', () => {
  const blockedCases: [string, Partial<Suggestion>][] = [
    ['검증 차단', { validation_result: 'block', reasons: [blockedReason] }],
    ['상태 blocked', { status: 'blocked', validation_result: 'block', reasons: [blockedReason] }],
    [
      '엄격 모드+경고(건강·금융)',
      {
        strict: true,
        validation_result: 'warn',
        reasons: [{ code: 'w', severity: 'warn', message: '효능 단정 표현' }],
      },
    ],
    ['엄격 모드+검증 전', { strict: true, validation_result: 'none' }],
  ];
  it.each(blockedCases)(
    'TC-VMF-100 %s: 승인은 막히고 이유가 카드에 있으며 [제목 수정]·[반려]는 누를 수 있다',
    async (_n, over) => {
      await openVideo([suggestion(1, over)]);
      const card = within(cardOf(1));
      expect(card.getByRole('button', { name: ko.suggestion.approve })).toBeDisabled();
      expect(card.getByRole('button', { name: ko.suggestion.edit })).toBeEnabled();
      expect(card.getByRole('button', { name: ko.suggestion.reject })).toBeEnabled();
      expect(card.getByText(ko.suggestion.cannotApproveTitle)).toBeInTheDocument();
      expect(card.getByText(ko.suggestion.approveBlocked)).toBeInTheDocument();
      expect(card.getByText(ko.suggestion.blockedStatusHint)).toBeInTheDocument();
      // 승인 버튼은 이유 설명과 연결돼 있다(스크린리더)
      const ap = card.getByRole('button', { name: ko.suggestion.approve });
      const desc = ap.getAttribute('aria-describedby');
      expect(desc && document.getElementById(desc)?.textContent).toContain(
        ko.suggestion.cannotApproveTitle,
      );
    },
  );

  it('TC-VMF-101 이유가 서버에서 오지 않은 차단도 빈 안내가 아니라 "사유는 위 검증 사유를 확인" 안내가 나온다', async () => {
    await openVideo([suggestion(1, { validation_result: 'block', reasons: [] })]);
    expect(within(cardOf(1)).getByText(ko.suggestion.cannotApproveNoReason)).toBeInTheDocument();
  });

  it('TC-VMF-102 차단 이유 목록은 error/block 심각도 사유만 보이고 정보성 사유는 차단 이유로 나오지 않는다', async () => {
    await openVideo([
      suggestion(1, {
        validation_result: 'block',
        reasons: [blockedReason, { code: 'i', severity: 'info', message: '참고 정보 문장' }],
      }),
    ]);
    const box = within(cardOf(1)).getByText(ko.suggestion.cannotApproveTitle).closest('div')!;
    expect(within(box as HTMLElement).getByText('금칙어가 들어 있습니다.')).toBeInTheDocument();
    expect(within(box as HTMLElement).queryByText('참고 정보 문장')).toBeNull();
  });

  it('TC-VMF-103 통과 제안과 엄격 모드 통과 제안에는 차단 안내가 없고 승인 버튼이 켜져 있다', async () => {
    await openVideo([suggestion(1), suggestion(2, { strict: true, validation_result: 'pass' })]);
    for (const id of [1, 2]) {
      const c = within(cardOf(id));
      expect(c.getByRole('button', { name: ko.suggestion.approve })).toBeEnabled();
      expect(c.queryByText(ko.suggestion.cannotApproveTitle)).toBeNull();
    }
  });

  it('TC-VMF-104 이미 승인·반영 완료·반려된 제안에는 차단 안내와 승인 버튼이 없다(상태 거짓 표시 금지)', async () => {
    await openVideo([
      suggestion(1, { status: 'applied', validation_result: 'block' }),
      suggestion(2, { status: 'rejected', validation_result: 'block' }),
      suggestion(3, { status: 'approved', validation_result: 'block' }),
    ]);
    for (const id of [1, 2, 3]) {
      const c = within(cardOf(id));
      expect(c.queryByRole('button', { name: ko.suggestion.approve })).toBeNull();
      expect(c.queryByText(ko.suggestion.cannotApproveTitle)).toBeNull();
    }
  });

  it('TC-VMF-105 차단 카드에서 [제목 수정]: 빈 값·같은 값·101자는 저장 불가, 100자는 저장되어 PATCH 로 trim 된 제목이 간다', async () => {
    const user = userEvent.setup();
    const { calls } = await openVideo(
      [suggestion(1, { validation_result: 'block', reasons: [blockedReason] })],
      [route('PATCH', '/api/v1/suggestions/1', () => json(200, suggestion(1)))],
    );
    await user.click(within(cardOf(1)).getByRole('button', { name: ko.suggestion.edit }));
    const dlg = await screen.findByRole('dialog', { name: ko.suggestion.editTitle });
    const input = within(dlg).getByRole('textbox');
    const save = within(dlg).getByRole('button', { name: ko.app.save });
    await user.clear(input);
    expect(save).toBeDisabled();
    expect(within(dlg).getByText(ko.suggestion.editEmpty)).toBeInTheDocument();
    await user.type(input, '가'.repeat(101));
    expect(save).toBeDisabled();
    expect(within(dlg).getByText(ko.suggestion.editTooLong)).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, '  ' + '나'.repeat(100) + '  ');
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect((calls.find((c) => c.method === 'PATCH')!.body as { title: string }).title).toBe(
      '나'.repeat(100),
    );
  });

  it('TC-VMF-106 차단 카드에서 [반려]는 확인 후 POST reject, 취소하면 요청 없음', async () => {
    const user = userEvent.setup();
    const { calls } = await openVideo(
      [suggestion(1, { validation_result: 'block', reasons: [blockedReason] })],
      [
        route('POST', '/api/v1/suggestions/1/reject', () =>
          json(200, suggestion(1, { status: 'rejected' })),
        ),
      ],
    );
    await user.click(within(cardOf(1)).getByRole('button', { name: ko.suggestion.reject }));
    let dlg = await screen.findByRole('dialog', { name: ko.suggestion.rejectTitle });
    await user.click(within(dlg).getByRole('button', { name: ko.app.cancel }));
    expect(calls.some((c) => c.path.endsWith('/reject'))).toBe(false);
    await user.click(within(cardOf(1)).getByRole('button', { name: ko.suggestion.reject }));
    dlg = await screen.findByRole('dialog', { name: ko.suggestion.rejectTitle });
    await user.click(within(dlg).getByRole('button', { name: ko.suggestion.reject }));
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/reject'))).toHaveLength(1));
  });

  it('TC-VMF-107 차단 제안이어도 키보드/강제 제출로 승인 요청이 서버에 가지 않는다(화면 방어)', async () => {
    const { calls } = await openVideo([
      suggestion(1, { validation_result: 'block', reasons: [blockedReason] }),
    ]);
    const ap = within(cardOf(1)).getByRole('button', { name: ko.suggestion.approve });
    ap.click(); // disabled 버튼의 click()
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false);
  });

  it('TC-VMF-108 승인 대화상자: 승인자 이름이 비면 승인 불가, 경고 제안은 확인란 체크 전에는 승인 불가, 둘 다 하면 POST approve', async () => {
    const user = userEvent.setup();
    const { calls } = await openVideo(
      [
        suggestion(1, {
          validation_result: 'warn',
          reasons: [{ code: 'w', severity: 'warn', message: '주의 문장' }],
        }),
      ],
      [
        route('POST', '/api/v1/suggestions/1/approve', () =>
          json(200, suggestion(1, { status: 'approved' })),
        ),
      ],
    );
    window.localStorage.clear();
    await user.click(within(cardOf(1)).getByRole('button', { name: ko.suggestion.approve }));
    const dlg = await screen.findByRole('dialog', { name: ko.suggestion.approveTitle });
    const ok = within(dlg).getByRole('button', { name: ko.suggestion.approve });
    expect(ok).toBeDisabled();
    await user.type(within(dlg).getByRole('textbox'), '  홍길동 ');
    expect(ok).toBeDisabled(); // 경고 확인 전
    await user.click(within(dlg).getByRole('checkbox', { name: ko.suggestion.warnAck }));
    expect(ok).toBeEnabled();
    await user.click(ok);
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/approve'))).toHaveLength(1));
    expect(
      (calls.find((c) => c.path.endsWith('/approve'))!.body as { approver: string }).approver,
    ).toBe('홍길동');
  });
});

describe('C-2 초안 배치 버리기 (DEF-7-009)', () => {
  const gone = () =>
    draftBatch({
      status: 'cancelled',
      items: draftBatch().items.map((i) => ({ ...i, status: 'cancelled' })),
    });
  // 서버처럼 상태를 기억한다: 취소 응답 뒤 다시 읽으면 취소된 상태가 돌아온다
  let serverBatch = draftBatch();
  const cancelOk = (delay = 0) =>
    route('POST', '/api/v1/batches/7/cancel', async () => {
      if (delay) await new Promise((r) => setTimeout(r, delay));
      serverBatch = gone();
      return json(200, serverBatch);
    });
  async function openBatch(extra: Handler[] = [], b = draftBatch()) {
    serverBatch = b;
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, serverBatch)),
      ...extra,
    ]);
    const r = renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByText(ko.batches.confirmTitle).catch(() => undefined);
    await screen.findByText('새 제목 1');
    return { ...c, ...r };
  }

  it('TC-VMF-110 초안 상세에 [초안 버리기]가 있고, 누르면 "제목은 그대로" 안내가 있는 확인창, 취소하면 요청이 없다', async () => {
    const user = userEvent.setup();
    const { calls } = await openBatch();
    await user.click(screen.getByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog', { name: ko.batches.discardTitle });
    expect(within(dlg).getByText(ko.batches.discardBody)).toBeInTheDocument();
    expect(ko.batches.discardBody).toMatch(/제목은 그대로/);
    await user.click(within(dlg).getByRole('button', { name: ko.app.cancel }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(calls.some((c) => c.path.endsWith('/cancel'))).toBe(false);
  });

  it('TC-VMF-111 확인하면 POST cancel 1번, 완료 안내(토스트)·"버려진 초안" 표시, 실행 영역과 버리기 버튼이 사라진다', async () => {
    const user = userEvent.setup();
    const { calls } = await openBatch([cancelOk()]);
    await user.click(screen.getByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog', { name: ko.batches.discardTitle });
    await user.click(within(dlg).getByRole('button', { name: ko.batches.discardConfirm }));
    expect(await screen.findByText(ko.batches.discardedBody)).toBeInTheDocument();
    expect(screen.getByText(ko.batches.discardedLabel)).toBeInTheDocument();
    expect(screen.getByText(ko.batches.discardedToast)).toBeInTheDocument();
    expect(calls.filter((c) => c.path === '/api/v1/batches/7/cancel')).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /초안 버리기/ })).toBeNull();
    expect(screen.queryByRole('button', { name: ko.batches.execute })).toBeNull();
    expect(screen.queryByText(ko.batches.confirmTitle)).toBeNull();
    expect(screen.getAllByRole('link', { name: ko.batches.backToList }).length).toBeGreaterThan(0);
  });

  it('TC-VMF-112 버리기 실패(409: 이미 취소됨)면 확인창이 남고 오류가 보이며 "버렸습니다" 안내는 없다', async () => {
    const user = userEvent.setup();
    await openBatch([
      route('POST', '/api/v1/batches/7/cancel', () =>
        problem(409, 'batch_not_cancellable', '이미 처리된 배치입니다', '상태를 확인하세요.'),
      ),
    ]);
    await user.click(screen.getByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog', { name: ko.batches.discardTitle });
    await user.click(within(dlg).getByRole('button', { name: ko.batches.discardConfirm }));
    expect(await within(dlg).findByText('이미 처리된 배치입니다')).toBeInTheDocument();
    expect(screen.queryByText(ko.batches.discardedToast)).toBeNull();
    expect(screen.queryByText(ko.batches.discardedBody)).toBeNull();
    // 오류 후 닫았다 다시 열면 이전 오류가 남아 있지 않다
    await userEvent.setup().click(within(dlg).getByRole('button', { name: ko.app.cancel }));
    await userEvent.setup().click(screen.getByRole('button', { name: /초안 버리기/ }));
    const dlg2 = await screen.findByRole('dialog', { name: ko.batches.discardTitle });
    expect(within(dlg2).queryByText('이미 처리된 배치입니다')).toBeNull();
  });

  it('TC-VMF-113 확인 버튼을 연타해도 서버 요청은 1번(응답이 느릴 때)', async () => {
    const user = userEvent.setup();
    const { calls } = await openBatch([cancelOk(300)]);
    await user.click(screen.getByRole('button', { name: /초안 버리기/ }));
    const dlg = await screen.findByRole('dialog', { name: ko.batches.discardTitle });
    const yes = within(dlg).getByRole('button', { name: ko.batches.discardConfirm });
    await user.click(yes);
    await user.click(yes);
    await user.click(yes);
    await screen.findByText(ko.batches.discardedBody);
    expect(calls.filter((c) => c.path.endsWith('/cancel'))).toHaveLength(1);
  });

  it('TC-VMF-114 진행 중(running)·완료·실행 전 취소가 아닌 취소(실행 이력 있음) 배치에는 [초안 버리기]가 없다', async () => {
    for (const over of [
      { status: 'running' as const, executed_at: '2026-10-10T00:00:00Z' },
      { status: 'completed' as const, executed_at: '2026-10-10T00:00:00Z' },
      { status: 'cancelled' as const, executed_at: '2026-10-10T00:00:00Z' },
    ]) {
      const r = await openBatch([], draftBatch(over));
      expect(screen.queryByRole('button', { name: /초안 버리기/ })).toBeNull();
      expect(
        screen.queryByText(ko.batches.discardedBody),
        `executed_at 있는 ${over.status} 를 버려진 초안으로 오인`,
      ).toBeNull();
      r.unmount();
    }
  });

  it('TC-VMF-115 목록의 초안 행에만 [초안 버리기]가 있고, 구별용 숨은 이름에 배치 번호가 들어 있다', async () => {
    const mk = (id: number, status: string) => ({
      ...draftBatch({ id, status: status as 'draft' }),
      items: [],
    });
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', () => page([])),
      route('GET', '/api/v1/batches', () =>
        page([mk(7, 'draft'), mk(5, 'completed'), mk(3, 'draft')]),
      ),
      route('GET', /^\/api\/v1\/batches\/\d+$/, (r) =>
        json(200, draftBatch({ id: Number(r.path.split('/').pop()) })),
      ),
    ]);
    renderWithApp(batchUi, c.client, '/batches');
    expect(
      await screen.findByRole('button', { name: /초안 버리기\s*\(배치 #7\)/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /초안 버리기\s*\(배치 #3\)/ })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /초안 버리기/ })).toHaveLength(2);
  });
});

describe('A/B 확인 문구 · 실행 버튼 조건', () => {
  async function open(b = draftBatch()) {
    const c = await connectedClient([route('GET', '/api/v1/batches/7', () => json(200, b))]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByText(ko.batches.confirmTitle);
    return c;
  }
  const run = () => screen.getByRole('button', { name: ko.batches.execute });

  it('TC-VMF-120 확인 문구·설명·"필요" 안내가 보이고 실행은 잠겨 있다', async () => {
    await open();
    expect(screen.getByText(ko.legal.abConfirm)).toBeInTheDocument();
    expect(screen.getByText(ko.legal.abHint)).toBeInTheDocument();
    expect(screen.getByText(ko.legal.abNeeded)).toBeInTheDocument();
    expect(run()).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ })).not.toBeChecked();
  });

  it('TC-VMF-121 확인란만 체크 / 확인 문구만 입력 / 둘 다 → 둘 다일 때만 실행 가능, 체크를 풀면 다시 잠기고 안내가 돌아온다', async () => {
    const user = userEvent.setup();
    await open();
    const box = screen.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ });
    await user.click(box);
    expect(run()).toBeDisabled(); // 확인 문구 없음
    expect(screen.queryByText(ko.legal.abNeeded)).toBeNull();
    await user.type(screen.getByRole('textbox'), '실행 2건');
    expect(run()).toBeEnabled();
    await user.click(box);
    expect(run()).toBeDisabled();
    expect(screen.getByText(ko.legal.abNeeded)).toBeInTheDocument();
    await user.click(box);
    await user.clear(screen.getByRole('textbox'));
    await user.type(screen.getByRole('textbox'), '실행 3건'); // 틀린 문구
    expect(run()).toBeDisabled();
  });

  it('TC-VMF-122 실행하면 confirm_text 만 서버로 가고 A/B 확인 값은 서버에 보내지 않는다(DEC-047 데모 단계 화면 전용)', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/batches/7', () => json(200, draftBatch())),
      route('POST', '/api/v1/batches/7/execute', () =>
        json(202, {
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
        }),
      ),
    ]);
    renderWithApp(batchUi, c.client, '/batches/7');
    await screen.findByText(ko.batches.confirmTitle);
    await user.click(screen.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ }));
    await user.type(screen.getByRole('textbox'), '실행 2건');
    await user.click(run());
    await waitFor(() => expect(c.calls.filter((x) => x.path.endsWith('/execute'))).toHaveLength(1));
    expect(c.calls.find((x) => x.path.endsWith('/execute'))!.body).toEqual({
      confirm_text: '실행 2건',
    });
  });

  it('TC-VMF-123 모든 항목이 차단이면 A/B 확인란·실행 버튼 없이 "모두 제외" 안내만 나온다', async () => {
    const b = draftBatch();
    b.precheck = { ...b.precheck!, item_count: 0 };
    await open(b);
    expect(screen.queryByText(ko.legal.abConfirm)).toBeNull();
    expect(screen.queryByRole('button', { name: ko.batches.execute })).toBeNull();
    expect(screen.getByText(ko.batches.pc.allBlocked)).toBeInTheDocument();
  });
});

describe('면책·AI 고지가 실제 화면(App 전체)의 어디에 나오는가', () => {
  it('TC-VMF-130 영상 상세 화면: 면책은 본문(제안 목록 위)과 화면 맨 아래 푸터 두 곳에 있고 AI 고지는 푸터와 각 AI 제안 카드에 있다', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
      route('GET', '/api/v1/videos/vid00000001', () => json(200, detail([suggestion(1)]))),
    ]);
    renderWithApp(<App />, c.client, '/videos/vid00000001');
    await screen.findAllByText('테스트 영상 1 핵심 정리');
    const main = document.querySelector('main') as HTMLElement;
    const foot = screen.getByRole('contentinfo', { name: ko.legal.footerLabel });
    expect(within(main).getAllByText(D)).toHaveLength(1);
    expect(within(foot).getAllByText(D)).toHaveLength(1);
    expect(within(foot).getByText(ko.legal.aiNotice)).toBeInTheDocument();
    expect(within(main).getByText(ko.legal.aiNotice)).toBeInTheDocument(); // 카드 안
    expect(main.compareDocumentPosition(foot) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy(); // 푸터는 본문 뒤
  });

  it.each(['/', '/videos', '/batches', '/history', '/reports', '/settings'])(
    'TC-VMF-131 %s 화면에서 푸터 면책은 정확히 1번 보이고 숨김(hidden/aria-hidden/display:none) 처리가 아니다',
    async (path) => {
      const c = await connectedClient([
        route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
      ]);
      renderWithApp(<App />, c.client, path);
      const foot = await screen.findByRole('contentinfo', { name: ko.legal.footerLabel });
      const p = within(foot).getByText(D);
      for (let el: HTMLElement | null = p; el; el = el.parentElement) {
        expect(el.hidden).toBe(false);
        expect(el.getAttribute('aria-hidden')).not.toBe('true');
        expect(el.style.display).not.toBe('none');
      }
      expect(within(foot).getAllByRole('paragraph').length).toBe(2);
    },
  );
});

describe('화면 상단 모드 배지는 현재 모드에 대해 사실이어야 한다', () => {
  it('TC-VMF-140 실제 모드(dashboard.mode=live)인데도 상단 배지가 "유튜브에 아무것도 전송되지 않습니다"라고 하면 거짓 안내', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/dashboard', () =>
        json(
          200,
          dashboard({
            mode: 'live',
            live_enabled: true,
            google: { mode: 'read', connected: true },
          }),
        ),
      ),
    ]);
    renderWithApp(<App />, c.client, '/');
    await screen.findByRole('heading', { name: ko.home.title });
    await waitFor(() => expect(screen.getByText(ko.home.liveOn)).toBeInTheDocument());
    expect(document.body.textContent).not.toContain('아무것도 전송되지 않습니다');
  });

  it('TC-VMF-141 구글 읽기 연결 상태(실제 영상 목록을 읽는 중)에서 상단 배지가 "데모 모드"라고만 하면 현재 상태와 맞지 않는다', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/dashboard', () =>
        json(200, dashboard({ mode: 'demo', google: { mode: 'read', connected: true } })),
      ),
      route('GET', '/api/v1/google/status', () =>
        json(200, {
          mode: 'read',
          connected: true,
          client_ready: true,
          message: '구글에 연결돼 있습니다.',
          write_connected: false,
          live_allowed_count: 0,
          live_write_ready: false,
        }),
      ),
    ]);
    renderWithApp(<App />, c.client, '/');
    await screen.findByText('구글에 연결돼 있습니다.');
    expect(document.body.textContent).not.toContain(
      '데모 모드 — 유튜브에 아무것도 전송되지 않습니다',
    );
  });
});

describe('실제 서버가 보내는 모양(대시보드는 항상 demo·live_enabled=false) 그대로 실제 수정 가능 상태일 때', () => {
  it('TC-VMF-142 구글 상태가 live_write_ready=true 인 화면 전체에서 "유튜브에 아무것도 전송되지 않습니다"·"실제 반영(라이브): 꺼짐"이 함께 보이면 서로 모순되는 거짓 안내', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/dashboard', () => json(200, dashboard())), // 백엔드 dashboard.py 는 live_enabled 를 항상 False 로 보낸다
      route('GET', '/api/v1/google/status', () =>
        json(200, {
          mode: 'read',
          connected: true,
          client_ready: true,
          message: '구글에 연결돼 있습니다.',
          write_connected: true,
          live_write_enabled: true,
          live_allowed_count: 1,
          live_write_ready: true,
        }),
      ),
    ]);
    renderWithApp(<App />, c.client, '/');
    await screen.findByText(ko.google.liveWarnTitle);
    const t = document.body.textContent ?? '';
    expect(t, '경고는 "실제로 바뀐다"인데 상단은 "아무것도 전송되지 않는다"').not.toContain(
      '아무것도 전송되지 않습니다',
    );
    expect(t, '경고는 켜짐인데 홈 상태 카드는 라이브 꺼짐').not.toContain(ko.home.liveOff);
  });
});
