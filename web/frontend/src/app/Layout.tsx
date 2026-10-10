import { useEffect, useRef } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useApiClient, useConnection } from '../api/context';
import { Button, Callout, useToast } from '../components';
import { describeError } from '../components/ErrorPanel';
import { ko } from '../i18n/ko';

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
    document.querySelector<HTMLElement>('[data-page-title]')?.focus();
  }, [pathname]);

  const online = conn.state === 'online';
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
        <span className="demo-badge">
          <span aria-hidden="true">●</span> {ko.app.demoBadge}
        </span>
        <div className="row">
          <span className="conn" role="status">
            <span aria-hidden="true">{online ? '●' : '○'}</span>
            {online ? ko.conn.online : ko.conn.offline}
          </span>
          <Button size="sm" onClick={logout}>
            {ko.conn.logout}
          </Button>
        </div>
      </header>
      <main className="main" id="main" tabIndex={-1}>
        {!online && (
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
        <Outlet />
      </main>
    </div>
  );
}
