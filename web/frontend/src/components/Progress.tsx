export function Progress({ value, max, label }: { value: number; max: number; label: string }) {
  return <progress className="progress" value={value} max={Math.max(max, 1)} aria-label={label} />;
}
