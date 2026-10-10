import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { video } from '../test/fixtures';
import { connectedClient, json, problem, renderWithApp, route } from '../test/utils';
import { VideosPage } from './VideosPage';

const pageOf = (items: ReturnType<typeof video>[], page: number, total: number) => ({
  items,
  total,
  page,
  page_size: 2,
});
const listRoute = route('GET', '/api/v1/videos', (req) => {
  const p = Number(req.query.get('page') ?? '1');
  return json(
    200,
    p === 1
      ? pageOf([video(1), video(2)], 1, 4)
      : pageOf([video(3), video(4, { excluded: true, exclusion_reasons: ['비공개 영상'] })], 2, 4),
  );
});

describe('영상 목록', () => {
  it('TC-WF-027 검색어와 필터를 서버 쿼리로 보낸다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([listRoute]);
    renderWithApp(<VideosPage />, client, '/videos');
    await screen.findByText('테스트 영상 1');
    await user.type(screen.getByLabelText('제목 또는 영상 ID 검색'), '전기');
    await user.selectOptions(screen.getByLabelText('진행 상태'), 'approved');
    await user.click(screen.getByRole('button', { name: '검색' }));
    await waitFor(() => {
      const last = calls.filter((c) => c.path === '/api/v1/videos').at(-1);
      expect(last?.query.get('q')).toBe('전기');
      expect(last?.query.get('status')).toBe('approved');
      expect(last?.query.get('page')).toBe('1');
    });
  });

  it('TC-WF-028 페이지를 넘겨도 선택이 유지되고 선택 개수가 보인다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([listRoute]);
    renderWithApp(<VideosPage />, client, '/videos?page_size=2');
    await screen.findByText('테스트 영상 1');
    await user.click(screen.getByRole('checkbox', { name: '테스트 영상 1 선택' }));
    expect(screen.getAllByText('1개 선택됨').length).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: '다음' }));
    await screen.findByText('테스트 영상 3');
    await user.click(screen.getByRole('checkbox', { name: '테스트 영상 3 선택' }));
    expect(screen.getAllByText('2개 선택됨').length).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: '이전' }));
    await screen.findByText('테스트 영상 2');
    expect(screen.getByRole('checkbox', { name: '테스트 영상 1 선택' })).toBeChecked();
  });

  it('TC-WF-029 제외된 영상은 선택할 수 없고 제외 사유가 보인다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([listRoute]);
    renderWithApp(<VideosPage />, client, '/videos?page=2&page_size=2');
    await screen.findByText('테스트 영상 4');
    expect(screen.getByRole('checkbox', { name: '테스트 영상 4 선택' })).toBeDisabled();
    expect(screen.getByText('비공개 영상')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: '이 페이지 전체 선택' }));
    expect(screen.getByRole('checkbox', { name: '테스트 영상 3 선택' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '테스트 영상 4 선택' })).not.toBeChecked();
  });

  it('TC-WF-030 선택한 영상(여러 쪽)으로 AI 제안 생성을 요청하고 작업 진행·완료를 보여 준다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([
      listRoute,
      route('POST', '/api/v1/suggestions/generate', () =>
        json(202, {
          id: 'job-1',
          type: 'suggestions.generate',
          status: 'queued',
          progress: 0,
          total: 2,
          error: null,
          result: null,
        }),
      ),
      route('GET', '/api/v1/jobs/job-1', () =>
        json(200, {
          id: 'job-1',
          type: 'suggestions.generate',
          status: 'succeeded',
          progress: 2,
          total: 2,
          error: null,
          result: null,
        }),
      ),
    ]);
    renderWithApp(<VideosPage />, client, '/videos?page_size=2');
    await screen.findByText('테스트 영상 1');
    await user.click(screen.getByRole('checkbox', { name: '테스트 영상 1 선택' }));
    await user.click(screen.getByRole('button', { name: '다음' }));
    await screen.findByText('테스트 영상 3');
    await user.click(screen.getByRole('checkbox', { name: '테스트 영상 3 선택' }));
    await user.click(screen.getByRole('button', { name: '선택 영상 AI 제안 생성' }));
    const dlg = await screen.findByRole('dialog', { name: 'AI 제안 생성' });
    await within(dlg).findByText(/2 \/ 2 처리됨/);
    expect(calls.find((c) => c.path === '/api/v1/suggestions/generate')?.body).toEqual({
      video_ids: ['vid00000001', 'vid00000003'],
    });
    await waitFor(() => expect(within(dlg).getByRole('button', { name: '닫기' })).toBeEnabled());
  });

  it('TC-WF-031 조건에 맞는 영상이 없으면 안내와 필터 초기화 버튼을 보여 준다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/videos', () =>
        json(200, { items: [], total: 0, page: 1, page_size: 50 }),
      ),
    ]);
    renderWithApp(<VideosPage />, client, '/videos?q=없는말');
    expect(await screen.findByText('조건에 맞는 영상이 없습니다')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '필터 초기화' }).length).toBeGreaterThan(0);
  });

  it('TC-WF-032 영상이 하나도 없으면 다음 행동(데모 영상 불러오기)을 안내한다', async () => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/videos', () =>
        json(200, { items: [], total: 0, page: 1, page_size: 50 }),
      ),
    ]);
    renderWithApp(<VideosPage />, client, '/videos');
    expect(await screen.findByText('아직 영상이 없습니다')).toBeInTheDocument();
    expect(screen.getByText(/데모 영상 불러오기/)).toBeInTheDocument();
  });

  it('TC-WF-033 목록 오류는 조치 안내와 오류 코드, 다시 시도 버튼과 함께 보여 준다', async () => {
    const user = userEvent.setup();
    let fail = true;
    const { client } = await connectedClient([
      route('GET', '/api/v1/videos', () =>
        fail
          ? problem(
              500,
              'internal_error',
              '서버 안에서 오류가 났습니다',
              '',
              '서버 로그를 확인해 주세요.',
            )
          : json(200, pageOf([video(1)], 1, 1)),
      ),
    ]);
    renderWithApp(<VideosPage />, client, '/videos');
    const alert = (await screen.findByText('internal_error')).closest(
      '[role=alert]',
    ) as HTMLElement;
    expect(alert).toHaveTextContent('서버 안에서 오류가 났습니다');
    expect(alert).toHaveTextContent('서버 로그를 확인해 주세요.');
    expect(alert).toHaveTextContent('internal_error');
    fail = false;
    await user.click(within(alert).getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByText('테스트 영상 1')).toBeInTheDocument();
  });
});
