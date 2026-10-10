import { useRef, type KeyboardEvent, type ReactNode } from 'react';

export interface TabItem {
  id: string;
  label: string;
}

/** WAI-ARIA tabs 패턴: 좌우 방향키·Home·End 로 이동. 패널 내용은 children 으로 받는다. */
export function Tabs({
  items,
  value,
  onChange,
  label,
  children,
}: {
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  children: ReactNode;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const onKey = (e: KeyboardEvent) => {
    const i = items.findIndex((t) => t.id === value);
    let n = i;
    if (e.key === 'ArrowRight') n = (i + 1) % items.length;
    else if (e.key === 'ArrowLeft') n = (i - 1 + items.length) % items.length;
    else if (e.key === 'Home') n = 0;
    else if (e.key === 'End') n = items.length - 1;
    else return;
    e.preventDefault();
    const next = items[n];
    if (next) {
      onChange(next.id);
      refs.current[next.id]?.focus();
    }
  };
  return (
    <div>
      <div className="tabs" role="tablist" aria-label={label}>
        {items.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            className="tab"
            aria-selected={t.id === value}
            aria-controls={`panel-${t.id}`}
            tabIndex={t.id === value ? 0 : -1}
            onClick={() => onChange(t.id)}
            onKeyDown={onKey}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${value}`} aria-labelledby={`tab-${value}`} tabIndex={0}>
        {children}
      </div>
    </div>
  );
}
