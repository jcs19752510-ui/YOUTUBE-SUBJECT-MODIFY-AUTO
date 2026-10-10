import type { ReactNode } from 'react';

/** 가로로 넘칠 때 키보드로도 스크롤할 수 있게 tabIndex 를 둔 표 래퍼 */
export function TableWrap({ label, children }: { label: string; children: ReactNode }) {
  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
    <div className="table-wrap" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}

export function SortHeader({
  label,
  active,
  order,
  onSort,
}: {
  label: string;
  active: boolean;
  order: 'asc' | 'desc';
  onSort: () => void;
}) {
  return (
    <th scope="col" aria-sort={active ? (order === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button type="button" className="th-sort" onClick={onSort}>
        {label}
        <span aria-hidden="true">{active ? (order === 'asc' ? '▲' : '▼') : '↕'}</span>
      </button>
    </th>
  );
}
