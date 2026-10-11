// 06단계 독립 검증(W-FIX-FE) — 면책·AI 고지 문구(DEF-9-007·008): 서버 원문 대조, 위치별 렌더링, 중복 방지
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from '../src/app/App';
import { ko } from '../src/i18n/ko';
import { dashboard, draftBatch, suggestion } from '../src/test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../src/test/utils';
import {
  DISCLAIMER_LITERAL as D,
  batchUi,
  cardOf,
  openBatch,
  openVideo,
  page,
  readRepo,
} from './shared';
import { ReportsPage } from '../src/pages/ReportsPage';
import { HistoryPage } from '../src/pages/HistoryPage';

const count = (root: HTMLElement | Document, text: string) =>
  Array.from(root.querySelectorAll('p, span, li, div')).filter(
    (el) => el.children.length === 0 && el.textContent === text,
  ).length;

describe('면책 문장 원문 대조 (DEF-9-007)', () => {
  it('TC-VWF-001 ko.legal.disclaimer 는 서버 notices.py 의 DISCLAIMER 와 한 글자도 다르지 않다(파일을 읽어 대조)', () => {
    const src = readRepo('web/backend/ytweb/domain/notices.py');
    const m = /DISCLAIMER\s*=\s*"([^"\n]*)"/.exec(src);
    expect(m, 'notices.py 에서 DISCLAIMER 를 찾지 못함').not.toBeNull();
    const server = m![1]!;
    expect(ko.legal.disclaimer).toBe(server);
    expect(Buffer.from(ko.legal.disclaimer, 'utf8').equals(Buffer.from(server, 'utf8'))).toBe(true);
    expect(server).toBe(D);
  });

  it('TC-VWF-002 CLI(src/youtube_title/ui.py) 면책 문장과도 같고, 앞뒤 공백·NFD·보이지 않는 문자가 없다', () => {
    const ui = readRepo('src/youtube_title/ui.py');
    const m = /^DISCLAIMER\s*=\s*"([^"\n]*)"/m.exec(ui);
    expect(m![1]).toBe(ko.legal.disclaimer);
    expect(ko.legal.disclaimer).toBe(ko.legal.disclaimer.normalize('NFC'));
    expect(ko.legal.disclaimer).toBe(ko.legal.disclaimer.trim());
    // eslint-disable-next-line no-misleading-character-class
    expect(ko.legal.disclaimer).not.toMatch(/[​-‏‪-‮⁠-⁩﻿ ]/);
  });

  it('TC-VWF-003 test_sec_05 가 요구하는 문구 패턴이 ko.legal 에 모두 있다(소스 시험과 같은 정규식)', () => {
    const all = Object.values(ko.legal).join('\n');
    expect(all).toMatch(/법률 자문이 아니/);
    expect(all).toMatch(/최종 책임/);
    expect(all).toMatch(/채널 소유자/);
    expect(ko.legal.aiNotice).toMatch(/AI가 (?:생성|만든)/);
    expect(ko.legal.aiLimit).toMatch(/표시[·ㆍ]?\s?광고/);
    expect(ko.legal.aiLimit).toMatch(/보장하지|적합성/);
    expect(ko.legal.abConfirm).toMatch(/A\/B\s*테스트\s*중이\s*아/);
    expect(ko.legal.aiLimit).toMatch(/건강/);
    expect(ko.legal.aiLimit).toMatch(/금융/);
  });
});

describe('위치별 렌더링', () => {
  it.each(['/', '/videos', '/batches', '/history', '/reports', '/settings', '/없는-주소'])(
    'TC-VWF-004 %s — 서버가 모두 실패(404)해도 푸터 면책이 정확히 한 번 있다',
    async (path) => {
      const { client } = await connectedClient([]);
      renderWithApp(<App />, client, path);
      const foot = await screen.findByRole('contentinfo', { name: ko.legal.footerLabel });
      expect(within(foot).getAllByText(D)).toHaveLength(1);
      expect(within(foot).getAllByText(ko.legal.aiNotice)).toHaveLength(1);
      await waitFor(() => expect(document.querySelector('main')).not.toBeNull());
    },
  );

  it('TC-VWF-005 영상 상세: 제안이 0건이어도 본문에 면책이 있고(푸터와 별개), 제안이 있으면 본문 면책은 1번', async () => {
    // [06 재검증 시험 수정] 이 시험은 Layout 없이 VideoDetailPage 만 그려 <main> 이 없다(원래 실패: null.querySelectorAll). 본문만 그려지므로 body 로 센다.
    const a = await openVideo([]);
    await screen.findByText(ko.legal.validationNote);
    expect(count(document.body, D)).toBe(1);
    a.unmount();
    await openVideo([suggestion(1), suggestion(2, { title: '두번째' })]);
    await screen.findAllByText('두번째'); // [06 재검증 시험 수정] 제목이 카드 제목·비교 표에 모두 나와 findByText 는 중복 오류
    expect(count(document.body, D)).toBe(1);
  });

  it.each([
    ['통과', { validation_result: 'pass' as const, strict: false }],
    [
      '경고',
      {
        validation_result: 'warn' as const,
        strict: false,
        reasons: [{ code: 'w', severity: 'warn' as const, message: '주의 문장' }],
      },
    ],
    ['직접 수정(manual)', { source: 'manual', strict: false }],
    ['엄격 모드 통과', { strict: true, validation_result: 'pass' as const }],
  ])(
    'TC-VWF-006 승인 대화상자(%s)에 면책이 정확히 1번, AI 고지는 AI 출처에서만',
    async (_n, over) => {
      const user = userEvent.setup();
      await openVideo([suggestion(1, over)]);
      await screen.findByRole('article');
      await user.click(within(cardOf(1)).getByRole('button', { name: '승인' }));
      const dlg = await screen.findByRole('dialog', { name: ko.suggestion.approveTitle });
      expect(count(dlg, D)).toBe(1);
      expect(within(dlg).getAllByText(ko.legal.aiLimit)).toHaveLength(1);
      const isAi = (over as { source?: string }).source !== 'manual';
      expect(within(dlg).queryAllByText(ko.legal.aiNotice)).toHaveLength(isAi ? 1 : 0);
      expect(within(dlg).queryAllByText(ko.legal.strictCaution)).toHaveLength(
        (over as { strict?: boolean }).strict ? 1 : 0,
      );
    },
  );

  it('TC-VWF-007 사전 점검: notice 가 없으면 화면 면책을, 서버 notice 가 면책 원문이면 카드 안에 정확히 1번만(중복 없음)', async () => {
    const withoutNotice = await openBatch();
    const card1 = (await screen.findByText(ko.batches.precheckTitle)).closest(
      'section, div.card',
    ) as HTMLElement;
    expect(count(card1, D)).toBe(1);
    withoutNotice.unmount();
    const b = draftBatch();
    b.precheck = { ...b.precheck!, notice: D };
    await openBatch([], b);
    const card2 = (await screen.findByText(ko.batches.precheckTitle)).closest(
      'section, div.card',
    ) as HTMLElement;
    expect(count(card2, D)).toBe(1);
    expect(within(card2).getAllByText(ko.legal.aiLimit)).toHaveLength(1);
  });

  it('TC-VWF-008 사전 점검 정보가 화면 이동 상태(location.state)로 와도 같은 고지가 나온다', async () => {
    const b = draftBatch({ precheck: null });
    const pc = { ...draftBatch().precheck!, notice: '서버 안내: ' + D };
    const c = await connectedClient([route('GET', '/api/v1/batches/7', () => json(200, b))]);
    renderWithApp(batchUi, c.client, { pathname: '/batches/7', state: { precheck: pc } });
    await screen.findByText(ko.batches.precheckTitle);
    expect(screen.getByText('서버 안내: ' + D)).toBeInTheDocument();
    expect(screen.getByText(ko.legal.aiLimit)).toBeInTheDocument();
  });

  it('TC-VWF-009 성과 리포트: notes 가 비어도 화면 면책 1번, 서버 notes 에 면책이 있으면 본문에는 1번(푸터 제외)', async () => {
    const mk = (notes: string[]) =>
      connectedClient([
        route('GET', '/api/v1/reports/changes', () => json(200, { items: [], notes })),
      ]);
    const a = await mk([]);
    const r1 = renderWithApp(<ReportsPage />, a.client);
    await screen.findByText(ko.legal.reportsNote);
    expect(count(document.body, D)).toBe(1);
    expect(screen.getByText(ko.reports.fallbackNote)).toBeInTheDocument();
    r1.unmount();
    const b = await mk([D, '참고용']);
    renderWithApp(<ReportsPage />, b.client);
    await screen.findByText('참고용');
    expect(count(document.body, D)).toBe(1);
  });

  it('TC-VWF-010 리포트: 서버 notes 가 면책을 앞뒤 문장과 한 줄로 이어 줘도 중복되지 않는다', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/reports/changes', () =>
        json(200, { items: [], notes: [`※ ${D} (참고)`] }),
      ),
    ]);
    renderWithApp(<ReportsPage />, c.client);
    await screen.findByText(`※ ${D} (참고)`);
    expect(document.body.textContent!.split(D).length - 1).toBe(1);
  });

  it('TC-VWF-011 이력 화면: AI 고지가 목록 로딩 실패 상태에서도 보인다', async () => {
    const { client } = await connectedClient([]);
    renderWithApp(<HistoryPage />, client);
    expect(await screen.findByText(ko.legal.historyNote)).toBeInTheDocument();
    expect(screen.getByText(ko.legal.aiNotice)).toBeInTheDocument();
  });

  it('TC-VWF-012 홈 화면에도 푸터 면책이 있다(화면 전환 후에도 남음)', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([
      route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
      route('GET', '/api/v1/videos', () => page([])),
    ]);
    renderWithApp(<App />, client, '/');
    await screen.findByRole('heading', { name: '홈' });
    // [06 재검증 시험 수정] 원래 실패: 메뉴 이름은 '영상'이 아니라 '영상 목록'(ko.nav.videos)
    await user.click(screen.getByRole('link', { name: ko.nav.videos }));
    await screen.findByRole('heading', { name: ko.videos.title });
    const foot = screen.getByRole('contentinfo');
    expect(within(foot).getByText(D)).toBeInTheDocument();
  });
});
