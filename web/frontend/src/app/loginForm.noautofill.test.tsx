import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeClient, renderWithApp } from '../test/utils';
import { LoginForm } from './LoginForm';

/** 브라우저 자동 채움(저장된 아이디·비밀번호) 차단 — 선생님 지시 2026-10-15. 실제 비밀번호 관리자는 jsdom 에 없어 "브라우저가 값을 몰래 넣는 상황"을 직접 흉내 낸다. */
const setNative = (el: HTMLInputElement, v: string) => {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
  setter.call(el, v); // React 의 onChange 를 거치지 않고 화면 값만 바꾼다(브라우저 자동 채움과 같은 방식)
};

describe('로그인 화면: 저장된 아이디·비밀번호 자동 채움 차단', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it('자동 채움을 끄는 속성이 붙어 있다(form·아이디 off, 비밀번호 new-password, 흔한 이름 username/password 아님)', () => {
    const { client } = makeClient([]);
    const { container } = renderWithApp(<LoginForm />, client);
    const form = container.querySelector('form')!;
    const id = screen.getByLabelText('아이디');
    const pw = screen.getByLabelText('비밀번호');
    expect(form).toHaveAttribute('autocomplete', 'off');
    expect(id).toHaveAttribute('autocomplete', 'off');
    expect(pw).toHaveAttribute('autocomplete', 'new-password');
    expect(id.getAttribute('name')).not.toMatch(/^(user(name)?|email|login|id)$/i);
    expect(pw.getAttribute('name')).not.toMatch(/^(pass(word)?|pwd)$/i);
    expect(pw).toHaveAttribute('type', 'password');
  });

  it('사용자가 누르기 전에는 읽기 전용이고, 누르면 입력할 수 있다', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { client } = makeClient([]);
    renderWithApp(<LoginForm />, client);
    const pw = screen.getByLabelText('비밀번호') as HTMLInputElement;
    expect(pw.readOnly).toBe(true);
    await user.click(pw);
    expect(pw.readOnly).toBe(false);
    await user.type(pw, 'abc');
    expect(pw.value).toBe('abc');
  });

  it('브라우저가 화면 값을 몰래 채워도(화면 열린 직후·조금 뒤) 사람이 입력하기 전이면 다시 비운다', () => {
    const { client } = makeClient([]);
    renderWithApp(<LoginForm />, client);
    const id = screen.getByLabelText('아이디') as HTMLInputElement;
    const pw = screen.getByLabelText('비밀번호') as HTMLInputElement;
    for (const wait of [40, 300, 600, 900]) {
      act(() => {
        setNative(id, 'saved-id');
        setNative(pw, 'saved-password');
        vi.advanceTimersByTime(wait);
      });
    }
    act(() => vi.advanceTimersByTime(2000));
    expect(id.value).toBe('');
    expect(pw.value).toBe('');
    expect(screen.getByText('아이디를 입력해 주세요.')).toBeInTheDocument();
  });

  it('사람이 키보드로 입력하기 시작하면 입력한 값을 지우지 않는다', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { client } = makeClient([]);
    renderWithApp(<LoginForm />, client);
    const id = screen.getByLabelText('아이디') as HTMLInputElement;
    await user.click(id);
    await user.type(id, 'typed-by-person');
    act(() => vi.advanceTimersByTime(3000));
    expect(id.value).toBe('typed-by-person');
  });

  it('뒤로 가기로 이전 화면이 복원되면(pageshow persisted) 입력값과 읽기 전용 상태를 되돌린다', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { client } = makeClient([]);
    renderWithApp(<LoginForm />, client);
    const id = screen.getByLabelText('아이디') as HTMLInputElement;
    await user.click(id);
    await user.type(id, 'abc');
    const ev = new Event('pageshow') as Event & { persisted: boolean };
    Object.defineProperty(ev, 'persisted', { value: true });
    act(() => {
      window.dispatchEvent(ev);
    });
    expect(id.value).toBe('');
    expect(id.readOnly).toBe(true);
  });

  it('로그아웃 뒤 로그인 화면을 다시 열면(새로 그려짐) 이전 입력이 남아 있지 않다', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { client } = makeClient([]);
    const first = renderWithApp(<LoginForm />, client);
    await user.click(screen.getByLabelText('아이디'));
    await user.type(screen.getByLabelText('아이디'), 'someone');
    first.unmount();
    renderWithApp(<LoginForm />, client);
    expect((screen.getByLabelText('아이디') as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('비밀번호') as HTMLInputElement).value).toBe('');
  });

  it('값이 쿠키·localStorage·sessionStorage·URL 에 남지 않는다', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { client } = makeClient([]);
    renderWithApp(<LoginForm />, client);
    await user.click(screen.getByLabelText('아이디'));
    await user.type(screen.getByLabelText('아이디'), 'person-id');
    await user.click(screen.getByLabelText('비밀번호'));
    await user.type(screen.getByLabelText('비밀번호'), 'person-secret');
    const all = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }) + document.cookie + window.location.href;
    expect(all).not.toContain('person-id');
    expect(all).not.toContain('person-secret');
  });
});
