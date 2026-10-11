import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { Suggestion, VideoDetail } from '../api/types';
import { detail, suggestion } from '../test/fixtures';
import { connectedClient, json, problem, renderWithApp, route, type Handler } from '../test/utils';
import { VideoDetailPage } from './VideoDetailPage';

const ui = (
  <Routes>
    <Route path="videos/:videoId" element={<VideoDetailPage />} />
  </Routes>
);
const go = async (d: VideoDetail, extra: Handler[] = []) => {
  const c = await connectedClient([
    route('GET', '/api/v1/videos/vid00000001', () => json(200, d)),
    ...extra,
  ]);
  renderWithApp(ui, c.client, '/videos/vid00000001');
  return c;
};
const trio: Suggestion[] = [
  suggestion(1, { title: '테스트 영상 1 핵심 정리', validation_result: 'pass' }),
  suggestion(2, {
    title: '이거 모르면 큰일! 테스트 영상 1',
    validation_result: 'warn',
    reasons: [{ code: 'risky', severity: 'warn', message: '공포를 조장할 수 있는 표현' }],
  }),
  suggestion(3, {
    title: '테스트 100% 무조건',
    validation_result: 'block',
    reasons: [{ code: 'banned', severity: 'block', message: '근거 없는 100% 단정' }],
  }),
];
const card = (id: number) =>
  document.querySelector<HTMLElement>(`#sg-${id}`)!.closest('article') as HTMLElement;

describe('영상 상세', () => {
  it('TC-WF-034 제안 카드마다 통과/경고/차단 뱃지와 사유 목록을 보여 준다', async () => {
    await go(detail(trio));
    await screen.findByText('테스트 영상 1 핵심 정리');
    expect(within(card(1)).getByText('통과')).toBeInTheDocument();
    expect(within(card(2)).getByText('경고')).toBeInTheDocument();
    expect(within(card(2)).getByText(/공포를 조장할 수 있는 표현/)).toBeInTheDocument();
    expect(within(card(3)).getByText('차단')).toBeInTheDocument();
    // 같은 사유가 "검증 사유"와 "승인할 수 없는 이유" 두 곳에 보인다(DEF-7-008)
    expect(within(card(3)).getAllByText(/근거 없는 100% 단정/).length).toBeGreaterThanOrEqual(2);
    expect(within(card(3)).getByText('[차단 사유]')).toBeInTheDocument();
  });

  it('TC-WF-035 현재 제목, 변경 전/후 비교와 글자 수를 보여 준다', async () => {
    await go(detail([trio[0]!]));
    await screen.findByText('테스트 영상 1 핵심 정리');
    expect(screen.getAllByText('테스트 영상 1').length).toBeGreaterThan(0);
    expect(within(card(1)).getByText('변경 전/후 비교')).toBeInTheDocument();
    expect(within(card(1)).getByText(/글자 수 \d+자 → \d+자/)).toBeInTheDocument();
  });

  it('TC-WF-036 차단 판정 제안은 승인 버튼이 꺼지고 이유가 보인다', async () => {
    await go(detail([trio[2]!]));
    await screen.findByText('테스트 100% 무조건');
    const approve = within(card(3)).getByRole('button', { name: '승인' });
    expect(approve).toBeDisabled();
    expect(approve).toHaveAccessibleDescription(/차단 판정이라 승인할 수 없습니다/);
  });

  it('TC-WF-037 경고 제안은 사유 확인 체크 후에만 승인할 수 있고, 승인자와 함께 요청을 보낸다', async () => {
    const user = userEvent.setup();
    const approved = suggestion(2, { status: 'approved', validation_result: 'warn' });
    const { calls } = await go(detail([trio[1]!]), [
      route('POST', '/api/v1/suggestions/2/approve', () => json(200, approved)),
    ]);
    await screen.findByText('이거 모르면 큰일! 테스트 영상 1');
    await user.click(within(card(2)).getByRole('button', { name: '승인' }));
    const dlg = await screen.findByRole('dialog', { name: '이 제안을 승인' });
    const submit = within(dlg).getByRole('button', { name: '승인' });
    await user.type(within(dlg).getByLabelText('승인자 이름'), '홍길동');
    expect(submit).toBeDisabled();
    await user.click(within(dlg).getByRole('checkbox', { name: /경고 사유를 모두 읽고/ }));
    expect(submit).toBeEnabled();
    await user.click(submit);
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith('/approve'))?.body).toEqual({ approver: '홍길동' }),
    );
    expect(await screen.findByText('승인했습니다.')).toBeInTheDocument();
  });

  it('TC-WF-038 서버가 승인을 거절(409)하면 사유와 조치를 대화상자 안에 보여 준다', async () => {
    const user = userEvent.setup();
    await go(detail([trio[0]!]), [
      route('POST', '/api/v1/suggestions/1/approve', () =>
        problem(
          409,
          'suggestion_blocked',
          '차단 판정이라 승인할 수 없습니다',
          '규칙 위반',
          '제목을 수정해 보세요',
        ),
      ),
    ]);
    await screen.findByText('테스트 영상 1 핵심 정리');
    await user.click(within(card(1)).getByRole('button', { name: '승인' }));
    const dlg = await screen.findByRole('dialog');
    await user.type(within(dlg).getByLabelText('승인자 이름'), '홍');
    await user.click(within(dlg).getByRole('button', { name: '승인' }));
    expect(await within(dlg).findByText('규칙 위반')).toBeInTheDocument();
    expect(within(dlg).getByText(/제목을 수정해 보세요/)).toBeInTheDocument();
  });

  it('TC-WF-039 반려는 확인 단계를 거친 뒤에만 요청한다', async () => {
    const user = userEvent.setup();
    const { calls } = await go(detail([trio[0]!]), [
      route('POST', '/api/v1/suggestions/1/reject', () =>
        json(200, suggestion(1, { status: 'rejected' })),
      ),
    ]);
    await screen.findByText('테스트 영상 1 핵심 정리');
    await user.click(within(card(1)).getByRole('button', { name: '반려' }));
    expect(calls.some((c) => c.path.endsWith('/reject'))).toBe(false);
    const dlg = await screen.findByRole('dialog', { name: '이 제안을 반려할까요?' });
    await user.click(within(dlg).getByRole('button', { name: '반려' }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/reject'))).toBe(true));
  });

  it('TC-WF-040 제목 수정은 빈 값·같은 값을 막고, 저장하면 PATCH 를 보낸다', async () => {
    const user = userEvent.setup();
    const { calls } = await go(detail([trio[0]!]), [
      route('PATCH', '/api/v1/suggestions/1', (r) =>
        json(200, suggestion(1, { title: (r.body as { title: string }).title, source: 'manual' })),
      ),
    ]);
    await screen.findByText('테스트 영상 1 핵심 정리');
    await user.click(within(card(1)).getByRole('button', { name: '제목 수정' }));
    const dlg = await screen.findByRole('dialog');
    const input = within(dlg).getByLabelText('새 제목');
    const save = within(dlg).getByRole('button', { name: '저장' });
    expect(save).toBeDisabled();
    await user.clear(input);
    expect(await within(dlg).findByText('제목을 입력해 주세요.')).toBeInTheDocument();
    await user.type(input, '새로 쓴 제목');
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ title: '새로 쓴 제목' }),
    );
  });

  it('TC-WF-041 변경 한도를 못 채우면(한도 초과) 사유와 다시 가능한 시각을 보여 준다', async () => {
    await go(
      detail([], {
        limits: {
          allowed: false,
          reasons: [
            '같은 영상은 72시간 안에 다시 바꿀 수 없습니다.',
            { message: '영상당 최대 3회' },
          ],
          next_allowed_at: '2026-10-13T00:00:00Z',
        },
      }),
    );
    expect(await screen.findByText(/지금은 이 영상의 제목을 바꿀 수 없습니다/)).toBeInTheDocument();
    expect(screen.getByText('영상당 최대 3회')).toBeInTheDocument();
    expect(screen.getByText(/2026-10-13 09:00/)).toBeInTheDocument();
  });

  it('TC-WF-042 제안이 없으면 빈 상태 안내를, 제외 영상이면 제안 생성을 막는다', async () => {
    await go(detail([], { excluded: true, exclusion_reasons: ['비공개 영상'] }));
    expect(await screen.findByText('아직 제안이 없습니다.')).toBeInTheDocument();
    expect(screen.getByText('이 영상은 제외 대상입니다')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'AI 제안 만들기' })).toBeDisabled();
  });

  it('TC-WF-043 없는 영상(404)은 안내 화면을 보여 준다', async () => {
    const c = await connectedClient([
      route('GET', '/api/v1/videos/nope', () =>
        problem(404, 'video_not_found', '영상을 찾을 수 없습니다'),
      ),
    ]);
    renderWithApp(ui, c.client, '/videos/nope');
    expect(await screen.findByText('영상을 찾을 수 없습니다')).toBeInTheDocument();
  });

  it('TC-WF-044 AI 제안 만들기를 누르면 요청하는 동안 버튼이 비활성(중복 클릭 방지)이다', async () => {
    const user = userEvent.setup();
    let release: (r: Response) => void = () => undefined;
    const { calls } = await go(detail([]), [
      route(
        'POST',
        '/api/v1/videos/vid00000001/suggestions',
        () => new Promise<Response>((res) => (release = res)),
      ),
    ]);
    const btn = await screen.findByRole('button', { name: 'AI 제안 만들기' });
    await user.click(btn);
    const busy = await screen.findByRole('button', { name: /제안 만드는 중/ });
    expect(busy).toBeDisabled();
    await user.click(busy);
    release(json(201, [suggestion(9)]));
    await screen.findByText('제안 1개를 만들었습니다.');
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1);
  });
});
