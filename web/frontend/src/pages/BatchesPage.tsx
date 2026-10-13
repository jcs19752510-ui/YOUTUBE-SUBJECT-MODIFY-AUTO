import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
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
import { batchStatusText, isBatchActive } from '../lib/labels';
import { DiscardDraftButton } from './DiscardDraft';

export const MAX_BATCH = 50;

export function BatchesPage() {
  const api = useApi();
  const nav = useNavigate();
  const qc = useQueryClient();
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

  // 초안 배치에 이미 담긴 제안은 새 배치에 담을 수 없다. 어느 초안에 있는지 보여 주려고 초안 상세를 읽는다.
  const draftList = useQuery({
    queryKey: ['batches', 'drafts'],
    queryFn: () => api.batches({ page: 1, page_size: 200 }),
  });
  const draftIds = (draftList.data?.items ?? [])
    .filter((b) => b.status === 'draft')
    .map((b) => b.id);
  const draftDetails = useQueries({
    queries: draftIds.map((id) => ({ queryKey: ['batch', id], queryFn: () => api.batch(id) })),
  });
  const inDraft = new Map<number, number>();
  draftDetails.forEach((q) => {
    if (q.data?.status !== 'draft') return;
    for (const it of q.data.items) {
      if (it.status === 'pending') inDraft.set(it.suggestion_id, q.data.id);
    }
  });

  const create = useMutation({
    mutationFn: () => {
      const ids = chosen.map((x) => x.id).sort((a, b) => a - b);
      return api.createBatch(
        ids,
        note.trim() || undefined,
        keys.get(`${ids.join(',')}|${note.trim()}`),
      );
    },
    onSuccess: (r) => {
      keys.clear();
      // 초안에 담긴 제안이 승인 목록·초안 목록에 바로 반영되도록(되돌아왔을 때 낡은 목록을 보지 않게)
      void qc.invalidateQueries({ queryKey: ['batches'] });
      void qc.invalidateQueries({ queryKey: ['suggestions'] });
      nav(`/batches/${r.batch.id}`, { state: { precheck: r.precheck } });
    },
  });

  const items = approved.data?.items ?? [];
  // 목록에서 사라진 항목(승인 만료·다른 배치에 담김)을 이전에 골랐더라도 보내지 않는다
  const chosen = items.filter((x) => picked.has(x.id) && !inDraft.has(x.id));
  const over = chosen.length > MAX_BATCH;
  const toggle = (id: number) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const selectable = items.filter((s) => !inDraft.has(s.id));
  const allPicked = selectable.length > 0 && selectable.every((s) => picked.has(s.id));
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
                        <label className="check-hit">
                          <input
                            id="batches-select-all"
                            name="batches-select-all"
                            type="checkbox"
                            aria-label={ko.batches.selectAll}
                            checked={allPicked}
                            disabled={selectable.length === 0}
                            onChange={(e) =>
                              setPicked(
                                e.target.checked ? new Set(selectable.map((s) => s.id)) : new Set(),
                              )
                            }
                          />
                        </label>
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
                          <label className="check-hit">
                            <input
                              id={`batch-pick-${s.id}`}
                              name="batch-pick"
                              type="checkbox"
                              checked={picked.has(s.id) && !inDraft.has(s.id)}
                              disabled={inDraft.has(s.id)}
                              aria-label={ko.batches.selectOne(s.title)}
                              onChange={() => toggle(s.id)}
                            />
                          </label>
                        </td>
                        <td>
                          <Link to={`/videos/${encodeURIComponent(s.video_id)}`} className="mono">
                            {s.video_id}
                          </Link>
                        </td>
                        <td className="cell-title">
                          {s.title} <ValidationBadge result={s.validation_result} />
                          {inDraft.has(s.id) && (
                            <p className="field__error">
                              {ko.batches.inDraft(inDraft.get(s.id) ?? 0)}{' '}
                              <Link to={`/batches/${inDraft.get(s.id)}`}>
                                {ko.batches.inDraftOpen(inDraft.get(s.id) ?? 0)}
                              </Link>
                            </p>
                          )}
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
                {ko.videos.selectedCount(chosen.length)} · {ko.batches.maxNote(MAX_BATCH)}
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
                  disabled={chosen.length === 0 || over}
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
                  <TableWrap label={ko.batches.listTableLabel}>
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
                                {batchStatusText(b)}
                              </Badge>
                            </td>
                            <td className="num">
                              {b.items.length || Object.values(b.counts).reduce((a, c) => a + c, 0)}
                            </td>
                            <td>
                              <div className="row">
                                <Link to={`/batches/${b.id}`}>
                                  {ko.batches.open}
                                  <span className="sr-only"> {ko.batches.batchTitle(b.id)}</span>
                                </Link>
                                {b.status === 'draft' && (
                                  <DiscardDraftButton batchId={b.id} size="sm" />
                                )}
                              </div>
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
