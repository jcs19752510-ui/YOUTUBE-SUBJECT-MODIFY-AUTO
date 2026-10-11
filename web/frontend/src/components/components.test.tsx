import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/client';
import {
  ConfirmPhrase,
  Modal,
  Pagination,
  Tabs,
  TitleDiff,
  ValidationBadge,
  describeError,
} from '.';
import { axeViolations } from '../test/utils';

describe('TitleDiff', () => {
  it('TC-WF-016 변경 전/후 제목, 추가·삭제 부분, 글자 수를 보여 준다', () => {
    const { container } = render(<TitleDiff before="냉장고 정리" after="냉장고 정리 5가지" />);
    expect(screen.getByText('변경 전')).toBeInTheDocument();
    expect(container.querySelector('ins')?.textContent).toContain('5가지');
    expect(screen.getByText('글자 수 6자 → 10자 (+4)')).toBeInTheDocument();
    expect(screen.getAllByText('추가됨:').length).toBeGreaterThan(0);
  });

  it('TC-WF-017 삭제 부분은 취소선 요소와 스크린리더용 문구로 표시한다', () => {
    const { container } = render(<TitleDiff before="충격 냉장고 정리" after="냉장고 정리" />);
    expect(container.querySelector('del')?.textContent).toContain('충격');
    expect(screen.getAllByText('삭제됨:').length).toBeGreaterThan(0);
  });

  it('TC-WF-018 외부 문자열의 HTML 은 요소로 해석하지 않고 글자 그대로 보여 준다', () => {
    const evil = '<img src=x onerror=alert(1)><script>alert(1)</script>';
    const { container } = render(<TitleDiff before="가나다" after={evil} />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).toContain('<img src=x');
  });
});

describe('Modal', () => {
  function Demo({ onClose }: { onClose: () => void }) {
    const [open, setOpen] = useState(false);
    return (
      <div id="root">
        <button onClick={() => setOpen(true)}>열기</button>
        {open && (
          <Modal
            title="제목"
            onClose={() => {
              setOpen(false);
              onClose();
            }}
            footer={<button>확인</button>}
          >
            <input aria-label="이름" />
          </Modal>
        )}
      </div>
    );
  }
  it('TC-WF-019 Esc 로 닫히고 포커스가 열었던 버튼으로 돌아간다', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Demo onClose={onClose} />);
    await user.click(screen.getByRole('button', { name: '열기' }));
    const dlg = screen.getByRole('dialog', { name: '제목' });
    expect(dlg).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByLabelText('이름')).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: '열기' })).toHaveFocus();
  });

  it('TC-WF-020 Tab 이 대화상자 안에서만 순환하고 배경은 inert 가 된다', async () => {
    const user = userEvent.setup();
    render(<Demo onClose={() => undefined} />);
    await user.click(screen.getByRole('button', { name: '열기' }));
    expect(document.getElementById('root')).toHaveAttribute('inert');
    expect(screen.getByLabelText('이름')).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: '확인' })).toHaveFocus();
    await user.tab();
    expect(screen.getByLabelText('이름')).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole('button', { name: '확인' })).toHaveFocus();
  });

  it('TC-WF-021 대화상자에 접근성 위반이 없다', async () => {
    const user = userEvent.setup();
    render(<Demo onClose={() => undefined} />);
    await user.click(screen.getByRole('button', { name: '열기' }));
    expect(await axeViolations(screen.getByRole('dialog'))).toEqual([]);
  });
});

describe('ConfirmPhrase', () => {
  function Host() {
    const [v, setV] = useState('');
    return (
      <>
        <ConfirmPhrase phrase="실행 3건" value={v} onChange={setV} />
        <button disabled={v !== '실행 3건'}>실행</button>
      </>
    );
  }
  it('TC-WF-022 문구가 정확히 일치할 때만 일치 안내가 나온다', async () => {
    const user = userEvent.setup();
    render(<Host />);
    const input = screen.getByRole('textbox');
    await user.type(input, '실행 2건');
    expect(screen.getByText(/문구가 일치하지 않습니다/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '실행' })).toBeDisabled();
    await user.clear(input);
    await user.type(input, '실행 3건');
    expect(screen.getByText(/문구가 일치합니다/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '실행' })).toBeEnabled();
  });
});

describe('ValidationBadge', () => {
  it('TC-WF-023 통과/경고/차단을 색뿐 아니라 기호와 글자로 구분한다', () => {
    const { rerender } = render(<ValidationBadge result="pass" />);
    expect(screen.getByText('통과')).toBeInTheDocument();
    expect(screen.getByText('✓')).toBeInTheDocument();
    rerender(<ValidationBadge result="warn" />);
    expect(screen.getByText('경고')).toBeInTheDocument();
    expect(screen.getByText('▲')).toBeInTheDocument();
    rerender(<ValidationBadge result="block" />);
    expect(screen.getByText('차단')).toBeInTheDocument();
    expect(screen.getByText('✕')).toBeInTheDocument();
    rerender(<ValidationBadge result={null} />);
    expect(screen.getByText('검증 전')).toBeInTheDocument();
  });
});

describe('Tabs / Pagination / 오류 문구', () => {
  it('TC-WF-024 탭은 좌우 방향키로 이동하고 선택 상태를 aria-selected 로 알린다', async () => {
    const user = userEvent.setup();
    function Host() {
      const [v, setV] = useState('a');
      return (
        <Tabs
          label="구역"
          value={v}
          onChange={setV}
          items={[
            { id: 'a', label: '가' },
            { id: 'b', label: '나' },
          ]}
        >
          <p>내용 {v}</p>
        </Tabs>
      );
    }
    render(<Host />);
    screen.getByRole('tab', { name: '가' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: '나' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: '나' })).toHaveFocus();
    expect(screen.getByText('내용 b')).toBeInTheDocument();
  });

  it('TC-WF-025 첫 쪽에서는 이전, 마지막 쪽에서는 다음 버튼이 꺼진다', () => {
    const { rerender } = render(
      <Pagination page={1} pageSize={50} total={200} onPage={() => undefined} />,
    );
    expect(screen.getByRole('button', { name: '이전' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '다음' })).toBeEnabled();
    rerender(<Pagination page={4} pageSize={50} total={200} onPage={() => undefined} />);
    expect(screen.getByRole('button', { name: '다음' })).toBeDisabled();
  });

  it('TC-WF-026 오류를 연결 끊김·세션 만료·한도 초과·일반 오류로 나눠 한국어로 바꾼다', () => {
    const mk = (status: number, code: string) =>
      new ApiError({ status, code, title: '서버 제목', detail: '서버 상세', hint: '서버 힌트' });
    expect(describeError(mk(0, 'network_error')).kind).toBe('network');
    expect(describeError(mk(401, 'session_expired')).kind).toBe('expired');
    expect(describeError(mk(429, 'rate_limited')).kind).toBe('limit');
    const gen = describeError(mk(409, 'suggestion_blocked'));
    expect(gen).toMatchObject({
      kind: 'error',
      title: '서버 제목',
      detail: '서버 상세',
      hint: '서버 힌트',
    });
    expect(describeError(new Error('x')).title).toBe('불러오지 못했습니다');
  });
});
