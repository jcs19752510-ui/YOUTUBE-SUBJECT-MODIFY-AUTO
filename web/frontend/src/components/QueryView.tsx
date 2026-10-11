import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { ErrorPanel } from './ErrorPanel';
import { Skeleton } from './Skeleton';

/** 쿼리 상태(로딩/오류/성공)를 한 곳에서 처리한다. 오류에는 재시도 버튼을 붙인다. */
export function QueryView<T>({
  query,
  lines,
  children,
}: {
  query: UseQueryResult<T>;
  lines?: number;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <Skeleton lines={lines} />;
  if (query.isError) return <ErrorPanel error={query.error} onRetry={() => void query.refetch()} />;
  return <>{children(query.data)}</>;
}
