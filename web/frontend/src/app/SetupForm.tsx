import { useState, type FormEvent } from 'react';
import { ApiError } from '../api/client';
import { useApiClient } from '../api/context';
import { Button } from '../components';
import { describeError } from '../components/ErrorPanel';
import { ko } from '../i18n/ko';
import { AuthCard } from './AuthCard';

const ID_RE = /^[A-Za-z0-9]{4,20}$/;

/** 화면에서 먼저 하는 검사. 문제 없으면 null. */
export function validateSetup(loginId: string, password: string, confirm: string): string | null {
  if (!ID_RE.test(loginId)) return ko.setup.badId;
  if (password.length < 8 || password.length > 64) return ko.setup.badPassword;
  if (password !== confirm) return ko.setup.mismatch;
  return null;
}

function message(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.isNetwork) return ko.login.network;
    if (err.code === 'setup_closed') return ko.setup.closed;
    if (err.code === 'setup_invalid') return err.detail || err.hint || ko.setup.invalidFallback;
    if (err.status === 429) return err.hint || err.detail || ko.login.lockedFallback;
  }
  const v = describeError(err);
  return v.detail || v.title;
}

/** 최초 관리자 계정 만들기 카드. 비밀번호 확인 값은 화면에서만 비교하고 서버로 보내지 않는다. */
export function SetupForm({ onDone }: { onDone?: () => void }) {
  const client = useApiClient();
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const bad = validateSetup(loginId, password, confirm);
    if (bad) {
      setMsg(bad);
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await client.setup(loginId, password);
      setPassword('');
      setConfirm('');
      onDone?.();
    } catch (x) {
      setPassword('');
      setConfirm('');
      setMsg(message(x));
    } finally {
      setBusy(false);
    }
  };

  const shown = msg ?? (!loginId ? ko.setup.promptId : '');
  const isErr = msg !== null;

  return (
    <AuthCard title={ko.setup.title} body={ko.setup.body}>
      <form onSubmit={(e) => void submit(e)} className="stack" noValidate>
        <p
          id="setup-msg"
          className="auth-card__msg"
          role={isErr ? 'alert' : undefined}
          aria-live={isErr ? undefined : 'polite'}
        >
          {shown}
        </p>
        <input
          className="input"
          type="text"
          id="setup-id"
          name="username"
          aria-label={ko.setup.idLabel}
          placeholder={ko.login.idPlaceholder}
          aria-describedby="setup-msg"
          aria-invalid={isErr ? true : undefined}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          maxLength={40}
          value={loginId}
          data-autofocus=""
          onChange={(e) => setLoginId(e.target.value)}
        />
        <input
          className="input"
          type="password"
          id="setup-password"
          name="new-password"
          aria-label={ko.setup.passwordLabel}
          placeholder={ko.login.passwordPlaceholder}
          aria-describedby="setup-msg"
          autoComplete="new-password"
          maxLength={128}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <input
          className="input"
          type="password"
          id="setup-confirm"
          name="confirm-password"
          aria-label={ko.setup.confirmLabel}
          placeholder={ko.setup.confirmPlaceholder}
          aria-describedby="setup-msg"
          autoComplete="new-password"
          maxLength={128}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <Button type="submit" variant="primary" busy={busy} disabled={!loginId || !password || !confirm}>
          {ko.setup.submit}
        </Button>
      </form>
    </AuthCard>
  );
}
