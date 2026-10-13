import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { draftBatch } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { BatchDetailPage } from './BatchDetailPage';

const open = async (confirmText: string) => {
  const b = draftBatch();
  b.precheck = { ...b.precheck!, confirm_text: confirmText };
  const { client } = await connectedClient([route('GET', '/api/v1/batches/7', () => json(200, b))]);
  renderWithApp(
    <Routes>
      <Route path="batches/:batchId" element={<BatchDetailPage />} />
    </Routes>,
    client,
    '/batches/7',
  );
  await screen.findByText('실행 확인');
  return screen.getByRole('button', { name: '실행' });
};
const gate = () => document.getElementById('exec-gate')!;

describe('실행 버튼이 꺼진 이유 안내(execGate)', () => {
  it("데모: 둘 다 부족하면 ① A/B 확인 ② 확인 문구 '실행 2건' 을 버튼 아래에 보이고 버튼과 연결한다", async () => {
    const exec = await open('실행 2건');
    expect(exec).toBeDisabled();
    expect(exec).toHaveAccessibleDescription(/아직 필요한 것/);
    expect(gate().textContent).toContain('A/B 테스트 확인');
    expect(gate().textContent).toContain("'실행 2건'");
    expect(gate().getAttribute('aria-live')).toBe('polite');
    expect(exec.parentElement!.nextElementSibling).toBe(gate());
  });

  it('충족한 항목은 사라지고 모두 충족하면 부족 목록이 없어진다', async () => {
    const user = userEvent.setup();
    const exec = await open('실행 2건');
    await user.click(screen.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ }));
    expect(gate().textContent).not.toContain('A/B 테스트 확인');
    expect(gate().textContent).toContain("'실행 2건'");
    await user.type(screen.getByRole('textbox'), '실행 2건');
    expect(exec).toBeEnabled();
    expect(gate().textContent).not.toContain('아직 필요한 것');
    expect(gate().textContent).toContain('누를 수 있습니다');
  });

  it("실제 모드: 확인 문구 '실제 실행 2건' 을 정확히 안내한다", async () => {
    const exec = await open('실제 실행 2건');
    expect(exec).toBeDisabled();
    expect(gate().textContent).toContain("'실제 실행 2건'");
  });

  it('문구만 맞고 A/B 체크가 없으면 A/B 항목만 남는다', async () => {
    const user = userEvent.setup();
    const exec = await open('실행 2건');
    await user.type(screen.getByRole('textbox'), '실행 2건');
    expect(exec).toBeDisabled();
    expect(gate().textContent).toContain('A/B 테스트 확인');
    expect(gate().textContent).not.toContain("'실행 2건'");
  });
});
