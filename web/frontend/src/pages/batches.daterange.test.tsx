import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { kstDateOffset } from '../lib/format';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { BatchesPage } from './BatchesPage';

const today = kstDateOffset(0);
const empty = route('GET', '/api/v1/batches', () => json(200, { items: [], total: 0, page: 1, page_size: 50 }));
const suggestionsEmpty = route('GET', '/api/v1/suggestions', () => json(200, { items: [], total: 0, page: 1, page_size: 200 }));

const listCalls = (calls: { method: string; path: string; query: URLSearchParams }[]) =>
  calls.filter((c) => c.method === 'GET' && c.path === '/api/v1/batches');
const from = () => screen.getByLabelText('조회 시작일') as HTMLInputElement;
const to = () => screen.getByLabelText('조회 종료일') as HTMLInputElement;

describe('배치 목록 조회 기간', () => {
  it('기본값은 오늘(한국 시간)이고 첫 요청에 date_from/date_to 가 같이 간다. 기준 안내가 보인다', async () => {
    const { client, calls } = await connectedClient([suggestionsEmpty, empty]);
    renderWithApp(<BatchesPage />, client, '/batches');
    await waitFor(() => expect(listCalls(calls).length).toBeGreaterThan(0));
    expect(from().value).toBe(today);
    expect(to().value).toBe(today);
    expect(screen.getByText(/만든 시각 기준/)).toBeInTheDocument();
    const q = listCalls(calls).filter((c) => c.query.has('date_from')).at(-1)!.query;
    expect(q.get('date_from')).toBe(today);
    expect(q.get('date_to')).toBe(today);
  });

  it('날짜를 바꾸면 바뀐 값으로 다시 요청하고 1쪽부터 본다', async () => {
    const { client, calls } = await connectedClient([suggestionsEmpty, empty]);
    renderWithApp(<BatchesPage />, client, '/batches');
    await waitFor(() => expect(listCalls(calls).length).toBeGreaterThan(0));
    fireEvent.change(from(), { target: { value: '2026-09-01' } });
    await waitFor(() =>
      expect(listCalls(calls).some((c) => c.query.get('date_from') === '2026-09-01' && c.query.get('date_to') === today && (c.query.get('page') ?? '1') === '1')).toBe(true),
    );
  });

  it('[전체 기간]을 누르면 날짜 조건 없이 요청한다', async () => {
    const user = userEvent.setup();
    const { client, calls } = await connectedClient([suggestionsEmpty, empty]);
    renderWithApp(<BatchesPage />, client, '/batches');
    await waitFor(() => expect(listCalls(calls).length).toBeGreaterThan(0));
    await user.click(screen.getByRole('button', { name: '전체 기간' }));
    await waitFor(() => expect(listCalls(calls).some((c) => !c.query.has('date_from') && !c.query.has('date_to'))).toBe(true));
    expect(from().value).toBe('');
    expect(to().value).toBe('');
  });

  it('시작일이 종료일보다 뒤이면 오류를 보이고 조회하지 않는다', async () => {
    const { client, calls } = await connectedClient([suggestionsEmpty, empty]);
    renderWithApp(<BatchesPage />, client, '/batches');
    await waitFor(() => expect(listCalls(calls).length).toBeGreaterThan(0));
    const before = listCalls(calls).length;
    fireEvent.change(from(), { target: { value: kstDateOffset(-3) } }); // 오늘보다 3일 뒤
    expect((await screen.findAllByText('시작일이 종료일보다 뒤입니다. 날짜를 바꿔 주세요.')).length).toBeGreaterThan(0);
    await new Promise((r) => setTimeout(r, 100));
    expect(listCalls(calls).length).toBe(before);
  });

  it('기간 안에 0건이면 [전체 기간] 안내를 보여 주고, 전체 기간에서도 0건이면 원래 빈 화면 문구를 쓴다', async () => {
    const user = userEvent.setup();
    const { client } = await connectedClient([suggestionsEmpty, empty]);
    renderWithApp(<BatchesPage />, client, '/batches');
    expect(await screen.findByText(/선택한 기간에 해당하는 항목이 없습니다/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '전체 기간' }));
    await waitFor(() => expect(screen.queryByText(/선택한 기간에 해당하는 항목이 없습니다/)).not.toBeInTheDocument());
  });
});
