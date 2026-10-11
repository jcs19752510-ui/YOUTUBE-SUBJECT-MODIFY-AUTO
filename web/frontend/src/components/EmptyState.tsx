import type { ReactNode } from 'react';

export function EmptyState({
  title,
  children,
  action,
}: {
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <p className="empty__title">{title}</p>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  );
}
