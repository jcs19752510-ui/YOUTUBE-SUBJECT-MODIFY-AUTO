import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApi } from '../api/context';
import type { Dashboard } from '../api/types';
import {
  Button,
  Callout,
  Card,
  Badge,
  PageHead,
  Progress,
  QueryView,
  ErrorPanel,
  useToast,
} from '../components';
import { ko } from '../i18n/ko';
import { jobTypeLabel } from '../lib/labels';
import { fmtDate, fmtNum } from '../lib/format';
import { GoogleCard } from './GoogleCard';
import { JobPanel } from './JobPanel';

const COUNT_LINK = {
  videos: '/videos',
  excluded: '/videos?excluded=true',
  suggested: '/videos?status=suggested',
  approved: '/videos?status=approved',
  queued: '/videos?status=queued',
  applied: '/videos?status=applied',
} as const;

function Todo({ d }: { d: Dashboard }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobFinished, setJobFinished] = useState(false);
  const sync = useMutation({
    mutationFn: () => api.syncVideos(),
    onSuccess: (job) => {
      setJobId(job.id);
      setJobFinished(false);
      toast.push('info', ko.home.syncStarted);
    },
  });
  const items: { key: string; text: string; to: string; cta: string }[] = [];
  if (d.counts.suggested > 0)
    items.push({
      key: 's',
      text: ko.home.todoReview(d.counts.suggested),
      to: '/videos?status=suggested',
      cta: ko.home.gotoReview,
    });
  if (d.counts.approved > 0)
    items.push({
      key: 'a',
      text: ko.home.todoBatch(d.counts.approved),
      to: '/batches',
      cta: ko.home.gotoBatch,
    });
  if (d.counts.queued > 0)
    items.push({
      key: 'q',
      text: ko.home.todoQueued(d.counts.queued),
      to: '/batches',
      cta: ko.home.gotoQueue,
    });

  return (
    <Card title={ko.home.todoTitle}>
      {d.counts.videos === 0 ? (
        <div className="stack">
          <p>{ko.home.todoNoVideos}</p>
          <div>
            <Button
              variant="primary"
              busy={sync.isPending || (jobId !== null && !jobFinished)}
              onClick={() => sync.mutate()}
            >
              {sync.isPending ? ko.home.syncing : ko.home.syncDemo}
            </Button>
          </div>
          {sync.isError && <ErrorPanel error={sync.error} />}
          {jobId && (
            <JobPanel
              jobId={jobId}
              label={ko.home.syncDemo}
              onError={() => setJobFinished(true)}
              onDone={() => {
                setJobFinished(true);
                void qc.invalidateQueries({ queryKey: ['dashboard'] });
                void qc.invalidateQueries({ queryKey: ['videos'] });
              }}
            />
          )}
        </div>
      ) : items.length === 0 ? (
        <p>
          {ko.home.todoNothing} <Link to="/videos">{ko.nav.videos}</Link>
        </p>
      ) : (
        <ul className="item-list">
          {items.map((i) => (
            <li key={i.key} className="row row--between">
              <span>{i.text}</span>
              <Link className="btn btn--primary btn--sm" to={i.to}>
                {i.cta}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function HomePage() {
  const api = useApi();
  const q = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api.dashboard(),
    refetchInterval: (query) => (query.state.data?.active_job ? 2000 : false),
  });
  return (
    <>
      <PageHead
        title={ko.home.title}
        subtitle={ko.home.subtitle}
        actions={
          <Button busy={q.isFetching && !q.isPending} onClick={() => void q.refetch()}>
            {q.isFetching && !q.isPending ? ko.home.refreshing : ko.home.refresh}
          </Button>
        }
      />
      <QueryView query={q} lines={6}>
        {(d) => {
          const pct = d.quota.limit > 0 ? (d.quota.used / d.quota.limit) * 100 : 0;
          return (
            <div className="stack">
              {d.active_job && (
                <Callout tone="info" role="status">
                  <p>
                    {ko.home.activeJob(
                      jobTypeLabel(d.active_job.type),
                      d.active_job.progress,
                      d.active_job.total,
                    )}
                  </p>
                </Callout>
              )}
              <Todo d={d} />
              <div className="grid-cards">
                <Card title={ko.home.todayTitle}>
                  <p className="stat">{ko.home.todayOf(d.today.applied, d.today.cap)}</p>
                  <Progress value={d.today.applied} max={d.today.cap} label={ko.home.todayTitle} />
                  <p className="muted">{ko.home.todayHint}</p>
                </Card>
                <Card title={ko.home.quotaTitle}>
                  <p className="stat">{ko.home.quotaRemain(d.quota.remaining)}</p>
                  <Progress value={d.quota.used} max={d.quota.limit} label={ko.home.quotaTitle} />
                  <p className="muted">
                    {ko.home.quotaOf(d.quota.used, d.quota.limit)}
                    <br />
                    {ko.home.quotaDate(d.quota.pt_date)}
                  </p>
                  {pct >= 80 && (
                    <Callout tone="warning" role="status">
                      <p>{ko.home.quotaWarn}</p>
                    </Callout>
                  )}
                </Card>
                <Card title={ko.home.queueTitle}>
                  {d.queue.pending_items > 0 ? (
                    <>
                      <p className="stat">{ko.home.queuePending(d.queue.pending_items)}</p>
                      <p className="muted">{ko.home.queueNext(fmtDate(d.queue.next_run_date))}</p>
                    </>
                  ) : (
                    <p>{ko.home.queueNone}</p>
                  )}
                  <Link to="/batches">{ko.nav.batches}</Link>
                </Card>
              </div>
              <div className="grid-cards">
                <GoogleCard />
                <Card title={ko.home.statusTitle}>
                  <ul className="item-list">
                    <li>
                      <Badge tone="warning" icon="●">
                        {d.google.mode === 'demo' ? ko.home.googleDemo : ko.home.googleConnected}
                      </Badge>
                    </li>
                    <li>
                      {d.google.connected ? ko.home.googleConnected : ko.home.googleDisconnected}
                    </li>
                    <li>{d.live_enabled ? ko.home.liveOn : ko.home.liveOff}</li>
                  </ul>
                </Card>
                <Card title={ko.home.countsTitle}>
                  <ul className="count-list">
                    {(Object.keys(ko.home.counts) as (keyof typeof ko.home.counts)[]).map((k) => (
                      <li key={k}>
                        <Link to={COUNT_LINK[k]}>{ko.home.counts[k]}</Link>
                        <strong>{fmtNum(d.counts[k])}</strong>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            </div>
          );
        }}
      </QueryView>
    </>
  );
}
