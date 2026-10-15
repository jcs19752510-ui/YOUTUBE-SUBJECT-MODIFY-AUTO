import { useEffect, useRef, useState } from 'react';
import { useApiClient } from '../api/context';
import { Button, Modal } from '../components';
import { ko } from '../i18n/ko';

const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'click', 'keydown', 'touchstart', 'scroll', 'wheel'];

/** 경고를 띄우는 시점(한도 몇 초 전): 기본 5분, 한도가 짧으면 한도의 1/6 */
export function warnSeconds(limit: number): number {
  return Math.max(1, Math.min(300, Math.floor(limit / 6)));
}

/** 무활동 자동 로그아웃(화면 쪽). 서버가 한도(idle_timeout_seconds)를 주지 않으면 아무것도 하지 않는다. */
export function IdleLogout() {
  const client = useApiClient();
  const limit = client.idleTimeoutSeconds;
  const last = useRef(0);
  const lastTouch = useRef(0);
  const done = useRef(false);
  const continueRef = useRef<() => void>(() => undefined);
  const [remain, setRemain] = useState<number | null>(null); // 경고 중이면 남은 초

  useEffect(() => {
    if (!limit || limit <= 0) return;
    const warn = warnSeconds(limit);
    last.current = Date.now();
    lastTouch.current = Date.now();
    done.current = false;
    let stamp = 0;
    let warning = false;

    const touch = () => {
      lastTouch.current = Date.now();
      return client.request<unknown>('GET', '/api/v1/auth/me').catch(() => undefined);
    };
    const onActivity = () => {
      const now = Date.now();
      if (warning || done.current || now - stamp < 1000) return; // 경고 중에는 버튼으로만 연장
      stamp = now;
      last.current = now;
      // 서버 쪽 마지막 사용 시각이 너무 오래되면(요청 없이 조작만 한 경우) 미리 갱신
      if (now - lastTouch.current > (limit * 1000) / 4) void touch();
    };
    const tick = () => {
      if (done.current) return;
      const idle = (Date.now() - last.current) / 1000;
      if (idle >= limit) {
        done.current = true;
        warning = false;
        setRemain(null);
        void client
          .logout()
          .catch(() => undefined)
          .finally(() => client.markExpired());
        return;
      }
      if (idle >= limit - warn) {
        warning = true;
        setRemain(Math.ceil(limit - idle));
      } else {
        warning = false;
        setRemain(null);
      }
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') tick();
    };
    for (const ev of ACTIVITY_EVENTS) window.addEventListener(ev, onActivity, { passive: true });
    document.addEventListener('visibilitychange', onVisible);
    const timer = setInterval(tick, 1000);
    continueRef.current = () => {
      last.current = Date.now();
      warning = false;
      setRemain(null);
      void touch();
    };
    return () => {
      clearInterval(timer);
      for (const ev of ACTIVITY_EVENTS) window.removeEventListener(ev, onActivity);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [client, limit]);

  if (remain === null) return null;
  return (
    <Modal title={ko.login.idleTitle} onClose={() => undefined} closeDisabled>
      <p role="alert">{ko.login.idleBody(Math.floor(remain / 60), remain % 60)}</p>
      <Button variant="primary" data-autofocus="" onClick={() => continueRef.current()}>
        {ko.login.idleContinue}
      </Button>
    </Modal>
  );
}
