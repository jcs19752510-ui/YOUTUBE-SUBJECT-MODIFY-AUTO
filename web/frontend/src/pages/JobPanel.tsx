import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { ApiError } from '../api/client';
import { useApi } from '../api/context';
import type { Job } from '../api/types';
import { ErrorPanel, Progress } from '../components';
import { ko } from '../i18n/ko';
import { jobPhase } from '../lib/labels';

export const JOB_404_RETRIES = 3;
export const JOB_404_RETRY_MS = 500;

/** 작업(job) 진행을 1초마다 조회해 보여 주고, 끝나면 onDone 을 한 번 부른다. */
export function JobPanel({
  jobId,
  label,
  onDone,
  onError,
}: {
  jobId: string;
  label: string;
  onDone?: (job: Job) => void;
  /** 작업 상태를 읽지 못해 오류가 보일 때 한 번 알린다(호출자가 창을 닫을 수 있게 하기 위함) */
  onError?: () => void;
}) {
  const api = useApi();
  const q = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.job(jobId),
    // 방금 만든 작업이 아주 잠깐 "없음"(404)으로 보일 수 있어(서버가 응답 직후 저장을 마치는 경우) 짧게 몇 번 다시 확인한다. 계속 없으면 오류를 보여 준다.
    retry: (count, err) => err instanceof ApiError && err.status === 404 && count < JOB_404_RETRIES,
    retryDelay: JOB_404_RETRY_MS,
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

  const failedToRead = q.isError;
  useEffect(() => {
    if (failedToRead) onError?.();
  }, [failedToRead, onError]);

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
