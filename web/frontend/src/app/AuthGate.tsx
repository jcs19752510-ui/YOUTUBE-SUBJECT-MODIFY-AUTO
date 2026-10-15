import { useEffect, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useApiClient, useConnection } from '../api/context';
import { Button, Card, Modal, Skeleton } from '../components';
import { describeError } from '../components/ErrorPanel';
import { ErrorPanel } from '../components/ErrorPanel';
import { ko } from '../i18n/ko';
import { IdleLogout } from './IdleLogout';
import { LoginForm } from './LoginForm';
import { PinForm } from './PinForm';

function Center({ children }: { children: ReactNode }) {
  return (
    <main className="fullscreen-center">
      <Card>{children}</Card>
    </main>
  );
}

/** 앱 시작 시 세션을 확인·발급하고, 연결 상태에 따라 화면을 고른다. 한 번 연결된 뒤에는 화면을 내리지 않고 오버레이로만 알린다. */
export function AuthGate({ children }: { children: ReactNode }) {
  const client = useApiClient();
  const conn = useConnection();
  const qc = useQueryClient();
  const [everOnline, setEverOnline] = useState(false);

  useEffect(() => {
    void client.bootstrap();
  }, [client]);
  if (conn.state === 'online' && !everOnline) setEverOnline(true);

  const needLogin = conn.state === 'login_required';
  useEffect(() => {
    // 로그인 화면이 뜨면 이전 사용자의 데이터가 캐시에 남지 않게 지운다
    if (needLogin) qc.clear();
  }, [needLogin, qc]);

  if (conn.state === 'online') {
    return (
      <>
        {children}
        <IdleLogout />
      </>
    );
  }

  if (needLogin) {
    return (
      <Center>
        <h1>{ko.login.title}</h1>
        <p>{ko.login.body}</p>
        <LoginForm expired={conn.expired} onDone={() => void qc.invalidateQueries()} />
      </Center>
    );
  }

  if (everOnline) {
    if (conn.state === 'pin_required') {
      return (
        <>
          {children}
          <Modal title={ko.conn.pinExpiredTitle} onClose={() => undefined} closeDisabled>
            <p>{ko.conn.pinExpiredBody}</p>
            <PinForm onDone={() => void qc.invalidateQueries()} />
          </Modal>
        </>
      );
    }
    if (conn.state === 'loggedout') {
      return (
        <Center>
          <h1>{ko.conn.loggedOutTitle}</h1>
          <p>{ko.conn.loggedOutBody}</p>
          <Button
            variant="primary"
            onClick={() => void client.bootstrap().then(() => qc.invalidateQueries())}
          >
            {ko.conn.reconnect}
          </Button>
        </Center>
      );
    }
    // offline/error: 화면은 유지하고 상단 배너가 알린다
    return <>{children}</>;
  }

  if (conn.state === 'starting') {
    return (
      <Center>
        <Skeleton lines={3} />
      </Center>
    );
  }
  if (conn.state === 'pin_required') {
    return (
      <Center>
        <h1>{ko.conn.pinTitle}</h1>
        <p>{ko.conn.pinBody}</p>
        <PinForm />
      </Center>
    );
  }
  if (conn.state === 'loggedout') {
    return (
      <Center>
        <h1>{ko.conn.loggedOutTitle}</h1>
        <p>{ko.conn.loggedOutBody}</p>
        <Button variant="primary" onClick={() => void client.bootstrap()}>
          {ko.conn.reconnect}
        </Button>
      </Center>
    );
  }
  const v = describeError(conn.error);
  return (
    <Center>
      <h1>{conn.state === 'offline' ? ko.conn.offlineTitle : ko.conn.startErrorTitle}</h1>
      {conn.error ? <ErrorPanel error={conn.error} /> : <p>{v.detail}</p>}
      <p />
      <Button variant="primary" onClick={() => void client.bootstrap()}>
        {ko.conn.reconnect}
      </Button>
    </Center>
  );
}
