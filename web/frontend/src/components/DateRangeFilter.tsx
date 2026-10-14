import { useState } from 'react';
import { kstDateOffset } from '../lib/format';
import { ko } from '../i18n/ko';
import { Button } from './Button';
import { Field } from './Field';

export interface DateRange {
  from: string;
  to: string;
  setFrom: (v: string) => void;
  setTo: (v: string) => void;
  /** 시작일이 종료일보다 뒤이면 false (이때는 조회하지 않는다) */
  valid: boolean;
  /** 둘 다 비어 있으면 전체 기간 */
  isAll: boolean;
  /** 조회에 쓰는 값: 비어 있으면 undefined */
  query: { date_from?: string; date_to?: string };
  setAll: () => void;
  setToday: () => void;
}

/** 조회 기간 상태. 기본값은 한국 시간 기준 오늘(시작일=종료일=오늘). */
export function useDateRange(): DateRange {
  const [from, setFrom] = useState(() => kstDateOffset(0));
  const [to, setTo] = useState(() => kstDateOffset(0));
  const valid = !from || !to || from <= to;
  return {
    from,
    to,
    setFrom,
    setTo,
    valid,
    isAll: !from && !to,
    query: { date_from: from || undefined, date_to: to || undefined },
    setAll: () => {
      setFrom('');
      setTo('');
    },
    setToday: () => {
      setFrom(kstDateOffset(0));
      setTo(kstDateOffset(0));
    },
  };
}

/** 달력 2개(시작일·종료일)와 [오늘] [전체 기간] 버튼. 날짜 기준은 한국 시간. */
export function DateRangeFilter({
  range,
  basis,
  onChange,
}: {
  range: DateRange;
  /** 어떤 날짜 기준인지 화면에 알려 주는 짧은 글(예: "요청 시각 기준") */
  basis: string;
  onChange?: () => void;
}) {
  return (
    <div className="toolbar" role="group" aria-label={ko.dateRange.groupLabel}>
      <Field label={ko.dateRange.from} hint={ko.dateRange.basis(basis)}>
        <input
          name="date-from"
          className="input"
          type="date"
          value={range.from}
          max={range.to || undefined}
          onChange={(e) => {
            range.setFrom(e.target.value);
            onChange?.();
          }}
        />
      </Field>
      <Field
        label={ko.dateRange.to}
        error={range.valid ? undefined : ko.dateRange.invalid}
      >
        <input
          name="date-to"
          className="input"
          type="date"
          value={range.to}
          min={range.from || undefined}
          onChange={(e) => {
            range.setTo(e.target.value);
            onChange?.();
          }}
        />
      </Field>
      <Button
        onClick={() => {
          range.setToday();
          onChange?.();
        }}
      >
        {ko.dateRange.today}
      </Button>
      <Button
        onClick={() => {
          range.setAll();
          onChange?.();
        }}
      >
        {ko.dateRange.all}
      </Button>
    </div>
  );
}
