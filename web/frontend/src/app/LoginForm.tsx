import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../api/client';
import { useApiClient } from '../api/context';
import { Button, Callout } from '../components';
import { describeError } from '../components/ErrorPanel';
import { ko } from '../i18n/ko';
import { AuthCard } from './AuthCard';

function message(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.isNetwork) return ko.login.network;
    if (err.status === 401) return ko.login.invalid;
    if (err.status === 429) return err.hint || err.detail || ko.login.lockedFallback;
    if (err.code === 'login_not_configured')
      return [err.title, err.hint].filter(Boolean).join(' ') || ko.login.notConfigured;
  }
  const v = describeError(err);
  return v.detail || v.title;
}

/**
 * 관리자 아이디·비밀번호 로그인 카드. 입력값은 상태에만 두고 console·URL·저장소에 남기지 않는다.
 * 브라우저(비밀번호 관리자)가 저장해 둔 아이디·비밀번호를 자동으로 채우지 않도록 한다(선생님 지시 2026-10-15):
 * ①자동 채움을 끄는 속성(form·아이디 off, 비밀번호 new-password) ②사용자가 칸을 누르기 전에는 읽기 전용
 * ③화면이 열릴 때·뒤로 가기로 다시 나타날 때 칸을 비운다. 브라우저 자체의 저장 기능은 이 화면이 끌 수 없어 한계가 있다.
 */
export function LoginForm({ onDone, expired }: { onDone?: () => void; expired?: boolean }) {
  const client = useApiClient();
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [armed, setArmed] = useState(false); // 사용자가 칸을 누르기 전에는 읽기 전용(브라우저 자동 채움은 읽기 전용 칸을 채우지 못한다)
  const idRef = useRef<HTMLInputElement>(null);
  const pwRef = useRef<HTMLInputElement>(null);
  const typed = useRef(false); // 사람이 키보드로 입력했는지(자동 채움은 키 입력 이벤트가 없다)

  const wipeDom = useCallback(() => {
    if (idRef.current) idRef.current.value = '';
    if (pwRef.current) pwRef.current.value = '';
  }, []);
  const wipe = useCallback(() => {
    setLoginId('');
    setPassword('');
    wipeDom();
  }, [wipeDom]);

  useEffect(() => {
    wipeDom(); // 처음 그릴 때 상태는 이미 비어 있다. 화면 값만 비운다.
    // 브라우저는 화면이 뜬 뒤 조금 늦게 채우기도 한다. 사람이 입력하기 전이면 그때마다 다시 비운다.
    const timers = [60, 250, 700, 1500].map((ms) =>
      window.setTimeout(() => {
        if (!typed.current) wipe();
      }, ms),
    );
    // 뒤로 가기·앞으로 가기로 이전 화면이 그대로 복원될 때도 비운다.
    const onShow = (ev: PageTransitionEvent) => {
      if (ev.persisted) {
        typed.current = false;
        setArmed(false);
        wipe();
      }
    };
    window.addEventListener('pageshow', onShow);
    return () => {
      timers.forEach((t) => window.clearTimeout(t));
      window.removeEventListener('pageshow', onShow);
    };
  }, [wipe, wipeDom]);

  const human = () => {
    typed.current = true;
  };

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

  const hasErr = err !== null;
  const msg = hasErr ? message(err) : !loginId ? ko.login.promptId : !password ? ko.login.promptPassword : '';

  return (
    <AuthCard title={ko.login.title}>
      <form onSubmit={(e) => void submit(e)} className="stack" noValidate autoComplete="off">
        {expired && !hasErr && (
          <Callout tone="warning" role="status">
            <p>{ko.login.expired}</p>
          </Callout>
        )}
        <p
          id="login-msg"
          className="auth-card__msg"
          role={hasErr ? 'alert' : undefined}
          aria-live={hasErr ? undefined : 'polite'}
        >
          {msg}
        </p>
        <input
          className="input"
          type="text"
          id="login-id"
          name="admin-login-id"
          ref={idRef}
          readOnly={!armed}
          onFocus={() => setArmed(true)}
          onPointerDown={() => setArmed(true)}
          onKeyDown={human}
          onPaste={human}
          aria-label={ko.login.idLabel}
          placeholder={ko.login.idPlaceholder}
          aria-describedby="login-msg"
          autoComplete="off"
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
          id="login-password"
          name="admin-login-secret"
          ref={pwRef}
          readOnly={!armed}
          onFocus={() => setArmed(true)}
          onPointerDown={() => setArmed(true)}
          onKeyDown={human}
          onPaste={human}
          aria-label={ko.login.passwordLabel}
          placeholder={ko.login.passwordPlaceholder}
          aria-describedby="login-msg"
          aria-invalid={hasErr ? true : undefined}
          autoComplete="new-password"
          maxLength={128}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" variant="primary" busy={busy} disabled={!loginId || !password}>
          {ko.login.submit}
        </Button>
      </form>
    </AuthCard>
  );
}
