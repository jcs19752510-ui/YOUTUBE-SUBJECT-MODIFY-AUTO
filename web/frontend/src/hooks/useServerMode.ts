import { useQuery } from '@tanstack/react-query';
import { useApi } from '../api/context';

/** 서버가 알려 주는 실제 모드(대시보드 상태). 모르면 가장 안전한 데모로 본다. */
export function useServerMode(): { live: boolean; googleConnected: boolean } {
  const api = useApi();
  const d = useQuery({ queryKey: ['dashboard'], queryFn: () => api.dashboard() }).data;
  return { live: d?.mode === 'live', googleConnected: d?.google.connected ?? false };
}
