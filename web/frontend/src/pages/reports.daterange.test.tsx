import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { kstDateOffset } from '../lib/format';
import { connectedClient, json, renderWithApp, route, type Req } from '../test/utils';
import { ReportsPage } from './ReportsPage';

const empty = () => json(200, { items: [], notes: [] });

describe('성과 리포트 조회 기간', () => {
  it('기본값은 오늘(한국시간)이고 조회 요청에 date_from/date_to 로 전달한다', async () => {
    const seen: Req[] = [];
    const { client } = await connectedClient([
      route('GET', '/api/v1/reports/changes', (r) => {
        seen.push(r);
        return empty();
      }),
    ]);
    renderWithApp(<ReportsPage />, client);
    const today = kstDateOffset(0);
    expect(await screen.findByLabelText('조회 시작일')).toHaveValue(today);
    expect(screen.getByLabelText('조회 종료일')).toHaveValue(today);
    await waitFor(() => expect(seen.length).toBeGreaterThan(0));
    expect(seen[0]!.query.get('date_from')).toBe(today);
    expect(seen[0]!.query.get('date_to')).toBe(today);
  });

  it('0건이면 기간 안내 문구를 보이고 [전체 기간]을 누르면 기간 없이 다시 조회한다', async () => {
    const user = userEvent.setup();
    const seen: Req[] = [];
    const { client } = await connectedClient([
      route('GET', '/api/v1/reports/changes', (r) => {
        seen.push(r);
        return empty();
      }),
    ]);
    renderWithApp(<ReportsPage />, client);
    expect(
      await screen.findByText('선택한 기간에 해당하는 항목이 없습니다. [전체 기간]을 눌러 보세요.'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '전체 기간' }));
    await waitFor(() => expect(seen.some((r) => !r.query.has('date_from') && !r.query.has('date_to'))).toBe(true));
    expect(await screen.findByText('비교할 리포트가 없습니다')).toBeInTheDocument();
  });

  it('시작일이 종료일보다 뒤이면 조회하지 않고 오류를 보인다', async () => {
    const seen: Req[] = [];
    const { client } = await connectedClient([
      route('GET', '/api/v1/reports/changes', (r) => {
        seen.push(r);
        return empty();
      }),
    ]);
    renderWithApp(<ReportsPage />, client);
    await screen.findByLabelText('조회 시작일');
    await waitFor(() => expect(seen.length).toBe(1));
    fireEvent.change(screen.getByLabelText('조회 시작일'), { target: { value: '2999-01-02' } });
    expect((await screen.findAllByText('시작일이 종료일보다 뒤입니다. 날짜를 바꿔 주세요.')).length).toBeGreaterThan(0);
    expect(seen.length).toBe(1);
    expect(screen.getByRole('button', { name: 'CSV 내보내기' })).toBeDisabled();
  });

  it('CSV 내보내기도 같은 기간을 전달한다', async () => {
    const user = userEvent.setup();
    const csv: Req[] = [];
    const { client } = await connectedClient([
      route('GET', '/api/v1/reports/changes', empty),
      route('GET', '/api/v1/reports/export.csv', (r) => {
        csv.push(r);
        return new Response('a', { status: 200, headers: { 'Content-Type': 'text/csv' } });
      }),
    ]);
    URL.createObjectURL = () => 'blob:x';
    URL.revokeObjectURL = () => undefined;
    renderWithApp(<ReportsPage />, client);
    fireEvent.change(await screen.findByLabelText('조회 시작일'), { target: { value: '2026-03-01' } });
    fireEvent.change(screen.getByLabelText('조회 종료일'), { target: { value: '2026-03-31' } });
    await user.click(screen.getByRole('button', { name: 'CSV 내보내기' }));
    await waitFor(() => expect(csv.length).toBe(1));
    expect(csv[0]!.query.get('date_from')).toBe('2026-03-01');
    expect(csv[0]!.query.get('date_to')).toBe('2026-03-31');
  });
});
