import { useState } from 'react';

// 승인자 이름은 비밀이 아니지만 저장소에 남기지 않고 이 탭의 메모리에만 기억한다
let remembered = '';

export function useApproverName(): [string, (v: string) => void] {
  const [v, set] = useState(remembered);
  return [
    v,
    (n: string) => {
      remembered = n;
      set(n);
    },
  ];
}
