import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApi } from '../api/context';
import type { Job, VideoListQuery, VideoSummary, WorkflowStatus } from '../api/types';
import {
  Badge,
  Button,
  EmptyState,
  ErrorPanel,
  Field,
  Modal,
  PageHead,
  Pagination,
  SortHeader,
  TableWrap,
  useToast,
} from '../components';
import { Skeleton } from '../components/Skeleton';
import { DateRangeFilter, useDateRange } from '../components/DateRangeFilter';
import { useSelection } from '../hooks/selection';
import { ko } from '../i18n/ko';
import { fmtDateTime, fmtDuration, fmtNum } from '../lib/format';
import { privacyLabel, workflowLabel, workflowTone } from '../lib/labels';
import { JobPanel } from './JobPanel';

/** 서버가 한 번에 받는 영상 수(API.md: 1~200개) */
export const MAX_GENERATE = 200;

export const STATUSES: WorkflowStatus[] = [
  'none',
  'suggested',
  'approved',
  'queued',
  'applied',
  'rolled_back',
];

function readParams(sp: URLSearchParams): Required<Omit<VideoListQuery, 'date_from' | 'date_to'>> {
  const num = (k: string, d: number) => {
    const n = Number(sp.get(k));
    return Number.isInteger(n) && n > 0 ? n : d;
  };
  const status = sp.get('status') ?? '';
  const excluded = sp.get('excluded') ?? '';
  const kind = sp.get('kind') ?? '';
  const order = sp.get('order');
  return {
    q: sp.get('q') ?? '',
    status: (STATUSES as string[]).includes(status) ? (status as WorkflowStatus) : '',
    excluded: excluded === 'true' || excluded === 'false' ? excluded : '',
    kind: kind === 'long' || kind === 'short' ? kind : '',
    sort: sp.get('sort') ?? 'last_change_at',
    order: order === 'asc' ? 'asc' : 'desc',
    page: num('page', 1),
    page_size: Math.min(num('page_size', 50), 200),
  };
}

export function VideosPage() {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const sel = useSelection();
  const [sp, setSp] = useSearchParams();
  const p = readParams(sp);
  const range = useDateRange();
  const [qInput, setQInput] = useState(p.q);
  const [genJob, setGenJob] = useState<{ id: string; count: number } | null>(null);
  const [genDone, setGenDone] = useState<Job | null>(null);
  const [genReadError, setGenReadError] = useState(false);

  const update = (patch: Record<string, string | number | null>, resetPage = true) => {
    const n = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '') n.delete(k);
      else n.set(k, String(v));
    }
    if (resetPage && !('page' in patch)) n.delete('page');
    setSp(n, { replace: true });
  };

  const query = useQuery({
    queryKey: ['videos', p, range.query],
    queryFn: () => api.videos({ ...p, ...range.query }),
    enabled: range.valid,
    placeholderData: (prev) => prev,
  });

  const gen = useMutation({
    mutationFn: (ids: string[]) => api.generateSuggestions(ids),
    onSuccess: (job, ids) => {
      setGenJob({ id: job.id, count: ids.length });
      setGenDone(null);
      setGenReadError(false);
    },
  });

  const items = query.data?.items ?? [];
  const selectable = items.filter((v) => !v.excluded);
  const allOnPage = selectable.length > 0 && selectable.every((v) => sel.has(v.video_id));
  const someOnPage = selectable.some((v) => sel.has(v.video_id));
  const headRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (headRef.current) headRef.current.indeterminate = someOnPage && !allOnPage;
  }, [someOnPage, allOnPage]);

  const toggleSort = (key: string) =>
    update(
      p.sort === key ? { order: p.order === 'asc' ? 'desc' : 'asc' } : { sort: key, order: 'asc' },
    );

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    update({ q: qInput.trim() });
  };
  const reset = () => {
    setQInput('');
    setSp(new URLSearchParams(), { replace: true });
  };
  const filtered = Boolean(p.q || p.status || p.excluded || p.kind);

  const closeGen = () => {
    if (genDone) {
      sel.clear();
      void qc.invalidateQueries({ queryKey: ['videos'] });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
    }
    setGenJob(null);
    gen.reset();
  };

  return (
    <>
      <PageHead title={ko.videos.title} subtitle={ko.videos.subtitle} />
      <form className="toolbar" role="search" onSubmit={onSearch}>
        <Field label={ko.videos.search} className="field--grow">
          <input
            className="input"
            type="search"
            value={qInput}
            placeholder={ko.videos.searchPlaceholder}
            onChange={(e) => setQInput(e.target.value)}
          />
        </Field>
        <Field label={ko.videos.filterStatus}>
          <select
            className="select"
            value={p.status}
            onChange={(e) => update({ status: e.target.value })}
          >
            <option value="">{ko.videos.filterAll}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {workflowLabel(s)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={ko.videos.filterKind}>
          <select
            name="kind-filter"
            className="select"
            value={p.kind}
            onChange={(e) => update({ kind: e.target.value })}
          >
            <option value="">{ko.videos.kindAll}</option>
            <option value="long">{ko.videos.kindLong}</option>
            <option value="short">{ko.videos.kindShort}</option>
          </select>
        </Field>
        <Field label={ko.videos.filterExcluded}>
          <select
            className="select"
            value={p.excluded}
            onChange={(e) => update({ excluded: e.target.value })}
          >
            <option value="">{ko.videos.excludedAll}</option>
            <option value="true">{ko.videos.excludedOnly}</option>
            <option value="false">{ko.videos.excludedHide}</option>
          </select>
        </Field>
        <Button type="submit" variant="primary">
          {ko.videos.searchButton}
        </Button>
        {filtered && <Button onClick={reset}>{ko.videos.reset}</Button>}
      </form>
      <DateRangeFilter
        range={range}
        basis="최근 변경 시각 기준"
        onChange={() => update({})}
      />

      {!range.valid ? null : query.isPending ? (
        <Skeleton lines={8} />
      ) : query.isError ? (
        <ErrorPanel error={query.error} onRetry={() => void query.refetch()} />
      ) : items.length === 0 ? (
        filtered || !range.isAll ? (
          <EmptyState
            title={ko.videos.emptyTitle}
            action={<Button onClick={reset}>{ko.videos.reset}</Button>}
          >
            {range.isAll ? ko.videos.emptyBody : ko.dateRange.none}
          </EmptyState>
        ) : (
          <EmptyState title={ko.videos.emptyFirstTitle} action={<Link to="/">{ko.nav.home}</Link>}>
            <EmptyFirstBody />
          </EmptyState>
        )
      ) : (
        <>
          {items.length > selectable.length && (
            <p className="muted" role="note">
              {ko.videos.excludedNotice(items.length - selectable.length, selectable.length)}
            </p>
          )}
          <TableWrap label={ko.videos.title}>
            <table className="table">
              <caption>{ko.videos.captionLine(query.data?.total ?? 0)}</caption>
              <thead>
                <tr>
                  <th scope="col">
                    <label className="check-hit">
                      <input
                        ref={headRef}
                        id="videos-select-page"
                        name="videos-select-page"
                        type="checkbox"
                        aria-label={ko.videos.selectPage}
                        checked={allOnPage}
                        disabled={selectable.length === 0}
                        onChange={(e) =>
                          sel.setMany(
                            selectable.map((v) => ({ id: v.video_id, title: v.title })),
                            e.target.checked,
                          )
                        }
                      />
                    </label>
                  </th>
                  <SortHeader
                    label={ko.videos.colTitle}
                    active={p.sort === 'title'}
                    order={p.order}
                    onSort={() => toggleSort('title')}
                  />
                  <th scope="col">{ko.videos.colStatus}</th>
                  <th scope="col">{ko.videos.colKind}</th>
                  <SortHeader
                    label={ko.videos.sortKeys.duration_sec ?? ''}
                    active={p.sort === 'duration_sec'}
                    order={p.order}
                    onSort={() => toggleSort('duration_sec')}
                  />
                  <th scope="col" className="num">
                    {ko.videos.colSuggestions}
                  </th>
                  <SortHeader
                    label={ko.videos.colViews}
                    active={p.sort === 'views'}
                    order={p.order}
                    onSort={() => toggleSort('views')}
                  />
                  <SortHeader
                    label={ko.videos.colLastChange}
                    active={p.sort === 'last_change_at'}
                    order={p.order}
                    onSort={() => toggleSort('last_change_at')}
                  />
                </tr>
              </thead>
              <tbody>
                {items.map((v) => (
                  <Row
                    key={v.video_id}
                    v={v}
                    selected={sel.has(v.video_id)}
                    onToggle={() => sel.toggle(v.video_id, v.title)}
                  />
                ))}
              </tbody>
            </table>
          </TableWrap>
          <Pagination
            page={query.data?.page ?? p.page}
            pageSize={query.data?.page_size ?? p.page_size}
            total={query.data?.total ?? 0}
            onPage={(n) => update({ page: n }, false)}
            onPageSize={(n) => update({ page_size: n })}
          />
        </>
      )}

      {sel.ids.length > 0 && (
        <div
          className="selection-bar"
          role="region"
          aria-label={ko.videos.selectedCount(sel.ids.length)}
        >
          <strong aria-live="polite">{ko.videos.selectedCount(sel.ids.length)}</strong>
          {sel.ids.length > MAX_GENERATE && (
            <span className="field__error" role="alert">
              {ko.videos.generateOver(MAX_GENERATE)}
            </span>
          )}
          <div className="row">
            <Button onClick={sel.clear}>{ko.videos.clearSelection}</Button>
            <Button
              variant="primary"
              busy={gen.isPending}
              disabled={sel.ids.length > MAX_GENERATE}
              onClick={() => gen.mutate(sel.ids)}
            >
              {gen.isPending ? ko.videos.generating : ko.videos.generate}
            </Button>
          </div>
        </div>
      )}
      {gen.isError && !genJob && (
        <Modal
          title={ko.videos.generateTitle}
          onClose={() => gen.reset()}
          footer={<Button onClick={() => gen.reset()}>{ko.app.close}</Button>}
        >
          <ErrorPanel error={gen.error} />
        </Modal>
      )}
      {genJob && (
        <Modal
          title={ko.videos.generateTitle}
          onClose={closeGen}
          closeDisabled={!genDone && !genReadError}
          footer={
            <Button variant="primary" disabled={!genDone && !genReadError} onClick={closeGen}>
              {ko.app.close}
            </Button>
          }
        >
          <JobPanel
            jobId={genJob.id}
            label={ko.videos.generateTitle}
            onError={() => setGenReadError(true)}
            onDone={(j) => {
              setGenDone(j);
              toast.push(
                j.status === 'succeeded' ? 'success' : 'error',
                j.status === 'succeeded'
                  ? ko.videos.generateDone(genJob.count)
                  : ko.videos.generateFail,
              );
            }}
          />
        </Modal>
      )}
    </>
  );
}

function Row({
  v,
  selected,
  onToggle,
}: {
  v: VideoSummary;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <tr aria-selected={selected}>
      <td>
        <label className="check-hit">
          <input
            id={`video-select-${v.video_id}`}
            name="video-select"
            type="checkbox"
            checked={selected}
            disabled={v.excluded}
            title={v.excluded ? ko.videos.excludedWhy : undefined}
            aria-label={ko.videos.selectOne(v.title)}
            onChange={onToggle}
          />
        </label>
      </td>
      <td className="cell-title">
        <Link to={`/videos/${encodeURIComponent(v.video_id)}`}>{v.title}</Link>
        <div className="muted mono">{v.video_id}</div>
        {v.excluded && (
          <div>
            <Badge tone="warning" icon="⊘">
              {ko.videos.excludedBadge}
            </Badge>{' '}
            <span className="muted">{v.exclusion_reasons.join(', ')}</span>
          </div>
        )}
      </td>
      <td>
        <Badge tone={workflowTone(v.workflow_status)}>{workflowLabel(v.workflow_status)}</Badge>
      </td>
      <td>
        {v.is_short ? (
          <Badge tone="info">{ko.videos.kindShort}</Badge>
        ) : v.duration_sec === null ? (
          '-'
        ) : (
          <Badge>{ko.videos.kindLong}</Badge>
        )}
      </td>
      <td>
        <span className="nowrap">{fmtDuration(v.duration_sec)}</span>
        <div className="muted">
          {privacyLabel(v.privacy_status)}
          {v.is_short ? ` · ${ko.videos.shortBadge}` : ''}
        </div>
      </td>
      <td className="num">{fmtNum(v.suggestion_count)}</td>
      <td className="num">{fmtNum(v.views)}</td>
      <td className="nowrap">{fmtDateTime(v.last_change_at)}</td>
    </tr>
  );
}

/** 영상이 하나도 없을 때의 안내. 구글 연결·실제 모드면 데모 문구 대신 내 채널 불러오기를 안내한다(상태를 못 읽으면 기존 데모 문구). */
function EmptyFirstBody() {
  const api = useApi();
  const q = useQuery({ queryKey: ['dashboard'], queryFn: () => api.dashboard() });
  const live = q.data ? q.data.google.connected || q.data.mode === 'live' : false;
  return <>{live ? ko.videos.emptyFirstBodyLive : ko.videos.emptyFirstBody}</>;
}
