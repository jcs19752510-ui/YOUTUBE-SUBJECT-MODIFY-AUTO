export interface DiffPart {
  type: 'same' | 'del' | 'ins';
  text: string;
}

/** 단어(공백 포함 토큰) 단위 LCS 비교. 글자 단위는 완전히 다른 제목에서 조각이 흩어져 읽기 어렵다. 제목은 짧아 O(n*m) 로 충분하다. */
export function diffTitles(before: string, after: string): DiffPart[] {
  const a = before.match(/\s+|\S+/g) ?? [];
  const b = after.match(/\s+|\S+/g) ?? [];
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i]![j] = a[i] === b[j] ? dp[i + 1]![j + 1]! + 1 : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!);
    }
  }
  const out: DiffPart[] = [];
  const push = (type: DiffPart['type'], ch: string) => {
    const last = out[out.length - 1];
    if (last && last.type === type) last.text += ch;
    else out.push({ type, text: ch });
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      push('same', a[i]!);
      i++;
      j++;
    } else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) {
      push('del', a[i++]!);
    } else {
      push('ins', b[j++]!);
    }
  }
  while (i < n) push('del', a[i++]!);
  while (j < m) push('ins', b[j++]!);
  return out;
}
