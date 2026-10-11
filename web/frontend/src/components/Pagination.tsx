import { ko } from '../i18n/ko';
import { fmtNum } from '../lib/format';
import { Button } from './Button';

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
  sizes = [25, 50, 100],
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
  onPageSize?: (n: number) => void;
  sizes?: number[];
}) {
  const last = Math.max(1, Math.ceil(total / pageSize));
  // 주소로 들어온 쪽 크기가 목록에 없어도 실제 값 그대로 보여 준다
  const options = sizes.includes(pageSize) ? sizes : [...sizes, pageSize].sort((a, b) => a - b);
  return (
    <nav className="pagination" aria-label={ko.pagination.nav}>
      <div className="row">
        <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          {ko.pagination.prev}
        </Button>
        <span aria-live="polite" aria-atomic="true">
          {ko.pagination.page(page, last)} · {fmtNum(total)}
        </span>
        <Button size="sm" disabled={page >= last} onClick={() => onPage(page + 1)}>
          {ko.pagination.next}
        </Button>
      </div>
      {onPageSize && (
        <label className="row">
          {ko.pagination.size}
          <select
            className="select"
            value={pageSize}
            onChange={(e) => onPageSize(Number(e.target.value))}
          >
            {options.map((s) => (
              <option key={s} value={s}>
                {ko.pagination.sizeUnit(s)}
              </option>
            ))}
          </select>
        </label>
      )}
    </nav>
  );
}
