import { ApiError } from '../api/client';
import { ko } from '../i18n/ko';
import { Button } from './Button';
import { Callout } from './Callout';

export interface ErrorView {
  kind: 'network' | 'expired' | 'limit' | 'error';
  title: string;
  detail: string;
  hint: string;
  code: string;
}

const HANGUL = /[\u3131-\u318e\uac00-\ud7a3]/;
const WORDS = /[A-Za-z]{3,}/;
/** 서버(검증 라이브러리 등)가 영어 문장을 그대로 내려 준 경우를 가려낸다. 한글이 하나도 없고 영어 단어가 있을 때만 */
const isForeign = (t: string) => t !== '' && !HANGUL.test(t) && WORDS.test(t);

/** 어떤 오류든 화면에 보여 줄 한국어 문구로 바꾼다. 서버 문구(한국어)를 우선하고 없으면 코드별 기본 문구를 쓴다. */
export function describeError(e: unknown): ErrorView {
  if (e instanceof ApiError) {
    const kind = e.isNetwork
      ? 'network'
      : e.isSessionExpired
        ? 'expired'
        : e.isLimit
          ? 'limit'
          : 'error';
    const fallback = ko.errors[e.code];
    // 코드별 한국어 문구가 있을 때만 영어 원문을 바꾼다(없으면 서버가 준 문장을 그대로 보여 준다)
    const foreignTitle = fallback !== undefined && isForeign(e.title);
    const foreignDetail = fallback !== undefined && isForeign(e.detail);
    return {
      kind,
      title:
        kind === 'network'
          ? ko.state.networkTitle
          : kind === 'expired'
            ? ko.state.expiredTitle
            : kind === 'limit'
              ? ko.state.limitTitle
              : foreignTitle
                ? ko.state.errorTitle
                : e.title,
      detail: foreignDetail ? fallback : e.detail || fallback || (kind === 'error' ? '' : e.title),
      hint:
        (fallback !== undefined && isForeign(e.hint) ? '' : e.hint) ||
        ko.errorHints[e.code] ||
        (kind === 'network' ? ko.conn.offlineHint : ko.state.defaultHint),
      code: e.code,
    };
  }
  return {
    kind: 'error',
    title: ko.state.errorTitle,
    detail: '',
    hint: ko.state.defaultHint,
    code: 'unknown',
  };
}

export function ErrorPanel({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const v = describeError(error);
  return (
    <Callout tone={v.kind === 'limit' ? 'warning' : 'danger'} role="alert" title={v.title}>
      {v.detail && <p>{v.detail}</p>}
      <p>
        <strong>{ko.state.nextStep}:</strong> {v.hint}
      </p>
      <p className="muted">
        {ko.state.codeLabel}: <code>{v.code}</code>
      </p>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          {ko.app.retry}
        </Button>
      )}
    </Callout>
  );
}
