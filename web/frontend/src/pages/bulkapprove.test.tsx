import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { ResolvedVideo, Suggestion } from '../api/types';
import { suggestion } from '../test/fixtures';
import {
  axeViolations,
  connectedClient,
  json,
  problem,
  renderWithApp,
  route,
  type Handler,
} from '../test/utils';
import { BulkApprovePage, parseVideoIds } from './BulkApprovePage';

const routes = (
  <Routes>
    <Route path="bulk-approve" element={<BulkApprovePage />} />
    <Route path="batches" element={<div>배치 화면</div>} />
  </Routes>
);
const vid = (n: number) => `vid${String(n).padStart(8, '0')}`;
const sg = (id: number, over: Partial<Suggestion> = {}) =>
  suggestion(id, { video_id: vid(id), title: `새 제목 ${id}`, ...over });
const page = (items: unknown[]) =>
  json(200, { items, total: items.length, page: 1, page_size: 50 });
const lists = (cand: Suggestion[], exp: Suggestion[] = []): Handler[] => [
  route('GET', '/api/v1/suggestions', (r) =>
    page(r.query.get('status') === 'expired' ? exp : cand),
  ),
];
const resolveRoute = (items: ResolvedVideo[]) =>
  route('POST', '/api/v1/suggestions/resolve-videos', () => json(200, { items }));
const rv = (n: number, over: Partial<ResolvedVideo> = {}): ResolvedVideo => ({
  video_id: vid(n),
  found: true,
  video_title: `현재 제목 ${n}`,
  excluded_reasons: [],
  candidates: [sg(n)],
  ...over,
});
const okResult = (ids: number[]) =>
  json(200, {
    approved: ids.map((i) => ({ suggestion_id: i, video_id: vid(i) })),
    skipped: [],
    counts: { requested: ids.length, approved: ids.length, skipped: 0 },
  });

async function setup(handlers: Handler[]) {
  const user = userEvent.setup();
  const c = await connectedClient(handlers);
  const r = renderWithApp(routes, c.client, '/bulk-approve');
  return { user, ...c, ...r };
}
const reviewBtn = () => screen.getByRole('button', { name: '확인 창 열기' });
const approverBox = () => screen.getByRole('textbox', { name: /승인자 이름/ });
const typeApprover = async (user: ReturnType<typeof userEvent.setup>, v: string) => {
  await user.clear(approverBox());
  await user.type(approverBox(), v);
};
const dialog = () => screen.getByRole('dialog');
const submitBtn = () => within(dialog()).getByRole('button', { name: /건 승인$/ });
const find = async (user: ReturnType<typeof userEvent.setup>, text: string) => {
  const box = screen.getByRole('textbox', { name: /영상 ID/ });
  await user.clear(box);
  await user.click(box);
  await user.paste(text);
  await user.click(screen.getByRole('button', { name: '찾기' }));
};

describe('파싱', () => {
  it('TC-FE-BA-001 줄바꿈·쉼표·공백으로 나누고 중복을 없애며 잘못된 형식을 따로 모은다', () => {
    const r = parseVideoIds(`${vid(1)}\n${vid(2)}, ${vid(3)}  ${vid(1)};short`);
    expect(r.valid).toEqual([vid(1), vid(2), vid(3)]);
    expect(r.invalid).toEqual(['short']);
  });
});

describe('방법 A', () => {
  it('TC-FE-BA-002 표를 그리고 선택하면 선택 N/50 과 승인 대기 목록에 반영한다', async () => {
    const { user } = await setup(lists([sg(1), sg(2)], [sg(3, { status: 'expired' })]));
    await screen.findByText('새 제목 1', { selector: 'td' });
    expect(screen.getByText('승인 가능한 제안 3건')).toBeInTheDocument();
    expect(screen.getByText('선택 0/50건')).toBeInTheDocument();
    expect(reviewBtn()).toBeDisabled();
    expect(screen.getByText('승인 대기 목록이 비어 있어 누를 수 없습니다.')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await user.click(screen.getByRole('checkbox', { name: '새 제목 3 선택' }));
    expect(screen.getByText('선택 2/50건')).toBeInTheDocument();
    expect(reviewBtn()).toBeEnabled();
  });

  it('TC-FE-BA-003 차단 건은 체크박스가 꺼지고 사유가 글로 보이며, 전체 선택에도 들어가지 않는다', async () => {
    const { user } = await setup(
      lists([
        sg(1),
        sg(2, { validation_result: 'block' }),
        sg(3, { strict: true, validation_result: 'warn' }),
      ]),
    );
    await screen.findByText('새 제목 1', { selector: 'td' });
    expect(screen.getByRole('checkbox', { name: '새 제목 2 선택' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: '새 제목 3 선택' })).toBeDisabled();
    expect(screen.getByText('차단 판정이라 승인할 수 없습니다.')).toBeInTheDocument();
    expect(screen.getByText(/엄격 모드/)).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    expect(screen.getByText('선택 1/50건')).toBeInTheDocument();
  });

  it('TC-FE-BA-004 50건이 차면 더 고를 수 없고 안내를 보여 준다', async () => {
    const many = Array.from({ length: 51 }, (_, i) => sg(i + 1));
    const { user } = await setup(lists(many));
    await screen.findByText('새 제목 1', { selector: 'td' });
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    expect(screen.getByText('선택 50/50건')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: '새 제목 51 선택' })).toBeDisabled();
    expect(screen.getByText(/최대 50건까지만 고를 수 있습니다/)).toBeInTheDocument();
    expect(reviewBtn()).toBeEnabled();
  });
});

describe('방법 B', () => {
  it('TC-FE-BA-005 붙여넣기 → 찾기는 중복을 뺀 올바른 ID 만 보내고 잘못된 ID 는 안내한다', async () => {
    const { user, calls } = await setup([...lists([]), resolveRoute([rv(1), rv(2)])]);
    await screen.findByText('승인할 수 있는 제안이 없습니다.');
    await find(user, `${vid(1)}, ${vid(2)}\n${vid(1)} abc`);
    expect(screen.getByText(/형식이 맞지 않아 찾지 않은 ID: abc/)).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith('resolve-videos'))?.body).toEqual({
        video_ids: [vid(1), vid(2)],
      }),
    );
    expect(await screen.findByText('찾은 결과 2개 영상')).toBeInTheDocument();
  });

  it('TC-FE-BA-006 비어 있으면 찾기가 꺼지고 이유가 글로 보인다', async () => {
    await setup(lists([]));
    expect(await screen.findByRole('button', { name: '찾기' })).toBeDisabled();
    expect(screen.getByText(/영상 ID 를 한 개 이상 입력/)).toBeInTheDocument();
  });

  it('TC-FE-BA-007 51개를 넣으면 찾기가 꺼지고 줄이라고 안내한다', async () => {
    const { user } = await setup(lists([]));
    await screen.findByText('승인할 수 있는 제안이 없습니다.');
    const ids = Array.from({ length: 51 }, (_, i) => vid(i + 1)).join('\n');
    const box = screen.getByRole('textbox', { name: /영상 ID/ });
    await user.click(box);
    await user.paste(ids);
    expect(screen.getByRole('button', { name: '찾기' })).toBeDisabled();
    expect(screen.getByText('영상 ID 가 51개입니다. 50개 이하로 줄여 주세요.')).toBeInTheDocument();
  });

  it('TC-FE-BA-008 못 찾음·제외·후보 0개는 따로 표시하고 승인 대기에 넣지 않는다', async () => {
    const { user } = await setup([
      ...lists([]),
      resolveRoute([
        rv(1, { found: false, video_title: null, candidates: [] }),
        rv(2, { excluded_reasons: ['쇼츠'], candidates: [sg(2)] }),
        rv(3, { candidates: [] }),
      ]),
    ]);
    await screen.findByText('승인할 수 있는 제안이 없습니다.');
    await find(user, `${vid(1)} ${vid(2)} ${vid(3)}`);
    expect(await screen.findByText(/없음 \(이 영상은 목록에 없습니다\)/)).toBeInTheDocument();
    expect(screen.getByText('제외 대상: 쇼츠')).toBeInTheDocument();
    expect(screen.getByText(/후보 제안 없음/)).toBeInTheDocument();
    expect(screen.getByText('선택 0/50건')).toBeInTheDocument();
    expect(reviewBtn()).toBeDisabled();
  });

  it('TC-FE-BA-009 후보가 여러 개면 라디오를 고르기 전에는 승인 대기에 들어가지 않는다(자동 선택 금지)', async () => {
    const { user } = await setup([
      ...lists([]),
      resolveRoute([
        rv(1, { candidates: [sg(11, { video_id: vid(1) }), sg(12, { video_id: vid(1) })] }),
      ]),
    ]);
    await screen.findByText('승인할 수 있는 제안이 없습니다.');
    await find(user, vid(1));
    const r1 = await screen.findByRole('radio', { name: /새 제목 11/ });
    const r2 = screen.getByRole('radio', { name: /새 제목 12/ });
    expect(r1).not.toBeChecked();
    expect(r2).not.toBeChecked();
    expect(screen.getByText('선택 필요')).toBeInTheDocument();
    expect(screen.getByText('선택 0/50건')).toBeInTheDocument();
    expect(screen.getByText(/후보를 고르지 않은 영상이 1개/)).toBeInTheDocument();
    await user.click(r2);
    expect(screen.getByText('선택 1/50건')).toBeInTheDocument();
    expect(screen.queryByText('선택 필요')).not.toBeInTheDocument();
  });

  it('TC-FE-BA-010 후보가 1개면 미리 선택되고 안내가 나온다', async () => {
    const { user } = await setup([...lists([]), resolveRoute([rv(1)])]);
    await screen.findByText('승인할 수 있는 제안이 없습니다.');
    await find(user, vid(1));
    expect(await screen.findByText('선택 1/50건')).toBeInTheDocument();
    expect(screen.getByText(/후보가 1개라 미리 선택했습니다/)).toBeInTheDocument();
  });

  it('TC-FE-BA-011 방법 A 와 B 가 같은 영상을 고르면 한 건만 담는다', async () => {
    const { user } = await setup([...lists([sg(1)]), resolveRoute([rv(1)])]);
    await screen.findByText('새 제목 1', { selector: 'td' });
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await find(user, vid(1));
    expect(await screen.findByText(/겹친 1건은 뺐습니다/)).toBeInTheDocument();
    expect(screen.getByText('선택 1/50건')).toBeInTheDocument();
  });
});

describe('확인 창·제출', () => {
  const warnS = (id: number) => sg(id, { validation_result: 'warn' });

  it('TC-FE-BA-012 승인자가 비면 사유가 보이고 버튼이 꺼진다. "승인만" 문구가 있다', async () => {
    const { user } = await setup(lists([sg(41)]));
    await screen.findByText('새 제목 41', { selector: 'td' });
    await user.click(screen.getByRole('checkbox', { name: '새 제목 41 선택' }));
    await user.click(reviewBtn());
    expect(submitBtn()).toBeDisabled();
    expect(within(dialog()).getByText('아직 필요한 것')).toBeInTheDocument();
    expect(within(dialog()).getAllByText('승인자 이름을 입력해 주세요.').length).toBeGreaterThan(0);
    expect(
      within(dialog()).getByText(/승인만 합니다\. 제목은 아직 바뀌지 않습니다/),
    ).toBeInTheDocument();
    await typeApprover(user, '홍길동');
    expect(submitBtn()).toBeEnabled();
    expect(within(dialog()).queryByText('아직 필요한 것')).not.toBeInTheDocument();
  });

  it('TC-FE-BA-013 경고 건은 건별 체크 전까지 꺼지고 남은 조건을 글로 보인다. 전체 체크 버튼은 없다', async () => {
    const { user } = await setup(lists([warnS(1), warnS(2), sg(3)]));
    await screen.findByText('새 제목 1', { selector: 'td' });
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    await user.click(reviewBtn());
    await typeApprover(user, '홍길동');
    expect(submitBtn()).toBeDisabled();
    expect(within(dialog()).getByText(/경고가 있는 2건은 건별로/)).toBeInTheDocument();
    expect(within(dialog()).queryByRole('checkbox', { name: /전체/ })).not.toBeInTheDocument();
    expect(within(dialog()).getAllByRole('checkbox')).toHaveLength(2);
    await user.click(within(dialog()).getByRole('checkbox', { name: /새 제목 1/ }));
    expect(submitBtn()).toBeDisabled();
    expect(within(dialog()).getByText(/경고가 있는 1건은 건별로/)).toBeInTheDocument();
    await user.click(within(dialog()).getByRole('checkbox', { name: /새 제목 2/ }));
    expect(submitBtn()).toBeEnabled();
  });

  it('TC-FE-BA-014 제출 payload: 선택 id 와 확인 체크한 경고 id 만 보낸다. 승인자는 앞뒤 공백 제거', async () => {
    const { user, calls } = await setup([
      ...lists([warnS(1), warnS(2), sg(3)]),
      route('POST', '/api/v1/suggestions/approve-batch', () => okResult([1, 2, 3])),
    ]);
    await screen.findByText('새 제목 1', { selector: 'td' });
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    await user.click(reviewBtn());
    await typeApprover(user, '  홍길동 ');
    await user.click(within(dialog()).getByRole('checkbox', { name: /새 제목 1/ }));
    await user.click(within(dialog()).getByRole('checkbox', { name: /새 제목 2/ }));
    await user.click(submitBtn());
    await screen.findByText(/승인 3건 \/ 제외 0건/);
    const post = calls.find((c) => c.path.endsWith('approve-batch'))!;
    expect(post.body).toEqual({
      approver: '홍길동',
      suggestion_ids: [1, 2, 3],
      acknowledged_warning_ids: [1, 2],
    });
    expect(post.headers['idempotency-key']).toBeTruthy();
    expect(post.headers['x-csrf-token']).toBeTruthy();
  });

  it('TC-FE-BA-015 경고 1건만 체크하면 그 id 만 ack 에 들어간다', async () => {
    const { user, calls } = await setup([
      ...lists([warnS(1), warnS(2)]),
      route('POST', '/api/v1/suggestions/approve-batch', () => okResult([1])),
    ]);
    await screen.findByText('새 제목 1', { selector: 'td' });
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await user.click(reviewBtn());
    await typeApprover(user, '홍');
    await user.click(within(dialog()).getByRole('checkbox', { name: /새 제목 1/ }));
    await user.click(submitBtn());
    await screen.findByText(/승인 1건/);
    expect(calls.find((c) => c.path.endsWith('approve-batch'))!.body).toMatchObject({
      suggestion_ids: [1],
      acknowledged_warning_ids: [1],
    });
  });

  it('TC-FE-BA-016 결과 패널: 승인/제외 사유 표(한국어), 부분 성공, 배치 링크, 승인만 했다는 문구', async () => {
    const { user } = await setup([
      ...lists([sg(1), sg(2)]),
      route('POST', '/api/v1/suggestions/approve-batch', () =>
        json(200, {
          approved: [{ suggestion_id: 1, video_id: vid(1) }],
          skipped: [
            { suggestion_id: 2, video_id: vid(2), code: 'same_as_current', reason: 'x' },
            { suggestion_id: 9, video_id: null, code: 'unknown_code', reason: '서버가 준 사유' },
          ],
          counts: { requested: 3, approved: 1, skipped: 2 },
        }),
      ),
    ]);
    await screen.findByText('새 제목 1', { selector: 'td' });
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    await user.click(reviewBtn());
    await typeApprover(user, '홍');
    await user.click(submitBtn());
    expect(await screen.findByText(/승인 1건 \/ 제외 2건/)).toBeInTheDocument();
    expect(screen.getByText('현재 제목과 같습니다.')).toBeInTheDocument();
    expect(screen.getByText('서버가 준 사유')).toBeInTheDocument();
    expect(screen.getByText('제외된 2건과 사유', { selector: 'caption' })).toBeInTheDocument();
    expect(screen.getByText('승인된 1건', { selector: 'caption' })).toBeInTheDocument();
    expect(screen.getByText(/승인만 했습니다\. 제목은 아직 바뀌지 않았습니다/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '배치 만들기로 이동' })).toHaveAttribute(
      'href',
      '/batches',
    );
  });

  it.each([
    [409, 'warning_not_acknowledged', '경고 확인이 필요합니다'],
    [422, 'bulk_too_many', '한 번에 최대 50건까지 승인할 수 있습니다'],
    [500, 'internal_error', '서버 오류가 났습니다'],
  ])(
    'TC-FE-BA-017 서버 오류 %i 를 확인 창 안에 한국어로 보이고 창을 유지한다',
    async (st, code, title) => {
      const { user } = await setup([
        ...lists([sg(1)]),
        route('POST', '/api/v1/suggestions/approve-batch', () => problem(st, code, title)),
      ]);
      await screen.findByText('새 제목 1', { selector: 'td' });
      await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
      await user.click(reviewBtn());
      await typeApprover(user, '홍');
      await user.click(submitBtn());
      expect(await within(dialog()).findByText(title)).toBeInTheDocument();
      expect(submitBtn()).toBeEnabled();
    },
  );

  it('TC-FE-BA-018 제출 중에는 버튼이 꺼져 중복 제출이 한 번만 나간다', async () => {
    let release: (r: Response) => void = () => {};
    const { user, calls } = await setup([
      ...lists([sg(1)]),
      route(
        'POST',
        '/api/v1/suggestions/approve-batch',
        () => new Promise<Response>((res) => (release = res)) as unknown as Response,
      ),
    ]);
    await screen.findByText('새 제목 1', { selector: 'td' });
    await user.click(screen.getByRole('checkbox', { name: '새 제목 1 선택' }));
    await user.click(reviewBtn());
    await typeApprover(user, '홍');
    await user.click(submitBtn());
    const busy = await within(dialog()).findByRole('button', { name: '승인하는 중' });
    expect(busy).toBeDisabled();
    await user.click(busy);
    expect(calls.filter((c) => c.path.endsWith('approve-batch'))).toHaveLength(1);
    release(okResult([1]));
    await screen.findByText(/승인 1건/);
    expect(calls.filter((c) => c.path.endsWith('approve-batch'))).toHaveLength(1);
  });
});

describe('접근성', () => {
  it('TC-FE-BA-019 표 캡션·체크박스 라벨·라이브 영역이 있고 axe 위반이 0이다(화면·확인 창)', async () => {
    const { user, container } = await setup([
      ...lists([sg(1), sg(2, { validation_result: 'warn' })]),
      resolveRoute([
        rv(5, { candidates: [sg(51, { video_id: vid(5) }), sg(52, { video_id: vid(5) })] }),
      ]),
    ]);
    await screen.findByText('새 제목 1', { selector: 'td' });
    await find(user, vid(5));
    await screen.findByRole('radio', { name: /새 제목 51/ });
    expect(container.querySelectorAll('caption').length).toBeGreaterThanOrEqual(2);
    expect(container.querySelector('[aria-live="polite"]')).not.toBeNull();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole('checkbox', { name: '현재 목록 전체 선택' }));
    await user.click(reviewBtn());
    expect(await axeViolations(dialog())).toEqual([]);
  });

  it('TC-FE-BA-020 키보드만으로 체크박스를 선택할 수 있다(Space)', async () => {
    const { user } = await setup(lists([sg(1)]));
    await screen.findByText('새 제목 1', { selector: 'td' });
    screen.getByRole('checkbox', { name: '새 제목 1 선택' }).focus();
    await user.keyboard(' ');
    expect(screen.getByText('선택 1/50건')).toBeInTheDocument();
  });
});
