import { ko } from '../i18n/ko';

/** 로딩 자리표시자. 스크린리더에는 한 번만 "불러오는 중"을 알린다. */
export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{ko.app.loading}</span>
      <div aria-hidden="true">
        {Array.from({ length: lines }, (_, i) => (
          <span key={i} className="skeleton" />
        ))}
      </div>
    </div>
  );
}
