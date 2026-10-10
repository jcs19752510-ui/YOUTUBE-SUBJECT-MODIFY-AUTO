import type { ButtonHTMLAttributes, ReactNode } from 'react';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'danger' | 'ghost';
  size?: 'md' | 'sm';
  /** 진행 중: 버튼을 비활성화하고 스피너를 보여 중복 클릭을 막는다 */
  busy?: boolean;
  children: ReactNode;
}

export function Button({
  variant = 'default',
  size = 'md',
  busy = false,
  disabled,
  className = '',
  type = 'button',
  children,
  ...rest
}: Props) {
  const cls = ['btn', variant !== 'default' && `btn--${variant}`, size === 'sm' && 'btn--sm', className]
    .filter(Boolean)
    .join(' ');
  return (
    <button {...rest} type={type} className={cls} disabled={disabled || busy} aria-busy={busy || undefined}>
      {busy && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}
