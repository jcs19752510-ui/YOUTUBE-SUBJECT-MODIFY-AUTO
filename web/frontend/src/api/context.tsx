import { createContext, useContext, useMemo, useSyncExternalStore, type ReactNode } from 'react';
import { ApiClient, type ConnectionSnapshot } from './client';
import { createEndpoints, type Endpoints } from './endpoints';

interface ApiContextValue {
  client: ApiClient;
  api: Endpoints;
}
const Ctx = createContext<ApiContextValue | null>(null);

export function ApiProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  const value = useMemo(() => ({ client, api: createEndpoints(client) }), [client]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function useCtx(): ApiContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('ApiProvider 가 필요합니다');
  return v;
}
export const useApi = (): Endpoints => useCtx().api;
export const useApiClient = (): ApiClient => useCtx().client;

export function useConnection(): ConnectionSnapshot {
  const { client } = useCtx();
  return useSyncExternalStore(client.subscribe, client.getSnapshot);
}
