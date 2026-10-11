import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { useApi } from '../api/context';
import { ApiError } from '../api/client';
import type { Batch, Precheck } from '../api/types';
import {
  Badge,
  Button,
  Callout,
  Card,
  ConfirmPhrase,
  EmptyState,
  ErrorPanel,
  Modal,
  PageHead,
  Progress,
  QueryView,
  TableWrap,
  useToast,
} from '../components';
import { useIdempotency } from '../hooks/useIdempotency';
import { ko } from '../i18n/ko';
import { fmtDate, fmtDateTime, fmtNum } from '../lib/format';
import { batchStatusText, isBatchActive, itemStatusLabel, itemTone } from '../lib/labels';
import { DiscardDraftButton } from './DiscardDraft';

function isPrecheck(v: unknown): v is Precheck {
  return typeof v === 'object' && v !== null && 'confirm_text' in v && 'item_count' in v;
}

const BLOCKED_LOOKUP_MAX = 20;

/** 제외된 항목마다 영상 제목을 보여 준다. 서버가 video_title 을 주면 그것을, 아니면 제안 목록→영상 상세에서 찾는다. */
function BlockedList({ blocked }: { blocked: Precheck['blocked'] }) {
  const api = useApi();
  const sug = useQuery({
    queryKey: ['suggestions', 'approved'],
    queryFn: () => api.suggestions({ status: 'approved', page_size: 200 }),
  });
  const videoIdOf = (b: Precheck['blocked'][number]) =>
    b.video_id ?? sug.data?.items.find((x) => x.id === b.suggestion_id)?.video_id;
  const vids = useQueries({
    queries: blocked.slice(0, BLOCKED_LOOKUP_MAX).map((b) => {
      const vid = videoIdOf(b);
      return {
        queryKey: ['video', vid],
        queryFn: () => api.video(vid ?? ''),
        enabled: Boolean(vid) && !b.video_title,
      };
    }),
  });
  return (
    <ul>
      {blocked.map((b, i) => {
        const vid = videoIdOf(b);
        const name = b.video_title ?? vids[i]?.data?.title;
        return (
          <li key={b.suggestion_id}>
            {name && vid ? (
              <>
                <Link to={`/videos/${encodeURIComponent(vid)}`}>{name}</Link>
                {` (${ko.batches.pc.blockedSuggestion(b.suggestion_id)}): ${b.reason}`}
              </>
            ) : (
              ko.batches.pc.blockedLine(b.suggestion_id, b.reason)
            )}
          </li>
        );
      })}
    </ul>
  );
}

function PrecheckView({ pc }: { pc: Precheck }) {
  const t = ko.batches.pc;
  return (
    <Card title={ko.batches.precheckTitle}>
      <p className="muted">{ko.batches.precheckNote}</p>
      <div className="grid-cards">
        <div>
          <p className="muted">{t.items}</p>
          <p className="stat">{t.itemsVal(pc.item_count)}</p>
        </div>
        <div>
          <p className="muted">{t.units}</p>
          <p className="stat">{t.unitsVal(pc.estimated_units)}</p>
        </div>
        <div>
          <p className="muted">{t.cap}</p>
          <p className="stat">{t.capVal(pc.daily_cap)}</p>
        </div>
        <div>
          <p className="muted">{t.quota}</p>
          <p className="stat">{t.unitsVal(pc.quota_remaining_units)}</p>
        </div>
      </div>
      <h3>{t.schedule}</h3>
      {pc.schedule.length === 0 ? (
        <p className="muted">-</p>
      ) : (
        <TableWrap label={t.schedule}>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t.scheduleDay}</th>
                <th scope="col" className="num">
                  {t.scheduleCount}
                </th>
              </tr>
            </thead>
            <tbody>
              {pc.schedule.map((s) => (
                <tr key={s.date}>
                  <td>{fmtDate(s.date)}</td>
                  <td className="num">{t.itemsVal(s.count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
      <p className="muted">{t.scheduleNote}</p>
      <div className="two-col">
        <div>
          <h3>{t.warnings}</h3>
          {pc.warnings.length === 0 ? (
            <Badge tone="success" icon="✓">
              {t.noWarnings}
            </Badge>
          ) : (
            <Callout tone="warning">
              <ul>
                {pc.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </Callout>
          )}
        </div>
        <div>
          <h3>{t.blocked}</h3>
          {pc.blocked.length === 0 ? (
            <Badge tone="success" icon="✓">
              {t.noBlocked}
            </Badge>
          ) : (
            <Callout tone="danger">
              <BlockedList blocked={pc.blocked} />
            </Callout>
          )}
        </div>
      </div>
      <div className="legal-note muted">
        <p>{ko.legal.aiLimit}</p>
        <p>{pc.notice ?? ko.legal.disclaimer}</p>
      </div>
    </Card>
  );
}

function ItemsTable({ batch }: { batch: Batch }) {
  return (
    <Card title={ko.batches.itemsTitle}>
      <TableWrap label={ko.batches.itemsTitle}>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">{ko.batches.colSeq}</th>
              <th scope="col">{ko.batches.colVideo}</th>
              <th scope="col">{ko.batches.colChange}</th>
              <th scope="col">{ko.batches.colDate}</th>
              <th scope="col">{ko.batches.colStatus}</th>
            </tr>
          </thead>
          <tbody>
            {batch.items.map((it) => (
              <tr key={it.id}>
                <td>{it.seq}</td>
                <td className="cell-title">
                  <Link to={`/videos/${encodeURIComponent(it.video_id)}`}>{it.video_title}</Link>
                  <div className="muted mono">{it.video_id}</div>
                </td>
                <td>
                  <div className="muted">{it.previous_title}</div>
                  <div aria-hidden="true">↓</div>
                  <strong>{it.new_title}</strong>
                </td>
                <td className="nowrap">{fmtDate(it.scheduled_date)}</td>
                <td>
                  <Badge tone={itemTone(it.status)}>{itemStatusLabel(it.status)}</Badge>
                  {it.skip_reason && <div className="muted">{it.skip_reason}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </Card>
  );
}

function Detail({ batch, pcFromNav }: { batch: Batch; pcFromNav: Precheck | null }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const keys = useIdempotency();
  const [phrase, setPhrase] = useState('');
  const [stopOpen, setStopOpen] = useState(false);
  const [abAck, setAbAck] = useState(false);

  const pc = pcFromNav ?? batch.precheck ?? null;
  const draft = batch.status === 'draft';
  const active = isBatchActive(batch.status);
  const pendingCount = batch.items.length;
  const expected = pc?.confirm_text ?? ko.batches.pc.confirmFallback(pendingCount);
  const total = Object.values(batch.counts).reduce((a, c) => a + c, 0) || batch.items.length;
  const doneCount =
    batch.counts.success + batch.counts.failed + batch.counts.skipped + batch.counts.cancelled;
  const blockedAll = pc ? pc.item_count === 0 : pendingCount === 0;
  const discarded = batch.status === 'cancelled' && !batch.executed_at;

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['batch', batch.id] });
    void qc.invalidateQueries({ queryKey: ['batches'] });
    void qc.invalidateQueries({ queryKey: ['dashboard'] });
    void qc.invalidateQueries({ queryKey: ['suggestions'] });
  };
  const execute = useMutation({
    mutationFn: () => api.executeBatch(batch.id, phrase, keys.get(`${batch.id}|${phrase}`)),
    onSuccess: (r) => {
      keys.clear();
      qc.setQueryData(['batch', batch.id], r.batch);
      toast.push('success', ko.batches.executedToast);
      refresh();
    },
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelBatch(batch.id),
    onSuccess: (b) => {
      qc.setQueryData(['batch', batch.id], b);
      setStopOpen(false);
      toast.push('success', ko.batches.stoppedToast);
      refresh();
    },
  });

  return (
    <div className="stack">
      <Card>
        <div className="row row--between">
          <div className="row">
            <Badge
              tone={
                active
                  ? 'info'
                  : batch.status === 'completed' || batch.status === 'done'
                    ? 'success'
                    : 'neutral'
              }
            >
              {batchStatusText(batch)}
            </Badge>
            <span className="muted">{fmtDateTime(batch.created_at)}</span>
            {batch.note && <span>{batch.note}</span>}
          </div>
          {draft && <DiscardDraftButton batchId={batch.id} />}
        </div>
      </Card>

      {draft && pc && <PrecheckView pc={pc} />}
      {draft && !pc && (
        <Callout tone="warning" title={ko.batches.draftLostTitle}>
          <p>{ko.batches.draftLostBody}</p>
        </Callout>
      )}

      {batch.items.length > 0 && <ItemsTable batch={batch} />}

      {draft && (
        <Card title={ko.batches.confirmTitle}>
          {blockedAll ? (
            <Callout tone="danger">
              <p>{ko.batches.pc.allBlocked}</p>
            </Callout>
          ) : (
            <div className="stack">
              <p>
                {expected.startsWith('실제 실행')
                  ? ko.batches.confirmBodyLive
                  : ko.batches.confirmBody}
              </p>
              <Callout tone="warning">
                <p>{ko.legal.abHint}</p>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={abAck}
                    aria-describedby="ab-needed"
                    onChange={(e) => setAbAck(e.target.checked)}
                  />
                  {ko.legal.abConfirm}
                </label>
              </Callout>
              <ConfirmPhrase phrase={expected} value={phrase} onChange={setPhrase} />
              <p id="ab-needed" className="muted" aria-live="polite">
                {abAck ? '' : ko.legal.abNeeded}
              </p>
              {execute.isError && <ErrorPanel error={execute.error} />}
              <div>
                <Button
                  variant="danger"
                  busy={execute.isPending}
                  disabled={phrase !== expected || !abAck}
                  onClick={() => execute.mutate()}
                >
                  {execute.isPending ? ko.batches.executing : ko.batches.execute}
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}

      {discarded && (
        <Callout tone="info" role="status">
          <p>{ko.batches.discardedBody}</p>
          <Link to="/batches">{ko.batches.backToList}</Link>
        </Callout>
      )}

      {!draft && !discarded && (
        <Card title={ko.batches.progressTitle}>
          <div className="stack">
            <Progress value={doneCount} max={total} label={ko.batches.progressLabel} />
            <p aria-live="polite">{ko.batches.progressDone(doneCount, total)}</p>
            <ul className="row" aria-label={ko.batches.progressTitle}>
              {(Object.keys(ko.batches.countsLabel) as (keyof typeof ko.batches.countsLabel)[]).map(
                (k) => (
                  <li key={k} className="item-inline">
                    <Badge
                      tone={itemTone(k)}
                    >{`${ko.batches.countsLabel[k]} ${fmtNum(batch.counts[k])}`}</Badge>
                  </li>
                ),
              )}
            </ul>
            {active ? (
              <>
                <p className="muted">{ko.batches.pollingHint}</p>
                <div>
                  <Button variant="danger" onClick={() => setStopOpen(true)}>
                    {ko.batches.stop}
                  </Button>
                </div>
              </>
            ) : (
              <p>
                {ko.batches.finished} <Link to="/history">{ko.batches.finishedHistory}</Link>
              </p>
            )}
          </div>
        </Card>
      )}

      {stopOpen && (
        <Modal
          title={ko.batches.stopTitle}
          onClose={() => setStopOpen(false)}
          footer={
            <>
              <Button onClick={() => setStopOpen(false)}>{ko.app.cancel}</Button>
              <Button variant="danger" busy={cancel.isPending} onClick={() => cancel.mutate()}>
                {ko.batches.stopConfirm}
              </Button>
            </>
          }
        >
          <p>{ko.batches.stopBody}</p>
          {cancel.isError && <ErrorPanel error={cancel.error} />}
        </Modal>
      )}
    </div>
  );
}

export function BatchDetailPage() {
  const { batchId = '' } = useParams();
  const id = Number(batchId);
  const loc = useLocation();
  const api = useApi();
  const valid = Number.isInteger(id) && id > 0;
  const q = useQuery({
    queryKey: ['batch', id],
    queryFn: () => api.batch(id),
    enabled: valid,
    // 진행 중이면 2초마다 서버 상태를 다시 읽는다(새로고침해도 같은 방식으로 복구된다)
    refetchInterval: (query) =>
      query.state.data && isBatchActive(query.state.data.status) ? 2000 : false,
  });
  const navState: unknown = (loc.state as { precheck?: unknown } | null)?.precheck;
  const notFound = !valid || (q.error instanceof ApiError && q.error.status === 404);
  return (
    <>
      <p>
        <Link to="/batches">{ko.batches.backToList}</Link>
      </p>
      <PageHead title={valid ? ko.batches.batchTitle(id) : ko.batches.notFoundTitle} />
      {notFound ? (
        <EmptyState
          title={ko.batches.notFoundTitle}
          action={<Link to="/batches">{ko.batches.backToList}</Link>}
        />
      ) : (
        <QueryView query={q} lines={6}>
          {(b) => (
            <Detail key={b.id} batch={b} pcFromNav={isPrecheck(navState) ? navState : null} />
          )}
        </QueryView>
      )}
    </>
  );
}
