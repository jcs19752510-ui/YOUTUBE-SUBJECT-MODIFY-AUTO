import type { ReactNode } from 'react';

export function Card({
  title,
  headingLevel = 2,
  flat,
  children,
  className = '',
  ...rest
}: {
  title?: ReactNode;
  headingLevel?: 2 | 3;
  flat?: boolean;
  children: ReactNode;
  className?: string;
  'aria-labelledby'?: string;
}) {
  const H = headingLevel === 2 ? 'h2' : 'h3';
  return (
    <section className={`card${flat ? ' card--flat' : ''} ${className}`.trim()} {...rest}>
      {title && <H className="card__title">{title}</H>}
      {children}
    </section>
  );
}
