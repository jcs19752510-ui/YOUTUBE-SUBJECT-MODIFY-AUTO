import { ko } from '../i18n/ko';
import { diffTitles } from '../lib/diff';
import { charCount } from '../lib/format';

/** 변경 전/후 제목 비교. 삭제=취소선, 추가=밑줄 + 스크린리더용 문구(색에만 의존하지 않음). 외부 문자열은 텍스트로만 렌더링한다. */
export function TitleDiff({ before, after }: { before: string; after: string }) {
  const parts = diffTitles(before, after);
  const a = charCount(before);
  const b = charCount(after);
  return (
    <div className="diff">
      <span className="diff__label">{ko.suggestion.before}</span>
      <span className="diff__text">
        {parts.map((p, i) =>
          p.type === 'ins' ? null : p.type === 'del' ? (
            <del key={i}>
              <span className="sr-only">{ko.suggestion.removed}</span>
              {p.text}
            </del>
          ) : (
            <span key={i}>{p.text}</span>
          ),
        )}
      </span>
      <span className="diff__label">{ko.suggestion.after}</span>
      <span className="diff__text">
        {parts.map((p, i) =>
          p.type === 'del' ? null : p.type === 'ins' ? (
            <ins key={i}>
              <span className="sr-only">{ko.suggestion.added}</span>
              {p.text}
            </ins>
          ) : (
            <span key={i}>{p.text}</span>
          ),
        )}
      </span>
      <span className="diff__count">{ko.suggestion.charsLine(a, b)}</span>
    </div>
  );
}
