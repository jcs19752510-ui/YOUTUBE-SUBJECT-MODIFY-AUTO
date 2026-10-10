import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { useApi } from '../api/context';
import type { Job } from '../api/types';
import { ErrorPanel, Progress } from '../components';
import { ko } from '../i18n/ko';
import { jobPhase } from '../lib/labels';

/** 작업(job) 진행을 1초마다 조회해 보여 주고, 끝나면 onDone 을 한 번 부른다. */
export function JobPanel({
  jobId,
  label,
  onDone,
}: {
  jobId: string;
  label: string;
  onDone?: (job: Job) => void;
}) {
  const api = useApi();
  const q = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.job(jobId),
    refetchInterval: (query) => {
      const j = query.state.data;
      return j && jobPhase(j) !== 'active' ? false : 1000;
    },
  });
  const job = q.data;
  const notified = useRef(false);
  useEffect(() => {
    if (job && jobPhase(job) !== 'active' && !notified.current) {
      notified.current = true;
      onDone?.(job);
    }
  }, [job, onDone]);

  if (q.isError) return <ErrorPanel error={q.error} onRetry={() => void q.refetch()} />;
  if (!job) return <p aria-live="polite">{ko.app.loading}</p>;
  const phase = jobPhase(job);
  return (
    <div className="stack">
      <Progress value={job.progress} max={job.total} label={label} />
      <p aria-live="polite">
        {ko.videos.generateProgress(job.progress, job.total)} ·{' '}
        {ko.jobStatus[job.status] ?? job.status}
      </p>
      {phase === 'failed' && job.error && <p className="field__error">{job.error}</p>}
    </div>
  );
}
