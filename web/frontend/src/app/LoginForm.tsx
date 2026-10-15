import { useState, type FormEvent } from 'react';
import { ApiError } from '../api/client';
import { useApiClient } from '../api/context';
import { Button, Callout, Field } from '../components';
import { describeError } from '../components/ErrorPanel';
import { ko } from '../i18n/ko';

function message(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.isNetwork) return ko.login.network;
    if (err.status === 401) return ko.login.invalid;
    if (err.status === 429) return err.hint || err.detail || ko.login.lockedFallback;
    if (err.code === 'login_not_configured') return ko.login.notConfigured;
  }
  const v = describeError(err);
  return v.detail || v.title;
}

/** 관리자 아이디·비밀번호 로그인 폼. 입력값은 상태에만 두고 console·URL·저장소에 남기지 않는다. */
export function LoginForm({ onDone, expired }: { onDone?: () => void; expired?: boolean }) {
  const client = useApiClient();
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || !loginId || !password) return;
    setBusy(true);
    setErr(null);
    try {
      await client.login(loginId, password);
      setPassword('');
      onDone?.();
    } catch (x) {
      setPassword('');
      setErr(x);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} className="stack" noValidate>
      {expired && err === null && (
        <Callout tone="warning" role="status">
          <p>{ko.login.expired}</p>
        </Callout>
      )}
      <Field label={ko.login.idLabel}>
        <input
          className="input"
          type="text"
          name="username"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          maxLength={40}
          value={loginId}
          data-autofocus=""
          onChange={(e) => setLoginId(e.target.value)}
        />
      </Field>
      <Field label={ko.login.passwordLabel}>
        <input
          className="input"
          type="password"
          name="password"
          autoComplete="current-password"
          maxLength={128}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      {err !== null && (
        <Callout tone="danger" role="alert">
          <p>{message(err)}</p>
        </Callout>
      )}
      <Button type="submit" variant="primary" busy={busy} disabled={!loginId || !password}>
        {ko.login.submit}
      </Button>
    </form>
  );
}
