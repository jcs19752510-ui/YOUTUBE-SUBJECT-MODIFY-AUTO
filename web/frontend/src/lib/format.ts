const TZ = 'Asia/Seoul';
const dt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});
const d = new Intl.DateTimeFormat('ko-KR', {
  timeZone: TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});
const nf = new Intl.NumberFormat('ko-KR');

/** 서버 시각(UTC ISO)을 한국 시간 "YYYY-MM-DD HH:MM" 으로 */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '-';
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return '-';
  const parts = Object.fromEntries(dt.formatToParts(t).map((p) => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

/** "YYYY-MM-DD" 날짜 문자열은 그대로, ISO 시각이면 한국 날짜로 */
export function fmtDate(v: string | null | undefined): string {
  if (!v) return '-';
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  const t = new Date(v);
  if (Number.isNaN(t.getTime())) return '-';
  const parts = Object.fromEntries(d.formatToParts(t).map((p) => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function fmtNum(n: number | null | undefined): string {
  return n === null || n === undefined ? '-' : nf.format(n);
}

export function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined) return '-';
  return `${n.toFixed(digits)}%`;
}

export function fmtDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined) return '-';
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** 글자 수는 화면 표시용으로 유니코드 코드포인트 기준 */
export function charCount(s: string): number {
  return Array.from(s).length;
}
