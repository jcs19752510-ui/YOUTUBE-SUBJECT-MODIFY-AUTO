import type { ReactNode } from 'react';

const ICON = { info: 'ⓘ', warning: '▲', danger: '✕', success: '✓' } as const;

export function Callout({
  tone = 'info',
  title,
  children,
  role,
}: {
  tone?: keyof typeof ICON;
  title?: ReactNode;
  children?: ReactNode;
  role?: 'alert' | 'status';
}) {
  return (
    <div className={`callout${tone === 'info' ? '' : ` callout--${tone}`}`} role={role}>
      <span className="callout__icon" aria-hidden="true">
        {ICON[tone]}
      </span>
      <div className="callout__body">
        {title && <p className="callout__title">{title}</p>}
        {children}
      </div>
    </div>
  );
}
