import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useApi } from '../api/context';
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorPanel,
  Field,
  PageHead,
  Pagination,
  QueryView,
  Skeleton,
  TableWrap,
  ValidationBadge,
} from '../components';
import { useIdempotency } from '../hooks/useIdempotency';
import { ko } from '../i18n/ko';
import { fmtDateTime } from '../lib/format';
import { batchStatusLabel, isBatchActive } from '../lib/labels';

export const MAX_BATCH = 50;

export function BatchesPage() {
  const api = useApi();
  const nav = useNavigate();
  const keys = useIdempotency();
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [note, setNote] = useState('');
  const [page, setPage] = useState(1);

  const approved = useQuery({
    queryKey: ['suggestions', 'approved'],
    queryFn: () => api.suggestions({ status: 'approved', page_size: 200 }),
  });
  const list = useQuery({
    queryKey: ['batches', page],
    queryFn: () => api.batches({ page, page_size: 20 }),
    refetchInterval: (q) =>
      q.state.data?.items.some((b) => isBatchActive(b.status)) ? 2000 : false,
  });

  const create = useMutation({
    mutationFn: () => {
      const ids = Array.from(picked).sort((a, b) => a - b);
      return api.createBatch(
        ids,
        note.trim() || undefined,
        keys.get(`${ids.join(',')}|${note.trim()}`),
      );
    },
    onSuccess: (r) => {
      keys.clear();
      nav(`/batches/${r.batch.id}`, { state: { precheck: r.precheck } });
    },
  });

  const items = approved.data?.items ?? [];
  const over = picked.size > MAX_BATCH;
  const toggle = (id: number) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const allPicked = items.length > 0 && items.every((s) => picked.has(s.id));
  const activeBatch = list.data?.items.find((b) => isBatchActive(b.status));

  return (
    <>
      <PageHead title={ko.batches.title} subtitle={ko.batches.subtitle} />
      <div className="stack">
        {activeBatch && (
          <Callout tone="info" role="status" title={ko.batches.runningBanner}>
            <Link to={`/batches/${activeBatch.id}`}>{ko.batches.batchTitle(activeBatch.id)}</Link>
          </Callout>
        )}
        <Card title={ko.batches.approvedTitle}>
          {approved.isPending ? (
            <Skeleton lines={4} />
          ) : approved.isError ? (
            <ErrorPanel error={approved.error} onRetry={() => void approved.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState
              title={ko.batches.approvedEmpty}
              action={<Link to="/videos">{ko.nav.videos}</Link>}
            >
              {ko.batches.approvedEmptyHint}
            </EmptyState>
          ) : (
            <div className="stack">
              <TableWrap label={ko.batches.approvedTitle}>
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">
                        <input
                          type="checkbox"
                          aria-label={ko.batches.selectAll}
                          checked={allPicked}
                          onChange={(e) =>
                            setPicked(
                              e.target.checked ? new Set(items.map((s) => s.id)) : new Set(),
                            )
                          }
                        />
                      </th>
                      <th scope="col">{ko.batches.colVideo}</th>
                      <th scope="col">{ko.batches.colChange}</th>
                      <th scope="col">{ko.batches.colApproval}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((s) => (
                      <tr key={s.id} aria-selected={picked.has(s.id)}>
                        <td>
                          <input
                            type="checkbox"
                            checked={picked.has(s.id)}
                            aria-label={ko.batches.selectOne(s.title)}
                            onChange={() => toggle(s.id)}
                          />
                        </td>
                        <td>
                          <Link to={`/videos/${encodeURIComponent(s.video_id)}`} className="mono">
                            {s.video_id}
                          </Link>
                        </td>
                        <td className="cell-title">
                          {s.title} <ValidationBadge result={s.validation_result} />
                        </td>
                        <td>
                          {s.approval ? (
                            <>
                              {s.approval.approver}
                              <div className="muted">{fmtDateTime(s.approval.expires_at)}</div>
                            </>
                          ) : (
                            '-'
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
              <p className="muted" aria-live="polite">
                {ko.videos.selectedCount(picked.size)} · {ko.batches.maxNote(MAX_BATCH)}
              </p>
              {over && <p className="field__error">{ko.batches.overMax(MAX_BATCH)}</p>}
              <Field label={ko.batches.noteLabel}>
                <input
                  className="input"
                  value={note}
                  maxLength={200}
                  onChange={(e) => setNote(e.target.value)}
                />
              </Field>
              {create.isError && <ErrorPanel error={create.error} />}
              <div>
                <Button
                  variant="primary"
                  busy={create.isPending}
                  disabled={picked.size === 0 || over}
                  onClick={() => create.mutate()}
                >
                  {create.isPending ? ko.batches.creating : ko.batches.createDraft}
                </Button>
              </div>
            </div>
          )}
        </Card>

        <section aria-labelledby="past-title" className="stack">
          <h2 id="past-title">{ko.batches.listTitle}</h2>
          <QueryView query={list} lines={3}>
            {(d) =>
              d.items.length === 0 ? (
                <p className="muted">{ko.batches.listEmpty}</p>
              ) : (
                <>
                  <TableWrap label={ko.batches.listTitle}>
                    <table className="table">
                      <thead>
                        <tr>
                          <th scope="col">{ko.batches.colId}</th>
                          <th scope="col">{ko.batches.colCreated}</th>
                          <th scope="col">{ko.batches.colBatchStatus}</th>
                          <th scope="col" className="num">
                            {ko.batches.colCount}
                          </th>
                          <th scope="col">
                            <span className="sr-only">{ko.batches.open}</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.items.map((b) => (
                          <tr key={b.id}>
                            <td>#{b.id}</td>
                            <td className="nowrap">{fmtDateTime(b.created_at)}</td>
                            <td>
                              <Badge
                                tone={
                                  isBatchActive(b.status)
                                    ? 'info'
                                    : b.status === 'completed' || b.status === 'done'
                                      ? 'success'
                                      : 'neutral'
                                }
                              >
                                {batchStatusLabel(b.status)}
                              </Badge>
                            </td>
                            <td className="num">
                              {b.items.length || Object.values(b.counts).reduce((a, c) => a + c, 0)}
                            </td>
                            <td>
                              <Link to={`/batches/${b.id}`}>
                                {ko.batches.open}
                                <span className="sr-only"> {ko.batches.batchTitle(b.id)}</span>
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </TableWrap>
                  <Pagination
                    page={d.page}
                    pageSize={d.page_size}
                    total={d.total}
                    onPage={setPage}
                  />
                </>
              )
            }
          </QueryView>
        </section>
      </div>
    </>
  );
}
