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
    return {
      kind,
      title:
        kind === 'network'
          ? ko.state.networkTitle
          : kind === 'expired'
            ? ko.state.expiredTitle
            : kind === 'limit'
              ? ko.state.limitTitle
              : e.title,
      detail: e.detail || fallback || (kind === 'error' ? '' : e.title),
      hint: e.hint || (kind === 'network' ? ko.conn.offlineHint : ko.state.defaultHint),
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
