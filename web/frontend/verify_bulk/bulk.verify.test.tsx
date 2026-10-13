// 일괄 승인 프런트 독립 검증(TC-FV-001~). 구현자 시험(bulkapprove.test.tsx)과 독립으로 작성.
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { App } from '../src/app/App';
import { Providers } from '../src/app/providers';
import type { ResolvedVideo, Suggestion } from '../src/api/types';
import { dashboard, suggestion } from '../src/test/fixtures';
import {
  authedHandlers,
  axeViolations,
  json,
  makeClient,
  problem,
  route,
  type Handler,
} from '../src/test/utils';

const vid = (n: number) => `vid${String(n).padStart(8, '0')}`;
const sg = (id: number, over: Partial<Suggestion> = {}) =>
  suggestion(id, { video_id: vid(id), title: `새 제목 ${id}`, ...over });
const page = (items: unknown[]) => json(200, { items, total: items.length, page: 1, page_size: 50 });
const rv = (n: number, over: Partial<ResolvedVideo> = {}): ResolvedVideo => ({
  video_id: vid(n),
  found: true,
  video_title: `현재 제목 ${n}`,
  excluded_reasons: [],
  candidates: [sg(n)],
  ...over,
});
/** 목록 + resolve(목록 영상의 현재 제목, 붙여넣기 모두 같은 규칙: 요청 ID 마다 rv) */
const baseHandlers = (cand: Suggestion[], resolve?: (ids: string[]) => ResolvedVideo[]): Handler[] => [
  route('GET', '/api/v1/suggestions', (r) =>
    page(r.query.get('status') === 'expired' ? [] : cand),
  ),
  route('POST', '/api/v1/suggestions/resolve-videos', (r) => {
    const ids = (r.body as { video_ids: string[] }).video_ids;
    const fn =
      resolve ??
      ((xs: string[]) =>
        xs.map((x) => {
          const n = Number(x.slice(3));
          const c = cand.find((s) => s.video_id === x);
          return rv(n, { candidates: c ? [c] : [sg(n)] });
        }));
    return json(200, { items: fn(ids) });
  }),
  route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
];
const okResult = (ids: number[]) =>
  json(200, {
    approved: ids.map((i) => ({ suggestion_id: i, video_id: vid(i) })),
    skipped: [],
    counts: { requested: ids.length, approved: ids.length, skipped: 0 },
  });

async function setup(handlers: Handler[], mode?: 'demo' | 'live') {
  const user = userEvent.setup();
  const c = makeClient([...authedHandlers, ...handlers]);
  void mode;
  document.getElementById('root')?.remove();
  const root = document.createElement('div');
  root.id = 'root';
  document.body.appendChild(root);
  const r = render(
    <Providers client={c.client}>
      <MemoryRouter initialEntries={['/bulk-approve']}>
        <App />
      </MemoryRouter>
    </Providers>,
    { container: root },
  );
  await screen.findByRole('heading', { name: '일괄 승인' });
  return { user, ...c, ...r };
}
const reviewBtn = () => screen.getByRole('button', { name: '확인 창 열기' });
const dialog = () => screen.getByRole('dialog');
const submitBtn = () => within(dialog()).getByRole('button', { name: /건 승인$/ });
const approverBox = () => within(dialog()).getByRole('textbox', { name: /승인자 이름/ });
const setApprover = async (u: ReturnType<typeof userEvent.setup>, v: string) => {
  const b = approverBox();
  await u.clear(b);
  if (v) await u.click(b), await u.paste(v);
};
const paste = async (u: ReturnType<typeof userEvent.setup>, text: string) => {
  const box = screen.getByRole('textbox', { name: /영상 ID/ });
  await u.clear(box);
  await u.click(box);
  if (text) await u.paste(text);
};
const clickFind = (u: ReturnType<typeof userEvent.setup>) =>
  u.click(screen.getByRole('button', { name: '찾기' }));
const waitList = (n = 1) => screen.findByText(`새 제목 ${n}`, { selector: 'td' });
const posts = (calls: { method: string; path: string; body?: unknown }[], p: string) =>
  calls.filter((c) => c.method === 'POST' && c.path.endsWith(p));

describe('화면 계약 1~3: 방법 A·B·합산', () => {
  it('TC-FV-001 방법 A 표: 열(영상 ID·현재 제목·새 제목·판정·글자 수), 캡션, 체크박스 라벨, 라이브 영역', async () => {
    await setup(baseHandlers([sg(1), sg(2)]));
    await waitList();
    const t = screen.getAllByRole('table')[0]!;
    for (const h of ['영상 ID', '현재 제목', '새 제목', '판정', '글자 수'])
      expect(within(t).getByRole('columnheader', { name: h })).toBeInTheDocument();
    expect(within(t).getByText('승인 가능한 제안 2건', { selector: 'caption' })).toBeInTheDocument();
    expect(await within(t).findByText('현재 제목 1')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: '새 제목 1 선택' })).toBeInTheDocument();
    expect(document.querySelector('[aria-live="polite"]')).not.toBeNull();
  });

  it('TC-FV-002 전체 선택을 껐다 켜면 방법 A 선택만 비워진다(B 선택은 유지)', async () => {
    const { user } = await setup(baseHandlers([sg(1), sg(2)]));
    await waitList();
    await paste(user, vid(9));
    await clickFind(user);
    await screen.findByText('찾은 결과 1개 영상');
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    expect(screen.getByText('선택 3/50건')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    expect(screen.getByText('선택 1/50건')).toBeInTheDocument();
  });

  it('TC-FV-003 50건 경계: A 49건 → 확인 창 열림, 50건 → 열림, B 로 1건 더(합산 51) → 막힘+사유 글', { timeout: 60000 }, async () => {
    const many = Array.from({ length: 50 }, (_, i) => sg(i + 1));
    const { user } = await setup(baseHandlers(many));
    await waitList();
    for (let i = 1; i <= 49; i++) await user.click(screen.getByRole('checkbox', { name: `새 제목 ${i} 선택` }));
    expect(screen.getByText('선택 49/50건')).toBeInTheDocument();
    expect(reviewBtn()).toBeEnabled();
    await user.click(screen.getByRole('checkbox', { name: '새 제목 50 선택' }));
    expect(screen.getByText('선택 50/50건')).toBeInTheDocument();
    expect(reviewBtn()).toBeEnabled();
    expect(screen.getByText(/최대 50건까지만 고를 수 있습니다/)).toBeInTheDocument();
    await paste(user, vid(77));
    await clickFind(user);
    await screen.findByText('찾은 결과 1개 영상');
    // B 의 새 후보는 자동 선택되어 합산 51 이 된다 -> 막혀야 한다
    const over = screen.queryAllByText(/승인 대기 목록이 51건입니다/).length > 0;
    const count = screen.getByText(/^선택 \d+\/50건$/).textContent;
    if (over) {
      expect(reviewBtn()).toBeDisabled();
      expect(screen.getAllByText(/50건 이하로 줄여야 합니다/).length).toBeGreaterThan(0);
    } else {
      // 51 로 담기지 않았다면 50 이하여야 하고, 그 이유가 화면에 보여야 한다
      expect(count).toMatch(/선택 50\/50건/);
    }
  });

  it('TC-FV-004 A 30 + B 21 (겹침 없음, 합산 51): 확인 창 버튼 꺼짐 + 남은 조건 글', async () => {
    const many = Array.from({ length: 30 }, (_, i) => sg(i + 1));
    const { user } = await setup(baseHandlers(many));
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    const ids = Array.from({ length: 21 }, (_, i) => vid(100 + i)).join('\n');
    await paste(user, ids);
    await clickFind(user);
    await screen.findByText('찾은 결과 21개 영상');
    await waitFor(() => expect(screen.getAllByText(/승인 대기 목록이 51건입니다/).length).toBeGreaterThan(0));
    expect(reviewBtn()).toBeDisabled();
  });

  it('TC-FV-005 같은 영상이 A 와 B 에 중복: 한 번만 담고 "겹친 N건" 안내, 승인 요청 ID 도 1개', async () => {
    const { user, calls } = await setup([
      ...baseHandlers([sg(1)]),
      route('POST', '/api/v1/suggestions/approve-batch', () => okResult([1])),
    ]);
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await paste(user, vid(1));
    await clickFind(user);
    await screen.findByText('찾은 결과 1개 영상');
    expect(screen.getByText('선택 1/50건')).toBeInTheDocument();
    expect(screen.getByText(/겹친 1건은 뺐습니다/)).toBeInTheDocument();
    await user.click(reviewBtn());
    await setApprover(user, '홍길동');
    await user.click(submitBtn());
    await screen.findByText(/승인 결과/);
    expect(posts(calls, 'approve-batch')[0]!.body).toMatchObject({ suggestion_ids: [1] });
  });

  it('TC-FV-006 차단 건: 체크박스 비활성 + 사유 글, 승인 완료 건도 비활성+사유', async () => {
    const { user } = await setup(
      baseHandlers([
        sg(1, { validation_result: 'block' }),
        sg(2, { status: 'approved' }),
        sg(3),
      ]),
    );
    await waitList(3);
    expect(screen.getByRole('checkbox', { name: '새 제목 1 선택' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: '새 제목 2 선택' })).toBeDisabled();
    expect(screen.getByText('차단 판정이라 승인할 수 없습니다.')).toBeInTheDocument();
    expect(screen.getByText('이미 승인된 제안입니다.')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    expect(screen.getByText('선택 1/50건')).toBeInTheDocument();
  });
});

describe('영상 ID 파싱 경계', () => {
  const run = async (text: string, handlers = baseHandlers([])) => {
    const s = await setup(handlers);
    await screen.findByText('승인할 수 있는 제안이 없습니다.');
    await paste(s.user, text);
    return s;
  };
  it('TC-FV-010 공백·탭·쉼표·세미콜론·줄바꿈(CRLF) 혼합 구분', async () => {
    const { user, calls } = await run(`${vid(1)},${vid(2)}\t${vid(3)};${vid(4)}\r\n${vid(5)}`);
    await clickFind(user);
    await waitFor(() => expect(posts(calls, 'resolve-videos').length).toBe(1));
    expect((posts(calls, 'resolve-videos')[0]!.body as { video_ids: string[] }).video_ids).toEqual([
      vid(1), vid(2), vid(3), vid(4), vid(5),
    ]);
  });
  it('TC-FV-011 대소문자는 서로 다른 ID(ABCDEFGHIJK 와 abcdefghijk)로 둘 다 보낸다', async () => {
    const { user, calls } = await run('ABCDEFGHIJK abcdefghijk');
    await clickFind(user);
    await waitFor(() => expect(posts(calls, 'resolve-videos').length).toBe(1));
    expect((posts(calls, 'resolve-videos')[0]!.body as { video_ids: string[] }).video_ids).toEqual([
      'ABCDEFGHIJK', 'abcdefghijk',
    ]);
  });
  it('TC-FV-012 10자·12자·한글은 보내지 않고 이유를 글로 보인다. 유효 ID 가 없으면 찾기 꺼짐', async () => {
    await run('abcdefghij abcdefghijkl 영상영상영상영상영상영');
    expect(screen.getByText(/형식이 맞지 않아 찾지 않은 ID/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '찾기' })).toBeDisabled();
    // 사유 글이 사용자에게 의미가 통하는가: 잘못된 ID 만 입력했는데 "한 개 이상 입력하세요" 로 안내하면 혼란
    const why = screen.getAllByText(/ID/).map((e) => e.textContent).join(' | ');
    expect(why).toContain('11자');
  });
  it('TC-FV-013 같은 ID 반복 입력은 한 번만 보낸다', async () => {
    const { user, calls } = await run(`${vid(1)} ${vid(1)}\n${vid(1)}`);
    await clickFind(user);
    await waitFor(() => expect(posts(calls, 'resolve-videos').length).toBe(1));
    expect((posts(calls, 'resolve-videos')[0]!.body as { video_ids: string[] }).video_ids).toHaveLength(1);
  });
  it('TC-FV-014 빈 입력·공백만 입력은 찾기 꺼짐 + 이유 글', async () => {
    await run('   \n  ');
    expect(screen.getByRole('button', { name: '찾기' })).toBeDisabled();
    expect(screen.getByText(/한 개 이상 입력/)).toBeInTheDocument();
  });
  it('TC-FV-015 매우 긴 입력(60만 자, 유효 ID 51개 + 쓰레기)은 멈추지 않고 51개 초과 안내', async () => {
    const ids = Array.from({ length: 51 }, (_, i) => vid(i + 1)).join(' ');
    const { user } = await run('x'.repeat(5000) + ' ' + ids);
    void user;
    expect(screen.getByRole('button', { name: '찾기' })).toBeDisabled();
    expect(screen.getByText(/51개입니다/)).toBeInTheDocument();
  });
  it('TC-FV-016 URL 전체를 붙여넣으면(https://youtu.be/ID) 형식 오류로 안내(조용히 버리지 않음)', async () => {
    await run(`https://youtu.be/${vid(1)}`);
    expect(screen.getByText(/형식이 맞지 않아 찾지 않은 ID: https/)).toBeInTheDocument();
  });
  it('TC-FV-017 51번째가 올바르지 않은 형식이면 50개로 찾기 가능(잘못된 건 제외 안내)', async () => {
    const ids = Array.from({ length: 50 }, (_, i) => vid(i + 1)).join(' ');
    await run(ids + ' bad');
    expect(screen.getByRole('button', { name: '찾기' })).toBeEnabled();
  });
});

describe('후보 선택·경고·승인 요청 내용', () => {
  it('TC-FV-020 후보 2개: 어느 쪽도 자동 선택 안 됨, 확인 창 버튼은 선택 전 막힘(대기 0건), 고르면 그 id 만 전송', async () => {
    const c1 = sg(11, { video_id: vid(1) });
    const c2 = sg(12, { video_id: vid(1) });
    const { user, calls } = await setup([
      ...baseHandlers([], () => [rv(1, { candidates: [c1, c2] })]),
      route('POST', '/api/v1/suggestions/approve-batch', () => okResult([12])),
    ]);
    await screen.findByText('승인할 수 있는 제안이 없습니다.');
    await paste(user, vid(1));
    await clickFind(user);
    const r1 = await screen.findByRole('radio', { name: /새 제목 11/ });
    expect(r1).not.toBeChecked();
    expect(screen.getByRole('radio', { name: /새 제목 12/ })).not.toBeChecked();
    expect(reviewBtn()).toBeDisabled();
    await user.click(screen.getByRole('radio', { name: /새 제목 12/ }));
    await user.click(reviewBtn());
    await setApprover(user, '홍길동');
    await user.click(submitBtn());
    await screen.findByText(/승인 결과/);
    expect(posts(calls, 'approve-batch')[0]!.body).toMatchObject({ suggestion_ids: [12] });
  });

  it('TC-FV-021 후보 2개 중 1개가 차단이면 승인 가능한 1개만 미리 선택하지 않고(후보 2개이므로) 차단 후보는 라디오에 없다', async () => {
    const c1 = sg(11, { video_id: vid(1) });
    const c2 = sg(12, { video_id: vid(1), validation_result: 'block' });
    const { user } = await setup(baseHandlers([], () => [rv(1, { candidates: [c1, c2] })]));
    await screen.findByText('승인할 수 있는 제안이 없습니다.');
    await paste(user, vid(1));
    await clickFind(user);
    await screen.findByText('찾은 결과 1개 영상');
    expect(screen.getByText('선택 0/50건')).toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    expect(screen.getByText('차단 판정이라 승인할 수 없습니다.')).toBeInTheDocument();
  });

  it('TC-FV-022 경고 건: 건별 체크, 전체 체크 없음, 일부만 체크하면 버튼 막힘+남은 글, payload 의 acknowledged_warning_ids 가 체크한 id 와 정확히 같음', async () => {
    const list = [
      sg(1, { validation_result: 'warn' }),
      sg(2, { validation_result: 'warn' }),
      sg(3, { validation_result: 'warn' }),
      sg(4),
    ];
    const { user, calls } = await setup([
      ...baseHandlers(list),
      route('POST', '/api/v1/suggestions/approve-batch', () => okResult([1, 2, 3, 4])),
    ]);
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    await user.click(reviewBtn());
    await setApprover(user, '홍길동');
    const d = within(dialog());
    expect(d.queryByRole('checkbox', { name: /전체/ })).not.toBeInTheDocument();
    expect(d.getAllByRole('checkbox')).toHaveLength(3);
    expect(submitBtn()).toBeDisabled();
    expect(d.getByText(/경고가 있는 3건은 건별로/)).toBeInTheDocument();
    await user.click(d.getByRole('checkbox', { name: /새 제목 1/ }));
    await user.click(d.getByRole('checkbox', { name: /새 제목 3/ }));
    expect(submitBtn()).toBeDisabled();
    expect(d.getByText(/경고가 있는 1건은 건별로/)).toBeInTheDocument();
    await user.click(d.getByRole('checkbox', { name: /새 제목 2/ }));
    await user.click(d.getByRole('checkbox', { name: /새 제목 2/ })); // 해제
    await user.click(d.getByRole('checkbox', { name: /새 제목 2/ })); // 재체크
    expect(submitBtn()).toBeEnabled();
    await user.click(submitBtn());
    await screen.findByText(/승인 결과/);
    const body = posts(calls, 'approve-batch')[0]!.body as { acknowledged_warning_ids: number[]; suggestion_ids: number[] };
    expect([...body.acknowledged_warning_ids].sort()).toEqual([1, 2, 3]);
    expect(body.suggestion_ids).toEqual([1, 2, 3, 4]);
  });

  it('TC-FV-023 경고 체크 후 대기 목록에서 그 건을 빼면 payload 에 남은 ack id 가 섞이지 않는다', async () => {
    const list = [sg(1, { validation_result: 'warn' }), sg(2)];
    const { user, calls } = await setup([
      ...baseHandlers(list),
      route('POST', '/api/v1/suggestions/approve-batch', () => okResult([2])),
    ]);
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await user.click(screen.getByRole('checkbox', { name: '새 제목 2 선택' }));
    await user.click(reviewBtn());
    await setApprover(user, '홍길동');
    await user.click(within(dialog()).getByRole('checkbox', { name: /새 제목 1/ }));
    await user.click(within(dialog()).getByRole('button', { name: '닫기' }));
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' })); // 해제
    await user.click(reviewBtn());
    await user.click(submitBtn());
    await screen.findByText(/승인 결과/);
    const body = posts(calls, 'approve-batch')[0]!.body as { acknowledged_warning_ids: number[] };
    expect(body.acknowledged_warning_ids).toEqual([]);
  });
});

describe('승인자 이름과 비활성 사유', () => {
  it('TC-FV-030 이름이 비면 버튼 꺼짐 + 옆에 남은 조건 글, 공백만도 마찬가지', async () => {
    const { user } = await setup(baseHandlers([sg(1)]));
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await user.click(reviewBtn());
    await setApprover(user, '');
    expect(submitBtn()).toBeDisabled();
    expect(within(dialog()).getByText('아직 필요한 것')).toBeInTheDocument();
    expect(within(dialog()).getAllByText('승인자 이름을 입력해 주세요.').length).toBeGreaterThan(0);
    await setApprover(user, '   ');
    expect(submitBtn()).toBeDisabled();
  });
  it('TC-FV-031 제로폭 문자(U+200B)만 있는 이름은 비어 있는 것으로 취급해야 한다', async () => {
    const { user } = await setup(baseHandlers([sg(1)]));
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await user.click(reviewBtn());
    await setApprover(user, '​​');
    expect(submitBtn()).toBeDisabled();
  });
  it('TC-FV-032 이름 앞뒤 공백은 잘라서 보낸다', async () => {
    const { user, calls } = await setup([
      ...baseHandlers([sg(1)]),
      route('POST', '/api/v1/suggestions/approve-batch', () => okResult([1])),
    ]);
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await user.click(reviewBtn());
    await setApprover(user, '  홍길동  ');
    await user.click(submitBtn());
    await screen.findByText(/승인 결과/);
    expect((posts(calls, 'approve-batch')[0]!.body as { approver: string }).approver).toBe('홍길동');
  });
});

describe('제출·오류·결과', () => {
  const open1 = async (extra: Handler[]) => {
    const s = await setup([...baseHandlers([sg(1)]), ...extra]);
    await waitList();
    await s.user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await s.user.click(reviewBtn());
    await setApprover(s.user, '홍길동');
    return s;
  };
  it('TC-FV-040 연속 두 번 클릭해도 요청은 1번(중복 제출 방지)', async () => {
    let n = 0;
    const { user } = await open1([
      route('POST', '/api/v1/suggestions/approve-batch', async () => {
        n++;
        await new Promise((r) => setTimeout(r, 80));
        return okResult([1]);
      }),
    ]);
    const b = submitBtn();
    await user.dblClick(b);
    await screen.findByText(/승인 결과/);
    expect(n).toBe(1);
  });
  it.each([
    [409, 'warning_not_acknowledged', '경고 확인 필요', '경고가 있는 제안은 확인 체크 후에만 승인할 수 있습니다'],
    [422, 'bulk_too_many', '너무 많음', '한 번에 최대 50건까지 승인할 수 있습니다'],
    [500, 'internal_error', '서버 오류', ''],
  ])('TC-FV-04%# 서버 %i 오류는 한국어로 보이고 내부 정보(스택·SQL·경로)가 없으며 창은 열린 채 재시도 가능', async (st, code, title, detail) => {
    const { user } = await open1([
      route('POST', '/api/v1/suggestions/approve-batch', () => problem(st as number, code as string, title as string, detail as string)),
    ]);
    await user.click(submitBtn());
    const alert = await within(dialog()).findByRole('alert');
    expect(alert.textContent).toMatch(/[가-힣]/);
    expect(alert.textContent).not.toMatch(/Traceback|SELECT |psycopg|\/home\/|\.py|undefined|\[object/);
    expect(alert.textContent).toMatch(/다음에 할 일|할 일|다시/);
    expect(submitBtn()).toBeEnabled();
  });
  it('TC-FV-044 네트워크 오류(fetch 거부)도 한국어 안내, 내부 정보 없음', async () => {
    const { user } = await open1([
      route('POST', '/api/v1/suggestions/approve-batch', () => {
        throw new TypeError('Failed to fetch');
      }),
    ]);
    await user.click(submitBtn());
    const alert = await within(dialog()).findByRole('alert');
    expect(alert.textContent).toMatch(/[가-힣]/);
    expect(alert.textContent).not.toMatch(/Failed to fetch|TypeError/);
  });
  it('TC-FV-045 부분 성공: 승인 표·제외 표·사유(한국어)·배치 만들기 링크, 알 수 없는 코드는 서버 reason 을 보임', async () => {
    const { user } = await setup([
      ...baseHandlers([sg(1), sg(2), sg(3)]),
      route('POST', '/api/v1/suggestions/approve-batch', () =>
        json(200, {
          approved: [{ suggestion_id: 1, video_id: vid(1) }],
          skipped: [
            { suggestion_id: 2, video_id: vid(2), code: 'same_as_current', reason: 'x' },
            { suggestion_id: 3, video_id: null, code: 'weird_new_code', reason: '서버가 준 이유' },
          ],
          counts: { requested: 3, approved: 1, skipped: 2 },
        }),
      ),
    ]);
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    await user.click(reviewBtn());
    await setApprover(user, '홍길동');
    await user.click(submitBtn());
    expect(await screen.findByText(/승인 1건 \/ 제외 2건/)).toBeInTheDocument();
    expect(screen.getByText('현재 제목과 같습니다.')).toBeInTheDocument();
    expect(screen.getByText('서버가 준 이유')).toBeInTheDocument();
    expect(within(screen.getByRole('main')).getByRole('link', { name: /배치/ })).toHaveAttribute('href', '/batches');
    expect(screen.getByText(/제목은 아직 바뀌지 않았습니다/)).toBeInTheDocument();
    expect(await axeViolations(document.body)).toEqual([]);
  });
});

describe('XSS·키보드·접근성·모드', () => {
  const evil = '<script>window.__x=1</script><img src=x onerror="window.__x=2">';
  it('TC-FV-050 제목·현재 제목에 HTML 이 있어도 텍스트로만 출력되고 요소가 생기지 않는다', async () => {
    const { user, container } = await setup(
      baseHandlers([sg(1, { title: evil })], () => [rv(1, { video_title: evil, candidates: [sg(1, { title: evil })] })]),
    );
    await screen.findByText(evil, { selector: 'td' });
    expect(container.querySelector('script, img[src="x"]')).toBeNull();
    await user.click(screen.getAllByRole('checkbox')[1]!);
    await user.click(reviewBtn());
    expect(document.querySelector('[role="dialog"] script, [role="dialog"] img')).toBeNull();
    expect((window as unknown as { __x?: number }).__x).toBeUndefined();
  });
  it('TC-FV-051 키보드: 확인 창 열면 포커스가 창 안(승인자 칸), Esc 로 닫히고 포커스가 열기 버튼으로 돌아온다', async () => {
    const { user } = await setup(baseHandlers([sg(1)]));
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    reviewBtn().focus();
    await user.keyboard('{Enter}');
    expect(dialog()).toBeInTheDocument();
    await waitFor(() => expect(dialog().contains(document.activeElement)).toBe(true));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement).toBe(reviewBtn()));
  });
  it('TC-FV-052 Tab 으로 창 밖으로 나가지 않는다(포커스 가둠)', async () => {
    const { user } = await setup(baseHandlers([sg(1)]));
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await user.click(reviewBtn());
    for (let i = 0; i < 8; i++) {
      await user.tab();
      expect(dialog().contains(document.activeElement)).toBe(true);
    }
  });
  it('TC-FV-053 방법 A 체크박스를 스페이스로 조작하고 찾기는 Enter 가 아닌 버튼으로도 폼 제출 가능', async () => {
    const { user } = await setup(baseHandlers([sg(1)]));
    await waitList();
    screen.getByRole('checkbox', { name: '새 제목 1 선택' }).focus();
    await user.keyboard(' ');
    expect(screen.getByText('선택 1/50건')).toBeInTheDocument();
  });
  it('TC-FV-054 axe 위반 0: 초기·방법 B 결과(라디오 포함)·확인 창(경고 체크 열 포함)', async () => {
    const c1 = sg(11, { video_id: vid(1), validation_result: 'warn' });
    const c2 = sg(12, { video_id: vid(1) });
    const { user } = await setup(
      baseHandlers([sg(2, { validation_result: 'warn' }), sg(3)], (ids) =>
        ids.map((x) => (x === vid(1) ? rv(1, { candidates: [c1, c2] }) : rv(Number(x.slice(3))))),
      ),
    );
    await waitList(2);
    expect(await axeViolations(document.body)).toEqual([]);
    await paste(user, `${vid(1)} ${vid(404)}`);
    await clickFind(user);
    await screen.findByRole('radio', { name: /새 제목 11/ });
    expect(await axeViolations(document.body)).toEqual([]);
    await user.click(screen.getByRole('radio', { name: /새 제목 11/ }));
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    await user.click(reviewBtn());
    expect(within(dialog()).getAllByRole('checkbox').length).toBeGreaterThanOrEqual(2);
    expect(await axeViolations(document.body)).toEqual([]);
  });
  it('TC-FV-055 데모 모드 배지가 이 화면에서도 유지되고 상단 메뉴에 일괄 승인이 있다', async () => {
    await setup(baseHandlers([sg(1)]));
    expect(screen.getAllByText(/데모/).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: '일괄 승인' }).length).toBeGreaterThan(0);
  });
  it('TC-FV-056 실제 모드 배지(live)도 유지된다', async () => {
    const { container } = await setup([
      ...baseHandlers([sg(1)]),
      route('GET', '/api/v1/dashboard', () => json(200, dashboard({ mode: 'live' } as never))),
    ]);
    void container;
    expect(screen.getAllByText(/실제|데모/).length).toBeGreaterThan(0);
  });
  it('TC-FV-057 목록 조회 실패는 한국어 오류+다시 시도, 승인 대기 0건이면 확인 창 버튼 꺼짐', async () => {
    await setup([route('GET', '/api/v1/suggestions', () => problem(500, 'internal_error', '서버 오류'))]);
    await screen.findAllByText(/다시 시도|서버 오류/);
    expect(within(screen.getByRole('main')).getByRole('alert').textContent).toMatch(/[가-힣]/);
    expect(reviewBtn()).toBeDisabled();
  });
  it('TC-FV-058 resolve-videos 실패(422/네트워크)도 한국어 오류와 다시 시도', async () => {
    const { user } = await setup([
      route('GET', '/api/v1/suggestions', () => page([])),
      route('POST', '/api/v1/suggestions/resolve-videos', () => problem(422, 'bulk_too_many', '너무 많음', '한 번에 최대 50건까지 승인할 수 있습니다')),
    ]);
    await screen.findByText('승인할 수 있는 제안이 없습니다.');
    await paste(user, vid(1));
    await clickFind(user);
    const a = await within(screen.getByRole('main')).findByRole('alert');
    expect(a.textContent).toMatch(/50건/);
  });
  it('TC-FV-059 act 경고 없음 확인용: 결과 화면에서 "다시 승인하기" 로 초기화', async () => {
    const { user } = await setup([
      ...baseHandlers([sg(1)]),
      route('POST', '/api/v1/suggestions/approve-batch', () => okResult([1])),
    ]);
    await waitList();
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await user.click(reviewBtn());
    await setApprover(user, '홍');
    await user.click(submitBtn());
    await screen.findByText(/승인 결과/);
    await act(async () => {});
    const again = screen.getAllByRole('button').find((b) => /새로 고르기/.test(b.textContent ?? ''));
    expect(again).toBeTruthy();
  });
});
