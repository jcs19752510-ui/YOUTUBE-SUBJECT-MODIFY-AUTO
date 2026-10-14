import type { VideoKind } from '../api/types';
import { ko } from '../i18n/ko';
import { Badge } from './Badge';
import { Field } from './Field';

/** 영상 구분 선택 상자(전체/롱폼/쇼츠). value '' = 전체 */
export function KindSelect({
  value,
  onChange,
}: {
  value: '' | VideoKind;
  onChange: (v: '' | VideoKind) => void;
}) {
  return (
    <Field label={ko.kind.label}>
      <select
        name="kind-filter"
        className="select"
        value={value}
        onChange={(e) => onChange(e.target.value as '' | VideoKind)}
      >
        <option value="">{ko.kind.all}</option>
        <option value="long">{ko.kind.long}</option>
        <option value="short">{ko.kind.short}</option>
      </select>
    </Field>
  );
}

/** 결과 표의 구분 칸: 롱폼/쇼츠 배지, 길이를 모르면 '-' */
export function KindBadge({ kind }: { kind: VideoKind | null | undefined }) {
  if (kind === 'short') return <Badge tone="info">{ko.kind.short}</Badge>;
  if (kind === 'long') return <Badge>{ko.kind.long}</Badge>;
  return <>{ko.kind.unknown}</>;
}
