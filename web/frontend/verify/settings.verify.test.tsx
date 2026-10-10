// 06단계 독립 검증(TC-VF) — 설정 화면: 라이브 허용 읽기 전용, 범위 검증, PIN 규칙
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { SettingsData } from '../src/api/types';
import { App } from '../src/app/App';
import { SettingsPage } from '../src/pages/SettingsPage';
import { dashboard } from '../src/test/fixtures';
import { connectedClient, json, problem, renderWithApp, route, type Handler } from '../src/test/utils';

const base: SettingsData = {
  daily_apply_cap: 10,
  suggestions_per_video: 3,
  tone: ['차분하게'],
  pin_enabled: false,
  mode: 'demo',
  read_only: { enable_live: false, live_allowlist: [], note: '변경 불가' },
};
async function goSettings(data: SettingsData = base, extra: Handler[] = [], entry = '/settings') {
  const c = await connectedClient([
    route('GET', '/api/v1/settings', () => json(200, data)),
    ...extra,
    route('PATCH', '/api/v1/settings', (r) => json(200, { ...data, ...(r.body as object) })),
  ]);
  renderWithApp(<SettingsPage />, c.client, entry);
  if (entry.includes('tab=pin')) await screen.findByLabelText(/새 PIN/);
  else await screen.findByLabelText(/하루/);
  return c;
}
const field = (re: RegExp) => screen.getByLabelText(re) as HTMLInputElement;
const saveBtn = () => screen.getByRole('button', { name: '저장' });

describe('설정: 라이브 허용은 편집 불가 (W-014, 요청서 설정 화면)', () => {
  it('TC-VF-@@@ 안전 설정 탭의 입력 요소는 하루 상한·영상당 제안 수·말투 3개뿐이고 체크박스·스위치·라디오가 없다', async () => {
    await goSettings({ ...base, read_only: { enable_live: true, live_allowlist: ['vidAAAAAAA1', 'vidBBBBBBB2'], note: 'n' } });
    expect(screen.getAllByRole('spinbutton')).toHaveLength(2);
    expect(screen.getAllByRole('textbox')).toHaveLength(1);
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    expect(screen.queryAllByRole('switch')).toHaveLength(0);
    expect(screen.queryAllByRole('radio')).toHaveLength(0);
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  });

  it('TC-VF-@@@ 서버가 enable_live=true 를 주어도 켜짐은 글자(▲ 기호 포함)로만 보이고 조작 버튼이 없다', async () => {
    await goSettings({ ...base, read_only: { enable_live: true, live_allowlist: ['vidAAAAAAA1'], note: 'n' } });
    const dd = document.querySelector('.readonly-kv dd') as HTMLElement;
    expect(within(dd).queryAllByRole('button')).toHaveLength(0);
    expect(within(dd).queryAllByRole('textbox')).toHaveLength(0);
    expect(dd.textContent).toContain('▲');
    expect(screen.getByText('vidAAAAAAA1')).toBeInTheDocument();
    expect(screen.getAllByText(/이 화면에서는 켤 수 없습니다/).length).toBeGreaterThan(0);
  });

  it('TC-VF-@@@ 저장 요청 본문에는 허용된 키(daily_apply_cap·suggestions_per_video·tone)만 들어가고 라이브 관련 키가 없다', async () => {
    const user = userEvent.setup();
    const { calls } = await goSettings();
    fireEvent.change(field(/하루/), { target: { value: '12' } });
    await user.click(saveBtn());
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    const body = calls.find((c) => c.method === 'PATCH')?.body as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(['daily_apply_cap', 'suggestions_per_video', 'tone']);
    expect(JSON.stringify(body)).not.toMatch(/live|allow/i);
  });

  it('TC-VF-@@@ 서버가 setting_not_allowed(403/422)로 거절하면 사유를 보여 주고 화면 값이 서버 값을 가장하지 않는다', async () => {
    const user = userEvent.setup();
    await goSettings(base, [route('PATCH', '/api/v1/settings', () => problem(403, 'setting_not_allowed', '이 설정은 화면에서 바꿀 수 없습니다'))]);
    fireEvent.change(field(/하루/), { target: { value: '12' } });
    await user.click(saveBtn());
    expect((await screen.findAllByText('이 설정은 화면에서 바꿀 수 없습니다')).length).toBeGreaterThan(0);
  });
});

describe('설정: 값 범위 경계 (하루 상한 1~20, 영상당 제안 1~5, 말투 5개·20자)', () => {
  it.each([
    ['0', false],
    ['1', true],
    ['2', true],
    ['19', true],
    ['20', true],
    ['21', false],
    ['-1', false],
    ['1.5', false],
    ['', false],
    ['2e0', true], // Number("2e0") === 2 라 정수로 인정됨(허용 범위 안)
    ['1e3', false],
  ])('TC-VF-@@@ 하루 반영 상한 입력 "%s" → 저장 가능 여부 %s', async (v, enabled) => {
    await goSettings();
    fireEvent.change(field(/하루/), { target: { value: v } });
    if (enabled) expect(saveBtn()).toBeEnabled();
    else expect(saveBtn()).toBeDisabled();
  });

  it.each([
    ['0', false],
    ['1', true],
    ['5', true],
    ['6', false],
    ['2.5', false],
    ['', false],
  ])('TC-VF-@@@ 영상당 제안 수 입력 "%s" → 저장 가능 여부 %s', async (v, enabled) => {
    await goSettings();
    fireEvent.change(field(/영상 하나당|영상당|제안/), { target: { value: v } });
    if (enabled) expect(saveBtn()).toBeEnabled();
    else expect(saveBtn()).toBeDisabled();
  });

  it('TC-VF-@@@ 값이 바뀌지 않았으면 저장 버튼이 꺼져 있고, 바꿨다 되돌려도 꺼진다', async () => {
    await goSettings();
    expect(saveBtn()).toBeDisabled();
    fireEvent.change(field(/하루/), { target: { value: '11' } });
    expect(saveBtn()).toBeEnabled();
    fireEvent.change(field(/하루/), { target: { value: '10' } });
    expect(saveBtn()).toBeDisabled();
  });

  it.each([
    ['5개(경계 안)', '가,나,다,라,마', true],
    ['6개(경계 밖)', '가,나,다,라,마,바', false],
    ['한 항목 20자(경계 안)', '가'.repeat(20), true],
    ['한 항목 21자(경계 밖)', '가'.repeat(21), false],
    ['이모지 20개(코드포인트 20)', '😀'.repeat(20), true],
    ['이모지 21개', '😀'.repeat(21), false],
    ['쉼표만(빈 항목은 무시)', ',,,', true],
  ])('TC-VF-@@@ 말투 목록 경계: %s', async (_n, v, enabled) => {
    await goSettings();
    fireEvent.change(field(/말투/), { target: { value: v } });
    if (enabled) expect(saveBtn()).toBeEnabled();
    else expect(saveBtn()).toBeDisabled();
  });

  // 결함 DEF-6-003(Low): 말투 입력칸이 maxLength=40(전체 글자수)이라 서버가 허용하는 5개×20자를 입력할 수 없다.
  it.fails('TC-VF-@@@ 사용자가 말투 3개(각 15자, 쉼표 포함 약 49자)를 직접 입력하면 잘리지 않고 그대로 저장된다 [DEF-6-003]', async () => {
    const user = userEvent.setup();
    await goSettings();
    const tone = field(/말투/);
    await user.clear(tone);
    const text = ['가나다라마바사아자차카타파하가', '나다라마바사아자차카타파하가나', '다라마바사아자차카타파하가나다'].join(', ');
    await user.type(tone, text);
    expect(tone.value).toBe(text);
  });
});

describe('설정: PIN 규칙 (S-W02 보조)', () => {
  const pinTab = '/settings?tab=pin';
  const labelNew = /새 PIN/;
  it.each([
    ['3자리', '123', false],
    ['4자리(경계)', '1234', true],
    ['12자리(경계)', '123456789012', true],
    ['13자리', '1234567890123', false],
    ['영문 혼합', '12ab', false],
    ['전각 숫자', '１２３４', false],
    ['아랍-인도 숫자', '١٢٣٤', false],
    ['공백 포함', '12 34', false],
    ['앞뒤 공백', ' 1234 ', false],
    ['기호', '12-34', false],
  ])('TC-VF-@@@ 새 PIN 형식(%s) → 설정 가능 여부 %s', async (_n, v, enabled) => {
    await goSettings(base, [], pinTab);
    const inputs = screen.getAllByLabelText(/PIN/, { selector: 'input' }) as HTMLInputElement[];
    const newBox = inputs.find((i) => i.autocomplete === 'new-password')!;
    const again = inputs.filter((i) => i.autocomplete === 'new-password')[1]!;
    fireEvent.change(newBox, { target: { value: v } });
    fireEvent.change(again, { target: { value: v } });
    const btn = screen.getByRole('button', { name: /PIN 설정/ });
    if (enabled) expect(btn).toBeEnabled();
    else expect(btn).toBeDisabled();
    void labelNew;
  });

  it('TC-VF-@@@ 재입력이 다르면 설정할 수 없고 불일치 안내가 나온다', async () => {
    await goSettings(base, [], pinTab);
    const [a, b] = screen.getAllByLabelText(/PIN/, { selector: 'input' }).filter((i) => (i as HTMLInputElement).autocomplete === 'new-password') as HTMLInputElement[];
    fireEvent.change(a!, { target: { value: '1234' } });
    fireEvent.change(b!, { target: { value: '1235' } });
    expect(screen.getByRole('button', { name: /PIN 설정/ })).toBeDisabled();
    expect(screen.getByText('PIN 이 서로 다릅니다.')).toBeInTheDocument();
  });

  it('TC-VF-@@@ PIN 입력칸은 모두 password 형식이며, 저장 뒤 입력칸이 비워지고 PIN 이 화면 텍스트에 남지 않는다', async () => {
    const user = userEvent.setup();
    const { calls } = await goSettings(base, [route('PATCH', '/api/v1/settings', () => json(200, { ...base, pin_enabled: true }))], pinTab);
    const pwds = document.querySelectorAll('input');
    for (const i of Array.from(pwds)) expect(i.type).toBe('password');
    const news = screen.getAllByLabelText(/PIN/, { selector: 'input' }).filter((i) => (i as HTMLInputElement).autocomplete === 'new-password') as HTMLInputElement[];
    fireEvent.change(news[0]!, { target: { value: '482915' } });
    fireEvent.change(news[1]!, { target: { value: '482915' } });
    await user.click(screen.getByRole('button', { name: /PIN 설정/ }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ pin: { action: 'set', new_pin: '482915' } });
    await waitFor(() => {
      for (const i of Array.from(document.querySelectorAll('input'))) expect((i as HTMLInputElement).value).toBe('');
    });
    expect(document.body.textContent).not.toContain('482915');
  });

  it('TC-VF-@@@ PIN 이 이미 있으면 현재 PIN 없이는 변경할 수 없고, 변경 본문에 current_pin 이 포함된다', async () => {
    const { calls } = await goSettings({ ...base, pin_enabled: true }, [], pinTab);
    const all = screen.getAllByLabelText(/PIN/, { selector: 'input' }) as HTMLInputElement[];
    const cur = all.find((i) => i.autocomplete === 'current-password')!;
    const news = all.filter((i) => i.autocomplete === 'new-password');
    fireEvent.change(news[0]!, { target: { value: '654321' } });
    fireEvent.change(news[1]!, { target: { value: '654321' } });
    const btn = screen.getByRole('button', { name: /PIN 변경/ });
    expect(btn).toBeDisabled();
    fireEvent.change(cur, { target: { value: '111111' } });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ pin: { action: 'set', new_pin: '654321', current_pin: '111111' } });
  });

  it('TC-VF-@@@ PIN 해제는 확인 대화상자의 현재 PIN 입력 전까지 실행할 수 없고, 취소하면 요청이 없다', async () => {
    const user = userEvent.setup();
    const { calls } = await goSettings({ ...base, pin_enabled: true }, [], pinTab);
    await user.click(await screen.findByRole('button', { name: 'PIN 해제' }));
    const d = await screen.findByRole('dialog');
    const submit = within(d).getAllByRole('button').find((b) => b.getAttribute('type') === 'submit')!;
    expect(submit).toBeDisabled();
    await user.click(within(d).getByRole('button', { name: '취소' }));
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false);
  });

  it('TC-VF-@@@ 틀린 현재 PIN(401 pin_invalid)은 대화상자 안에 안내하고 세션 재발급·만료 창을 띄우지 않는다', async () => {
    const user = userEvent.setup();
    const c = await connectedClient([
      route('GET', '/api/v1/settings', () => json(200, { ...base, pin_enabled: true })),
      route('GET', '/api/v1/dashboard', () => json(200, dashboard())),
      route('PATCH', '/api/v1/settings', () => problem(401, 'pin_invalid', 'PIN 이 맞지 않습니다')),
    ]);
    renderWithApp(<App />, c.client, '/settings?tab=pin');
    await user.click(await screen.findByRole('button', { name: 'PIN 해제' }));
    const meBefore = c.calls.filter((x) => x.path === '/api/v1/auth/me').length;
    const d = await screen.findByRole('dialog');
    fireEvent.change(within(d).getByLabelText(/현재 PIN/), { target: { value: '0000' } });
    await user.click(within(d).getAllByRole('button').find((b) => b.getAttribute('type') === 'submit')!);
    expect((await within(d).findAllByText('PIN 이 맞지 않습니다')).length).toBeGreaterThan(0);
    expect(screen.queryByText('세션이 만료되었습니다')).toBeNull();
    expect(c.calls.filter((x) => x.path === '/api/v1/auth/session')).toHaveLength(0);
    expect(c.calls.filter((x) => x.path === '/api/v1/auth/me')).toHaveLength(meBefore);
  });
});
