import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from 'react';

interface Props {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  className?: string;
  children: ReactElement<Record<string, unknown>>;
}

/** 라벨·도움말·오류를 입력칸과 연결(aria-describedby)한다. */
export function Field({ label, hint, error, className = '', children }: Props) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errId = `${id}-err`;
  const describedBy =
    [hint ? hintId : '', error ? errId : ''].filter(Boolean).join(' ') || undefined;
  const control = isValidElement(children)
    ? cloneElement(children, {
        id,
        'aria-describedby': describedBy,
        'aria-invalid': error ? true : undefined,
      })
    : children;
  return (
    <div className={`field ${className}`.trim()}>
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      {control}
      {hint && (
        <span className="field__hint" id={hintId}>
          {hint}
        </span>
      )}
      {error && (
        <span className="field__error" id={errId} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
