import { useId } from 'react';
import { ko } from '../i18n/ko';

/** 되돌릴 수 없는 동작 전에 정해진 문구를 직접 입력하게 한다. 일치(matches)할 때만 실행 버튼을 켜는 것은 호출자 몫. */
export function ConfirmPhrase({
  phrase,
  value,
  onChange,
  label,
  hint,
  autoFocus,
}: {
  phrase: string;
  value: string;
  onChange: (v: string) => void;
  label?: string;
  hint?: string;
  autoFocus?: boolean;
}) {
  const id = useId();
  const matches = value === phrase;
  return (
    <div className="confirm-phrase">
      <label htmlFor={id} className="field__label">
        {label ?? ko.batches.confirmLabel}: <span className="phrase">{phrase}</span>
      </label>
      {hint && <p id={`${id}-hint`}>{hint}</p>}
      <input
        id={id}
        className="input"
        type="text"
        value={value}
        autoComplete="off"
        spellCheck={false}
        data-autofocus={autoFocus ? '' : undefined}
        aria-describedby={`${id}-status${hint ? ` ${id}-hint` : ''}`}
        onChange={(e) => onChange(e.target.value)}
      />
      <p id={`${id}-status`} aria-live="polite">
        {value === ''
          ? ''
          : matches
            ? `✓ ${ko.batches.confirmMatch}`
            : `✕ ${ko.batches.confirmMismatch}`}
      </p>
    </div>
  );
}
