import { useEffect, useRef } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useApi, useApiClient, useConnection } from '../api/context';
import { Button, Callout, useToast } from '../components';
import { describeError } from '../components/ErrorPanel';
import { ko } from '../i18n/ko';
import { ErrorBoundary } from './ErrorBoundary';

/** 상단 모드 띠: 서버가 알려 준 실제 상태(구글 연결·실제 수정 가능 여부)를 그대로 보여 준다. 상태를 모르면 가장 안전한 데모 문구. */
function ModeBadge() {
  const api = useApi();
  const d = useQuery({ queryKey: ['dashboard'], queryFn: () => api.dashboard() }).data;
  if (d?.mode === 'live') {
    return (
      <span className="demo-badge" role="status">
        <span aria-hidden="true">●</span> {ko.app.liveBadge}
      </span>
    );
  }
  if (d?.google.connected) {
    return (
      <span className="demo-badge">
        <span aria-hidden="true">●</span> {ko.app.readBadge}
      </span>
    );
  }
  return (
    <span className="demo-badge">
      <span aria-hidden="true">●</span> {ko.app.demoBadge}
    </span>
  );
}

const NAV = [
  { to: '/', label: ko.nav.home, end: true },
  { to: '/videos', label: ko.nav.videos },
  { to: '/batches', label: ko.nav.batches },
  { to: '/history', label: ko.nav.history },
  { to: '/reports', label: ko.nav.reports },
  { to: '/settings', label: ko.nav.settings },
];

export function Layout() {
  const conn = useConnection();
  const client = useApiClient();
  const { pathname } = useLocation();
  const first = useRef(true);
  const toast = useToast();
  const logout = () =>
    client
      .logout()
      .catch((e: unknown) =>
        toast.push('error', describeError(e).detail || describeError(e).title),
      );

  // 화면을 옮기면 제목으로 포커스를 보내 스크린리더·키보드 사용자가 위치를 잃지 않게 한다
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    toast.clearTransient();
    document.querySelector<HTMLElement>('[data-page-title]')?.focus();
  }, [pathname, toast]);

  const online = conn.state === 'online';
  const offline = conn.state === 'offline' || conn.state === 'error';
  const statusLabel = online ? ko.conn.online : offline ? ko.conn.offline : ko.conn.sessionNeeded;
  return (
    <div className="app">
      <a
        className="skip-link"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById('main')?.focus();
        }}
      >
        {ko.app.skip}
      </a>
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          {ko.app.name}
          <small>{ko.app.tagline}</small>
        </NavLink>
        <nav aria-label={ko.app.mainNav}>
          <ul className="nav">
            {NAV.map((n) => (
              <li key={n.to}>
                <NavLink to={n.to} end={n.end}>
                  {n.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <header className="topbar">
        <ModeBadge />
        <div className="row">
          <span className="conn" role="status">
            <span aria-hidden="true">{online ? '●' : '○'}</span>
            {statusLabel}
          </span>
          <Button size="sm" onClick={logout}>
            {ko.conn.logout}
          </Button>
        </div>
      </header>
      <main className="main" id="main" tabIndex={-1}>
        {offline && (
          <div className="stack">
            <Callout tone="danger" role="alert" title={ko.conn.offlineTitle}>
              <p>{ko.conn.offlineBanner}</p>
              <Button size="sm" onClick={() => void client.bootstrap()}>
                {ko.conn.reconnect}
              </Button>
            </Callout>
            <div />
          </div>
        )}
        <ErrorBoundary resetKey={pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
      <footer className="legal-footer" aria-label={ko.legal.footerLabel}>
        <p>{ko.legal.disclaimer}</p>
        <p>{ko.legal.aiNotice}</p>
      </footer>
    </div>
  );
}
