import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { ApiError, type ApiClient } from '../api/client';
import { ApiProvider } from '../api/context';
import { ToastProvider } from '../components';
import { SelectionProvider } from '../hooks/selection';

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        // 4xx 는 다시 해도 같으므로 재시도하지 않고, 연결 문제만 한 번 더 시도한다
        retry: (count, err) => err instanceof ApiError && err.isNetwork && count < 1,
      },
      mutations: { retry: false },
    },
  });
}

export function Providers({ client, children }: { client: ApiClient; children: ReactNode }) {
  const [qc] = useState(makeQueryClient);
  return (
    <ApiProvider client={client}>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <SelectionProvider>{children}</SelectionProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ApiProvider>
  );
}
