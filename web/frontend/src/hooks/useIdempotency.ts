import { useState } from 'react';
import { IdempotencyKeys } from '../api/client';

/** 같은 요청을 다시 보낼 때(오류 후 재시도) 같은 키를 쓰고, 요청 내용이 바뀌면 새 키를 쓴다. */
export function useIdempotency(): IdempotencyKeys {
  const [keys] = useState(() => new IdempotencyKeys());
  return keys;
}
