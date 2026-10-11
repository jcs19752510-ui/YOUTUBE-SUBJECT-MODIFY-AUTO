import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useApi } from '../api/context';
import type { Change } from '../api/types';
import {
  Badge,
  Button,
  EmptyState,
  ErrorPanel,
  Field,
  Modal,
  PageHead,
  Pagination,
  Skeleton,
  TableWrap,
  useToast,
} from '../components';
import { useApproverName } from '../hooks/approver';
import { useIdempotency } from '../hooks/useIdempotency';
import { ko } from '../i18n/ko';
import { fmtDateTime } from '../lib/format';
import { changeResultLabel, changeTypeLabel, resultTone } from '../lib/labels';

function RollbackDialog({ change, onClose }: { change: Change; onClose: () => void }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const keys = useIdempotency();
  const [typed, setTyped] = useState('');
  const [approver, setApprover] = useApproverName();
  const match = typed === change.video_id;
  const ok = match && approver.trim() !== '';
  const m = useMutation({
    mutationFn: () =>
      api.rollback(
        change.id,
        typed,
        approver.trim(),
        keys.get(`${change.id}|${typed}|${approver.trim()}`),
      ),
    onSuccess: () => {
      keys.clear();
      toast.push('success', ko.history.rbDone);
      void qc.invalidateQueries({ queryKey: ['changes'] });
      void qc.invalidateQueries({ queryKey: ['videos'] });
      void qc.invalidateQueries({ queryKey: ['video', change.video_id] });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
      onClose();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (ok && !m.isPending) m.mutate();
  };
  return (
    <Modal
      title={ko.history.rbTitle}
      onClose={onClose}
      closeDisabled={m.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={m.isPending}>
            {ko.app.cancel}
          </Button>
          <Button variant="danger" type="submit" form="rb-form" busy={m.isPending} disabled={!ok}>
            {m.isPending ? ko.history.rbDoing : ko.history.rbSubmit}
          </Button>
        </>
      }
    >
      <form id="rb-form" className="stack" onSubmit={submit}>
        <p>{ko.history.rbBody}</p>
        <dl className="kv">
          <dt>{ko.history.rbFrom}</dt>
          <dd>
            <strong>{change.new_title}</strong>
          </dd>
          <dt>{ko.history.rbTo}</dt>
          <dd>
            <strong>{change.previous_title}</strong>
          </dd>
        </dl>
        <Field
          label={ko.history.rbTypeLabel(change.video_id)}
          hint={ko.history.rbTypeHint}
          error={typed !== '' && !match ? ko.batches.confirmMismatch : undefined}
        >
          <input
            className="input mono"
            value={typed}
            autoComplete="off"
            spellCheck={false}
            data-autofocus=""
            onChange={(e) => setTyped(e.target.value)}
          />
        </Field>
        <Field label={ko.history.rbApprover}>
          <input
            className="input"
            value={approver}
            maxLength={40}
            onChange={(e) => setApprover(e.target.value)}
          />
        </Field>
        {m.isError && <ErrorPanel error={m.error} />}
      </form>
    </Modal>
  );
}

export function HistoryPage() {
  const api = useApi();
  const [page, setPage] = useState(1);
  const [result, setResult] = useState('');
  const [videoInput, setVideoInput] = useState('');
  const [videoId, setVideoId] = useState('');
  const [target, setTarget] = useState<Change | null>(null);
  const q = useQuery({
    queryKey: ['changes', { page, result, videoId }],
    queryFn: () =>
      api.changes({
        page,
        page_size: 50,
        result: result || undefined,
        video_id: videoId || undefined,
      }),
    placeholderData: (p) => p,
  });
  const filtered = Boolean(result || videoId);
  return (
    <>
      <PageHead title={ko.history.title} subtitle={ko.history.subtitle} />
      <div className="legal-note muted">
        <p>{ko.legal.historyNote}</p>
        <p>{ko.legal.aiNotice}</p>
      </div>
      <form
        className="toolbar"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setVideoId(videoInput.trim());
          setPage(1);
        }}
      >
        <Field label={ko.history.filterVideo} className="field--grow">
          <input
            className="input"
            value={videoInput}
            onChange={(e) => setVideoInput(e.target.value)}
          />
        </Field>
        <Field label={ko.history.filterResult}>
          <select
            className="select"
            value={result}
            onChange={(e) => {
              setResult(e.target.value);
              setPage(1);
            }}
          >
            <option value="">{ko.history.resultAll}</option>
            {ko.resultFilter.map((k) => (
              <option key={k} value={k}>
                {changeResultLabel(k)}
              </option>
            ))}
          </select>
        </Field>
        <Button type="submit" variant="primary">
          {ko.videos.searchButton}
        </Button>
      </form>
      {q.isPending ? (
        <Skeleton lines={6} />
      ) : q.isError ? (
        <ErrorPanel error={q.error} onRetry={() => void q.refetch()} />
      ) : q.data.items.length === 0 ? (
        <EmptyState
          title={filtered ? ko.videos.emptyTitle : ko.history.emptyTitle}
          action={<Link to="/batches">{ko.nav.batches}</Link>}
        >
          {filtered ? ko.videos.emptyBody : ko.history.emptyBody}
        </EmptyState>
      ) : (
        <>
          <TableWrap label={ko.history.title}>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{ko.history.colTime}</th>
                  <th scope="col">{ko.history.colVideo}</th>
                  <th scope="col">{ko.history.colType}</th>
                  <th scope="col">{ko.history.colChange}</th>
                  <th scope="col">{ko.history.colResult}</th>
                  <th scope="col">{ko.history.colApprover}</th>
                  <th scope="col">{ko.history.colAction}</th>
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((c) => (
                  <tr key={c.id}>
                    <td className="nowrap">{fmtDateTime(c.applied_at)}</td>
                    <td className="cell-title">
                      <Link to={`/videos/${encodeURIComponent(c.video_id)}`}>{c.video_title}</Link>
                      <div className="muted mono">{c.video_id}</div>
                    </td>
                    <td>
                      {changeTypeLabel(c.change_type)}
                      <div className="muted">
                        {c.mode === 'demo' ? ko.history.modeDemo : c.mode}
                      </div>
                    </td>
                    <td>
                      <div className="muted">{c.previous_title}</div>
                      <div aria-hidden="true">↓</div>
                      <strong>{c.new_title}</strong>
                    </td>
                    <td>
                      <Badge tone={resultTone(c.result)}>{changeResultLabel(c.result)}</Badge>
                      {c.error_code && (
                        <div className="muted">{ko.history.errorCode(c.error_code)}</div>
                      )}
                    </td>
                    <td>{c.approver ?? '-'}</td>
                    <td>
                      {c.rollbackable ? (
                        <Button size="sm" onClick={() => setTarget(c)}>
                          {ko.history.rollback}
                          <span className="sr-only"> {c.video_title}</span>
                        </Button>
                      ) : (
                        <span className="muted" title={ko.history.notRollbackableWhy}>
                          {ko.history.notRollbackable}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          <Pagination
            page={q.data.page}
            pageSize={q.data.page_size}
            total={q.data.total}
            onPage={setPage}
          />
        </>
      )}
      {target && <RollbackDialog change={target} onClose={() => setTarget(null)} />}
    </>
  );
}
