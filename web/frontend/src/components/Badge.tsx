import type { ReactNode } from 'react';

export type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

export function Badge({
  tone = 'neutral',
  icon,
  children,
}: {
  tone?: Tone;
  icon?: string;
  children: ReactNode;
}) {
  return (
    <span className={`badge${tone === 'neutral' ? '' : ` badge--${tone}`}`}>
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </span>
  );
}
