import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { Suggestion } from '../api/types';
import { suggestion } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { BulkApprovePage } from './BulkApprovePage';

const sg = (id: number, vid: string, title: string, v: 'pass' | 'warn' = 'pass'): Suggestion =>
  suggestion(id, { video_id: vid, title, validation_result: v });
const items = [
  sg(1, 'AAAAAAAAAA1', '청소 설정 제목'),
  sg(2, 'BBBBBBBBBB2', '지원금 조회 제목'),
  sg(3, 'BBBBBBBBBB2', '지원금 다른 제목', 'warn'),
];

describe('일괄 승인 제목 또는 영상 ID 검색', () => {
  it('TC-WF-300 영상 ID 일부나 제목 일부를 입력하면 그 제안만 남고, 비우면 전체가 돌아온다', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', (r) =>
        json(200, {
          items: r.query.get('status') === 'candidate' ? items : [],
          total: 3,
          page: 1,
          page_size: 50,
        }),
      ),
      route('POST', '/api/v1/suggestions/resolve-videos', () => json(200, { items: [] })),
    ]);
    renderWithApp(
      <Routes>
        <Route path="bulk-approve" element={<BulkApprovePage />} />
      </Routes>,
      c.client,
      '/bulk-approve',
    );
    expect(await screen.findByText('승인 가능한 제안 3건')).toBeInTheDocument();
    const box = screen.getByRole('searchbox', { name: /제목 또는 영상 ID 검색/ });
    await user.type(box, 'BBBBBB');
    expect(screen.getByText('승인 가능한 제안 2건')).toBeInTheDocument();
    await user.clear(box);
    await user.type(box, '청소');
    expect(screen.getByText('승인 가능한 제안 1건')).toBeInTheDocument();
    await user.clear(box);
    await user.type(box, '없는글자zzz');
    expect(screen.getByText(/맞는 제안이 없습니다/)).toBeInTheDocument();
    await user.clear(box);
    expect(screen.getByText('승인 가능한 제안 3건')).toBeInTheDocument();
  });

  it('TC-WF-301 최근 제안(번호가 큰 것)이 위에 나오고, 판정으로 줄일 수 있다', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/suggestions', (r) =>
        json(200, {
          items: r.query.get('status') === 'candidate' ? items : [],
          total: 3,
          page: 1,
          page_size: 50,
        }),
      ),
      route('POST', '/api/v1/suggestions/resolve-videos', () => json(200, { items: [] })),
    ]);
    renderWithApp(
      <Routes>
        <Route path="bulk-approve" element={<BulkApprovePage />} />
      </Routes>,
      c.client,
      '/bulk-approve',
    );
    await screen.findByText('승인 가능한 제안 3건');
    const firstNew = () =>
      Array.from(document.querySelectorAll('tbody tr')).map((r) => r.textContent ?? '');
    expect(firstNew()[0]).toContain('지원금 다른 제목'); // 번호 3 이 맨 위
    expect(firstNew()[2]).toContain('청소 설정 제목'); // 번호 1 이 맨 아래
    await user.selectOptions(screen.getByRole('combobox', { name: /판정으로 줄여 보기/ }), 'warn');
    expect(screen.getByText('승인 가능한 제안 1건')).toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', { name: /판정으로 줄여 보기/ }), 'block');
    expect(screen.getByText(/맞는 제안이 없습니다/)).toBeInTheDocument();
  });
});
