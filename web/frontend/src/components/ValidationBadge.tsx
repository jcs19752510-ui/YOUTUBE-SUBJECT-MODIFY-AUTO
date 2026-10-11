import { ko } from '../i18n/ko';
import type { ValidationResult } from '../api/types';
import { Badge, type Tone } from './Badge';

const MAP: Record<ValidationResult, { tone: Tone; icon: string; label: string }> = {
  pass: { tone: 'success', icon: ko.validation.passIcon, label: ko.validation.pass },
  warn: { tone: 'warning', icon: ko.validation.warnIcon, label: ko.validation.warn },
  block: { tone: 'danger', icon: ko.validation.blockIcon, label: ko.validation.block },
};

/** 색에만 의존하지 않도록 기호+글자를 함께 보여 준다. */
export function ValidationBadge({ result }: { result: ValidationResult | null }) {
  if (!result || !Object.hasOwn(MAP, result)) return <Badge>{ko.validation.none}</Badge>;
  const m = MAP[result];
  return (
    <Badge tone={m.tone} icon={m.icon}>
      {m.label}
    </Badge>
  );
}
