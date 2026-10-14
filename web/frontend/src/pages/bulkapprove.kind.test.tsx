import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { Suggestion } from '../api/types';
import { suggestion } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { BulkApprovePage } from './BulkApprovePage';

const sg = (id: number, vid: string, title: string, kind: 'long' | 'short' | null): Suggestion =>
  suggestion(id, {
    video_id: vid,
    title,
    video_kind: kind,
    created_at: new Date().toISOString(),
  });
const items = [
  sg(1, 'AAAAAAAAAA1', '긴영상 제목안', 'long'),
  sg(2, 'BBBBBBBBBB2', '짧은영상 제목안', 'short'),
  sg(3, 'CCCCCCCCCC3', '길이모름 제목안', null),
];

async function setup() {
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
}
const rowsText = () =>
  Array.from(document.querySelectorAll('tbody tr')).map((r) => r.textContent ?? '');

describe('일괄 승인 영상 구분(롱폼/쇼츠)', () => {
  it('TC-KF-BA-01 "구분" 열에 롱폼/쇼츠 배지가 나오고 길이 불명은 "-" 이다', async () => {
    await setup();
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent);
    expect(heads).toContain('구분');
    const idx = heads.indexOf('구분');
    const trs = Array.from(document.querySelectorAll('tbody tr'));
    const cell = (t: string) =>
      (trs.find((r) => r.textContent?.includes(t))!.querySelectorAll('td')[idx]).textContent;
    expect(cell('긴영상')).toBe('롱폼');
    expect(cell('짧은영상')).toBe('쇼츠');
    expect(cell('길이모름')).toBe('-');
  });

  it('TC-KF-BA-02 선택 상자로 롱폼/쇼츠만 거르고 길이 불명은 어느 쪽에도 안 나온다', async () => {
    const user = userEvent.setup();
    await setup();
    const sel = screen.getByRole('combobox', { name: /영상 구분/ });
    await user.selectOptions(sel, 'long');
    expect(screen.getByText('승인 가능한 제안 1건')).toBeInTheDocument();
    expect(rowsText().join()).toContain('긴영상');
    expect(rowsText().join()).not.toContain('길이모름');
    await user.selectOptions(sel, 'short');
    expect(screen.getByText('승인 가능한 제안 1건')).toBeInTheDocument();
    expect(rowsText().join()).toContain('짧은영상');
    expect(rowsText().join()).not.toContain('길이모름');
    await user.selectOptions(sel, '');
    expect(screen.getByText('승인 가능한 제안 3건')).toBeInTheDocument();
  });

  it('TC-KF-BA-03 다른 조건(검색)과 AND 이고, 맞는 것이 없으면 안내가 나온다', async () => {
    const user = userEvent.setup();
    await setup();
    await user.selectOptions(screen.getByRole('combobox', { name: /영상 구분/ }), 'short');
    await user.type(screen.getByRole('searchbox', { name: /제목 또는 영상 ID 검색/ }), '긴영상');
    expect(screen.getByText(/조건에 맞는 제안이 없습니다/)).toBeInTheDocument();
  });

  it('TC-KF-BA-04 [필터 초기화] 가 구분 조건도 비운다', async () => {
    const user = userEvent.setup();
    await setup();
    const sel = screen.getByRole('combobox', { name: /영상 구분/ }) as HTMLSelectElement;
    await user.selectOptions(sel, 'short');
    expect(screen.getByText('승인 가능한 제안 1건')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '필터 초기화' }));
    expect(sel.value).toBe('');
    expect(screen.getByText('승인 가능한 제안 3건')).toBeInTheDocument();
    expect(within(document.body).queryByRole('button', { name: '필터 초기화' })).toBeNull();
  });
});
