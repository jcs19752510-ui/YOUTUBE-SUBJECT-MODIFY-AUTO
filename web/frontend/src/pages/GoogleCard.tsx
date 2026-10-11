import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useApi } from '../api/context';
import { Button, Callout, Card, ErrorPanel, useToast } from '../components';
import { ko } from '../i18n/ko';
import { navigateTo } from '../lib/navigate';

/** 구글(유튜브) 연결 카드: 연결·해제·내 영상 불러오기. 읽기 전용이며 제목은 바뀌지 않는다. */
export function GoogleCard() {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const status = useQuery({ queryKey: ['google'], queryFn: () => api.google() });
  const connect = useMutation({
    mutationFn: () => api.googleConnect(),
    onSuccess: (r) => navigateTo(r.auth_url),
  });
  const connectWrite = useMutation({
    mutationFn: () => api.googleConnectWrite(),
    onSuccess: (r) => navigateTo(r.auth_url),
  });
  const disconnect = useMutation({
    mutationFn: () => api.googleDisconnect(),
    onSuccess: () => {
      setAsking(false);
      toast.push('success', ko.google.disconnected);
      void qc.invalidateQueries({ queryKey: ['google'] });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
  const sync = useMutation({
    mutationFn: () => api.syncVideos(),
    onSuccess: () => {
      toast.push('info', ko.google.syncStarted);
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
  const g = status.data;
  return (
    <Card title={ko.google.title}>
      {status.isPending && <p className="muted">{ko.google.checking}</p>}
      {status.isError && <p className="muted">{ko.google.checkFail}</p>}
      {g && (
        <>
          {g.last_error && (
            <Callout tone="warning" role="alert">
              <p>
                <strong>{ko.google.errorTitle}</strong>
              </p>
              <p>{g.last_error}</p>
              {g.last_error.includes('데모') && <p>{ko.google.resetHint}</p>}
            </Callout>
          )}
          <p>{g.message}</p>
          {g.client_ready && !g.write_connected && !g.live_write_ready && (
            <p className="muted">{ko.google.readOnly}</p>
          )}
          {!g.client_ready && <p className="muted">{ko.google.needFile}</p>}
          <div className="row">
            {g.client_ready && !g.connected && (
              <Button
                variant="primary"
                disabled={connect.isPending}
                onClick={() => connect.mutate()}
              >
                {connect.isPending ? ko.google.connecting : ko.google.connect}
              </Button>
            )}
            {g.connected && (
              <Button variant="primary" disabled={sync.isPending} onClick={() => sync.mutate()}>
                {ko.google.syncReal}
              </Button>
            )}
            {g.connected && !asking && (
              <Button onClick={() => setAsking(true)}>{ko.google.disconnect}</Button>
            )}
          </div>
          {(g.connected || g.write_connected) && (
            <div>
              <h3>{ko.google.writeTitle}</h3>
              {g.live_write_ready ? (
                <Callout tone="warning" role="alert">
                  <p>
                    <strong>{ko.google.liveWarnTitle}</strong>
                  </p>
                  <p>{ko.google.liveWarn(g.live_allowed_count ?? 0)}</p>
                </Callout>
              ) : g.write_connected ? (
                <>
                  <p>{ko.google.writeConnected}</p>
                  <p className="muted">
                    {ko.google.writeNotReady(
                      g.live_write_enabled ?? false,
                      g.live_allowed_count ?? 0,
                    )}
                  </p>
                </>
              ) : (
                <>
                  <p className="muted">{ko.google.writeExplain}</p>
                  <Button disabled={connectWrite.isPending} onClick={() => connectWrite.mutate()}>
                    {ko.google.writeConnect}
                  </Button>
                </>
              )}
            </div>
          )}
          {g.connected && asking && (
            <Callout tone="warning" role="alert">
              <p>{ko.google.disconnectAsk}</p>
              <div className="row">
                <Button
                  variant="danger"
                  disabled={disconnect.isPending}
                  onClick={() => disconnect.mutate()}
                >
                  {ko.google.disconnectYes}
                </Button>
                <Button onClick={() => setAsking(false)}>{ko.google.disconnectNo}</Button>
              </div>
            </Callout>
          )}
        </>
      )}
      {connect.isError && <ErrorPanel error={connect.error} />}
      {connectWrite.isError && <ErrorPanel error={connectWrite.error} />}
      {sync.isError && <ErrorPanel error={sync.error} />}
      {disconnect.isError && <ErrorPanel error={disconnect.error} />}
    </Card>
  );
}
