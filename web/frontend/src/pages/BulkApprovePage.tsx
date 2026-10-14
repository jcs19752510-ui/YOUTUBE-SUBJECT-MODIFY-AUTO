import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApi } from '../api/context';
import type { BulkApproveResult, ResolvedVideo, Suggestion, WorkflowStatus } from '../api/types';
import {
  Button,
  Badge,
  Callout,
  Card,
  EmptyState,
  ErrorPanel,
  Field,
  Modal,
  PageHead,
  Skeleton,
  TableWrap,
  ValidationBadge,
} from '../components';
import { useApproverName } from '../hooks/approver';
import { useIdempotency } from '../hooks/useIdempotency';
import { ko } from '../i18n/ko';
import { Pagination } from '../components/Pagination';
import { fmtDate, fmtDateTimeSec, kstDateOffset } from '../lib/format';
import { workflowLabel } from '../lib/labels';
import { scoreTone, suggestionScore } from '../lib/score';
import { STATUSES } from './VideosPage';

export const MAX_BULK = ko.bulk.max;
const ID_FORMAT = /^[A-Za-z0-9_-]{11}$/;

/** 붙여넣은 글에서 영상 ID 를 뽑는다(줄바꿈·쉼표·세미콜론·공백 구분, 중복 제거, 순서 유지). */
export function parseVideoIds(text: string): { valid: string[]; invalid: string[] } {
  const seen = new Set<string>();
  const valid: string[] = [];
  const invalid: string[] = [];
  for (const t of text.split(/[\s,;]+/)) {
    if (!t || seen.has(t)) continue;
    seen.add(t);
    (ID_FORMAT.test(t) ? valid : invalid).push(t);
  }
  return { valid, invalid };
}

/** 서버 규칙과 같다: 차단이거나 엄격 모드에서 통과가 아니면 승인할 수 없다. */
function blockWhy(s: Suggestion): string | null {
  if (s.status === 'approved') return ko.bulk.alreadyApproved;
  if (s.status === 'blocked' || s.validation_result === 'block') return ko.bulk.blockedWhy;
  if (s.strict && s.validation_result !== 'pass') return ko.bulk.strictWhy;
  return null;
}
const isWarn = (s: Suggestion) => !blockWhy(s) && s.validation_result === 'warn';

interface QueueItem {
  s: Suggestion;
  currentTitle: string | null;
}

const MAX_APPROVER_CHARS = 40;
/** 서버 규칙(clean_approver)과 같게: 비어 있음 / 제어·보이지 않는 문자 / 40자 초과를 화면에서 먼저 알린다. 서버가 최종 판단한다. */
function approverProblem(v: string): 'empty' | 'invalid' | null {
  const t = v.trim();
  if (t === '' || t.replace(/[\p{Cf}\p{Zl}\p{Zp}\s]/gu, '') === '') return 'empty';
  if (/[\p{Cf}\p{Zl}\p{Zp}\p{Cc}]/u.test(t) || [...t].length > MAX_APPROVER_CHARS) return 'invalid';
  return null;
}

export function BulkApprovePage() {
  const api = useApi();
  const qc = useQueryClient();
  const keys = useIdempotency();
  const [filterText, setFilterText] = useState('');
  const [verdict, setVerdict] = useState('');
  const [dateRange, setDateRange] = useState<'' | 'today' | 'yesterday' | 'week'>('');
  const [wfStatus, setWfStatus] = useState<WorkflowStatus | ''>('');
  const [pg, setPg] = useState(1);
  const [pgSize, setPgSize] = useState(100);
  const [approver, setApprover] = useApproverName();
  const [pickedA, setPickedA] = useState<Set<number>>(new Set());
  const [text, setText] = useState('');
  const [resolved, setResolved] = useState<ResolvedVideo[]>([]);
  const [choice, setChoice] = useState<Map<string, number>>(new Map());
  const [open, setOpen] = useState(false);
  const [acks, setAcks] = useState<Set<number>>(new Set());
  const [result, setResult] = useState<BulkApproveResult | null>(null);

  const lists = useQueries({
    queries: ['candidate', 'expired', 'blocked'].map((status) => ({
      queryKey: ['suggestions', 'bulk', status],
      queryFn: () => api.suggestions({ status, page_size: MAX_BULK }),
    })),
  });
  const loading = lists.some((q) => q.isPending);
  const listError = lists.find((q) => q.isError)?.error;
  const rows = lists.flatMap((q) => q.data?.items ?? []);
  // 진행 상태: 영상 목록과 같은 이름·같은 기준(영상의 진행 상태)으로 거른다. 해당 상태의 영상 ID 를 영상 목록 API 로 받아 그 영상의 제안만 남긴다.
  const statusVideos = useQuery({
    queryKey: ['bulk-video-status', wfStatus, 1],
    queryFn: () => api.videos({ status: wfStatus, page_size: 200, page: 1 }),
    enabled: wfStatus !== '',
  });
  // 해당 상태의 영상이 200개를 넘으면 나머지 쪽도 받아 모두 합친다(가려지는 제안이 없게).
  const morePages = Array.from(
    { length: Math.max(0, Math.ceil((statusVideos.data?.total ?? 0) / 200) - 1) },
    (_, i) => i + 2,
  );
  const moreVideos = useQueries({
    queries: morePages.map((pageNo) => ({
      queryKey: ['bulk-video-status', wfStatus, pageNo],
      queryFn: () => api.videos({ status: wfStatus, page_size: 200, page: pageNo }),
    })),
  });
  const statusLoading =
    wfStatus !== '' && (statusVideos.isPending || moreVideos.some((q) => q.isPending));
  const statusError =
    wfStatus !== '' ? (statusVideos.error ?? moreVideos.find((q) => q.isError)?.error) : null;
  const statusIds = new Set(
    [statusVideos.data, ...moreVideos.map((q) => q.data)].flatMap((d) =>
      (d?.items ?? []).map((v) => v.video_id),
    ),
  );
  const needle = filterText.trim().toLowerCase();
  // 최근에 만든 제안이 맨 위에 오도록 번호가 큰 것부터 보여 준다. 글자·판정으로 줄일 수 있다.
  const today = kstDateOffset(0);
  const inDateRange = (iso: string): boolean => {
    if (!dateRange) return true;
    const day = fmtDate(iso);
    if (dateRange === 'today') return day === today;
    if (dateRange === 'yesterday') return day === kstDateOffset(1);
    return day >= kstDateOffset(6) && day <= today;
  };
  const shownRows = [...rows]
    .sort((x, y) => y.id - x.id)
    .filter(
      (s) =>
        (!needle ||
          s.video_id.toLowerCase().includes(needle) ||
          s.title.toLowerCase().includes(needle)) &&
        (!verdict || s.validation_result === verdict) &&
        inDateRange(s.created_at) &&
        (wfStatus === '' || statusIds.has(s.video_id)),
    );

  // 현재 제목: 목록 영상 ID 를 50개씩 resolve-videos 로 조회한다(실패해도 승인은 막지 않는다).
  const listVideoIds = [...new Set(rows.map((s) => s.video_id))];
  const chunks: string[][] = [];
  for (let i = 0; i < listVideoIds.length; i += MAX_BULK)
    chunks.push(listVideoIds.slice(i, i + MAX_BULK));
  const titleQs = useQueries({
    queries: chunks.map((ch) => ({
      queryKey: ['suggestions', 'bulk-titles', ch.join(',')],
      queryFn: () => api.resolveVideos(ch),
      staleTime: 60_000,
      retry: false,
    })),
  });
  const titleMap = new Map<string, string | null>();
  for (const q of titleQs)
    for (const it of q.data?.items ?? [])
      titleMap.set(it.video_id, it.found ? it.video_title : null);
  const titleLoading = titleQs.some((q) => q.isPending);
  const titleOf = (id: string): string | null => titleMap.get(id) ?? null;
  const titleText = (t: string | null) =>
    t ?? (titleLoading ? ko.bulk.titleLoading : ko.bulk.titleMissing);

  const parsed = parseVideoIds(text);
  const findDisabledWhy =
    parsed.valid.length === 0 && parsed.invalid.length === 0
      ? ko.bulk.findEmpty
      : parsed.valid.length > MAX_BULK
        ? ko.bulk.findTooMany(parsed.valid.length, MAX_BULK)
        : parsed.valid.length === 0
          ? ko.bulk.findEmpty
          : null;

  const find = useMutation({
    mutationFn: () => api.resolveVideos(parsed.valid),
    onSuccess: (r) => {
      setResolved(r.items);
      // 후보가 정확히 1개(승인 가능)일 때만 미리 선택한다. 2개 이상은 사람이 고를 때까지 비워 둔다.
      const next = new Map<string, number>();
      for (const it of r.items) {
        const ok = it.candidates.filter((c) => !blockWhy(c));
        if (
          it.found &&
          it.excluded_reasons.length === 0 &&
          it.candidates.length === 1 &&
          ok.length === 1
        )
          next.set(it.video_id, ok[0]!.id);
      }
      setChoice(next);
    },
  });

  // 승인 대기 목록: 방법 A 선택 → 방법 B 선택 순, 같은 영상은 처음 것 하나만
  const queue: QueueItem[] = [];
  const seenVideo = new Set<string>();
  let dupCount = 0;
  const add = (s: Suggestion, currentTitle: string | null) => {
    if (seenVideo.has(s.video_id)) {
      dupCount++;
      return;
    }
    seenVideo.add(s.video_id);
    queue.push({ s, currentTitle });
  };
  for (const s of rows) if (pickedA.has(s.id) && !blockWhy(s)) add(s, titleOf(s.video_id));
  for (const it of resolved) {
    const id = choice.get(it.video_id);
    const s = it.candidates.find((c) => c.id === id);
    if (s && !blockWhy(s) && it.found && it.excluded_reasons.length === 0) add(s, it.video_title);
  }
  const needChoice = resolved.filter(
    (it) =>
      it.found &&
      it.excluded_reasons.length === 0 &&
      it.candidates.filter((c) => !blockWhy(c)).length >= 2 &&
      !choice.has(it.video_id),
  ).length;
  const over = queue.length > MAX_BULK;
  const full = queue.length >= MAX_BULK;
  const warnItems = queue.filter((q) => isWarn(q.s));
  const warnLeft = warnItems.filter((q) => !acks.has(q.s.id));

  const toggleA = (id: number) =>
    setPickedA((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const lastPage = Math.max(1, Math.ceil(shownRows.length / pgSize));
  const curPage = Math.min(pg, lastPage);
  const pagedRows = shownRows.slice((curPage - 1) * pgSize, curPage * pgSize);
  const pickable = shownRows.filter((s) => !blockWhy(s));
  const pagePicked = pickable.length > 0 && pickable.every((s) => pickedA.has(s.id));
  const pickPage = (on: boolean) =>
    setPickedA((prev) => {
      // 줄여 보기로 숨겨진 항목의 선택은 건드리지 않는다: 보이는 항목만 더하거나 뺀다.
      if (!on) {
        const visible = new Set(shownRows.map((s) => s.id));
        return new Set([...prev].filter((id) => !visible.has(id)));
      }
      // 50건을 넘지 않는 만큼만 담는다(이미 담긴 것 포함)
      const room = MAX_BULK - queue.length;
      const add = pickable.filter((s) => !prev.has(s.id)).slice(0, Math.max(0, room));
      return new Set([...prev, ...add.map((s) => s.id)]);
    });

  const ackIds = warnItems.filter((q) => acks.has(q.s.id)).map((q) => q.s.id);
  const ids = queue.map((q) => q.s.id);
  const [snap, setSnap] = useState<Map<number, { cur: string | null; title: string }>>(new Map());
  const approve = useMutation({
    onMutate: () =>
      setSnap(new Map(queue.map((q) => [q.s.id, { cur: q.currentTitle, title: q.s.title }]))),
    mutationFn: () =>
      api.approveBatch(
        ids,
        approver.trim(),
        ackIds,
        keys.get(`${ids.join(',')}|${approver.trim()}|${ackIds.join(',')}`),
      ),
    onSuccess: (r) => {
      keys.clear();
      setResult(r);
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ['suggestions'] });
      void qc.invalidateQueries({ queryKey: ['videos'] });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });

  const gate: string[] = [];
  const apProblem = approverProblem(approver);
  if (apProblem === 'empty') gate.push(ko.bulk.approverEmpty);
  if (apProblem === 'invalid') gate.push(ko.bulk.approverInvalid);
  if (warnLeft.length > 0) gate.push(ko.bulk.ackNeed(warnLeft.length));
  if (over) gate.push(ko.bulk.queueOver(queue.length, MAX_BULK));
  if (queue.length === 0) gate.push(ko.bulk.reviewDisabledEmpty);

  const reset = () => {
    setResult(null);
    setPickedA(new Set());
    setResolved([]);
    setChoice(new Map());
    setText('');
    setAcks(new Set());
    approve.reset();
  };
  const closeDialog = () => {
    setOpen(false);
    approve.reset();
  };

  if (result) {
    return (
      <>
        <PageHead title={ko.bulk.title} subtitle={ko.bulk.subtitle} />
        <div className="stack">
          <Callout
            tone={result.counts.skipped > 0 ? 'warning' : 'success'}
            role="status"
            title={`${ko.bulk.resultTitle}: ${ko.bulk.resultSummary(result.counts.approved, result.counts.skipped)}`}
          >
            <p>{ko.bulk.resultOnly}</p>
            <p>{ko.bulk.ttlNotice}</p>
          </Callout>
          {result.approved.length > 0 && (
            <TableWrap label={ko.bulk.approvedCaption(result.approved.length)}>
              <table className="table">
                <caption>{ko.bulk.approvedCaption(result.approved.length)}</caption>
                <thead>
                  <tr>
                    <th scope="col">{ko.bulk.colVideo}</th>
                    <th scope="col">{ko.bulk.colCurrent}</th>
                    <th scope="col">{ko.bulk.colChange}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.approved.map((a) => (
                    <tr key={a.suggestion_id}>
                      <td className="mono">{a.video_id}</td>
                      <td>{titleText(snap.get(a.suggestion_id)?.cur ?? null)}</td>
                      <td className="cell-title">{snap.get(a.suggestion_id)?.title ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
          {result.skipped.length > 0 && (
            <TableWrap label={ko.bulk.skippedCaption(result.skipped.length)}>
              <table className="table">
                <caption>{ko.bulk.skippedCaption(result.skipped.length)}</caption>
                <thead>
                  <tr>
                    <th scope="col">{ko.bulk.colVideo}</th>
                    <th scope="col">{ko.bulk.colReason}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.skipped.map((k) => (
                    <tr key={k.suggestion_id}>
                      <td className="mono">{k.video_id ?? '-'}</td>
                      <td>
                        {k.code === 'suggestion_state'
                          ? k.reason || ko.bulk.codes[k.code]
                          : (ko.bulk.codes[k.code] ?? k.reason)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
          <div className="row">
            <Link to="/batches" className="btn btn--primary">
              {ko.bulk.goBatches}
            </Link>
            <Button onClick={reset}>{ko.bulk.again}</Button>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHead title={ko.bulk.title} subtitle={ko.bulk.subtitle} />
      <div className="stack">
        <Callout tone="info">{ko.bulk.onlyApprove}</Callout>

        <Card title={ko.bulk.methodA}>
          {loading ? (
            <Skeleton lines={4} />
          ) : listError ? (
            <ErrorPanel error={listError} onRetry={() => lists.forEach((q) => void q.refetch())} />
          ) : rows.length === 0 ? (
            <EmptyState title={ko.bulk.listEmpty} />
          ) : (
            <div className="stack">
              <form className="toolbar" role="search" onSubmit={(e) => e.preventDefault()}>
                <Field label={ko.videos.search} className="field--grow" hint={ko.bulk.filterHint}>
                  <input
                    name="bulk-list-filter"
                    className="input"
                    type="search"
                    value={filterText}
                    placeholder={ko.bulk.filterPlaceholder}
                    onChange={(e) => {
                      setFilterText(e.target.value);
                      setPg(1);
                    }}
                  />
                </Field>
                <Field label={ko.videos.filterStatus}>
                  <select
                    name="bulk-status-filter"
                    className="select"
                    value={wfStatus}
                    onChange={(e) => {
                      setWfStatus(e.target.value as WorkflowStatus | '');
                      setPg(1);
                    }}
                  >
                    <option value="">{ko.videos.filterAll}</option>
                    {STATUSES.map((st) => (
                      <option key={st} value={st}>
                        {workflowLabel(st)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={ko.bulk.verdictFilterLabel}>
                  <select
                    name="bulk-verdict-filter"
                    className="select"
                    value={verdict}
                    onChange={(e) => {
                      setVerdict(e.target.value);
                      setPg(1);
                    }}
                  >
                    <option value="">{ko.bulk.verdictAll}</option>
                    <option value="pass">{ko.bulk.verdictPass}</option>
                    <option value="warn">{ko.bulk.verdictWarn}</option>
                    <option value="block">{ko.bulk.verdictBlock}</option>
                  </select>
                </Field>
                <Field label={ko.bulk.dateFilterLabel}>
                  <select
                    name="bulk-date-filter"
                    className="select"
                    value={dateRange}
                    onChange={(e) => {
                      setDateRange(e.target.value as typeof dateRange);
                      setPg(1);
                    }}
                  >
                    <option value="">{ko.bulk.dateAll}</option>
                    <option value="today">{ko.bulk.dateToday}</option>
                    <option value="yesterday">{ko.bulk.dateYesterday}</option>
                    <option value="week">{ko.bulk.dateWeek}</option>
                  </select>
                </Field>
                {(needle || verdict || wfStatus || dateRange) && (
                  <Button
                    onClick={() => {
                      setDateRange('');
                      setFilterText('');
                      setVerdict('');
                      setWfStatus('');
                    }}
                  >
                    {ko.videos.reset}
                  </Button>
                )}
              </form>
              {!statusLoading &&
                !statusError &&
                (needle || verdict || wfStatus || dateRange) &&
                shownRows.length === 0 && <p className="muted">{ko.bulk.filterNone}</p>}
              {statusLoading && <Skeleton lines={3} />}
              {statusError && (
                <ErrorPanel
                  error={statusError}
                  onRetry={() => {
                    void statusVideos.refetch();
                    moreVideos.forEach((q) => void q.refetch());
                  }}
                />
              )}
              <TableWrap label={ko.bulk.methodA}>
                <table className="table">
                  <caption>
                    {statusLoading
                      ? ko.bulk.statusLoading
                      : statusError
                        ? ko.bulk.statusFail
                        : ko.bulk.listCaption(shownRows.length)}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">
                        <label className="check-hit">
                          <input
                            id="bulk-pick-page"
                            name="bulk-pick-page"
                            type="checkbox"
                            aria-label={ko.bulk.pickPage}
                            checked={pagePicked}
                            disabled={pickable.length === 0}
                            onChange={(e) => pickPage(e.target.checked)}
                          />
                        </label>
                      </th>
                      <th scope="col">{ko.bulk.colVideo}</th>
                      <th scope="col">{ko.bulk.colCurrent}</th>
                      <th scope="col">{ko.bulk.colNew}</th>
                      <th scope="col">{ko.bulk.colVerdict}</th>
                      <th scope="col">{ko.bulk.colScore}</th>
                      <th scope="col">{ko.bulk.colLength}</th>
                      <th scope="col">{ko.bulk.colRequested}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedRows.map((s) => {
                      const why = blockWhy(s);
                      const checked = pickedA.has(s.id);
                      return (
                        <tr key={s.id} aria-selected={checked}>
                          <td>
                            <label className="check-hit">
                              <input
                                id={`bulk-pick-${s.id}`}
                                name="bulk-pick"
                                type="checkbox"
                                aria-label={ko.bulk.pickOne(s.title)}
                                checked={checked && !why}
                                disabled={!!why || (full && !checked)}
                                onChange={() => toggleA(s.id)}
                              />
                            </label>
                          </td>
                          <td className="mono">{s.video_id}</td>
                          <td className="cell-title">{titleText(titleOf(s.video_id))}</td>
                          <td className="cell-title">
                            {s.title}
                            {why && <p className="field__error">{why}</p>}
                            {why && s.status === 'blocked' && (
                              <ul className="muted" aria-label={ko.bulk.blockReasonsLabel}>
                                {s.reasons
                                  .filter((r) => r.severity === 'block')
                                  .map((r, i) => (
                                    <li key={`${r.code}-${i}`}>{r.message}</li>
                                  ))}
                              </ul>
                            )}
                          </td>
                          <td>
                            <ValidationBadge result={s.validation_result} />
                          </td>
                          <td title={ko.suggestion.scoreHint}>
                            <Badge tone={scoreTone(suggestionScore(s))}>
                              {suggestionScore(s)}점
                            </Badge>
                          </td>
                          <td>{s.length}</td>
                          <td className="mono">{fmtDateTimeSec(s.created_at)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </TableWrap>
              <Pagination
                page={curPage}
                pageSize={pgSize}
                total={shownRows.length}
                onPage={setPg}
                onPageSize={(n) => {
                  setPgSize(n);
                  setPg(1);
                }}
              />

              {full && <p className="field__error">{ko.bulk.full(MAX_BULK)}</p>}
            </div>
          )}
        </Card>

        <Card title={ko.bulk.methodB}>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              if (!findDisabledWhy && !find.isPending) find.mutate();
            }}
          >
            <Field label={ko.bulk.pasteLabel} hint={ko.bulk.pasteHint}>
              <textarea
                name="bulk-video-ids"
                rows={4}
                className="input mono"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </Field>
            {parsed.invalid.length > 0 && (
              <p className="field__error" role="status">
                {ko.bulk.invalidIds(parsed.invalid.join(', '))}
              </p>
            )}
            <div className="row">
              <Button type="submit" busy={find.isPending} disabled={!!findDisabledWhy}>
                {find.isPending ? ko.bulk.finding : ko.bulk.find}
              </Button>
              {findDisabledWhy && <span className="muted">{findDisabledWhy}</span>}
            </div>
            {find.isError && <ErrorPanel error={find.error} onRetry={() => find.mutate()} />}
          </form>
          {resolved.length > 0 && (
            <div className="stack">
              <TableWrap label={ko.bulk.methodB}>
                <table className="table">
                  <caption>{ko.bulk.resultCaption(resolved.length)}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{ko.bulk.colVideo}</th>
                      <th scope="col">{ko.bulk.colState}</th>
                      <th scope="col">{ko.bulk.colCandidates}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resolved.map((it) => (
                      <ResolvedRow
                        key={it.video_id}
                        it={it}
                        chosen={choice.get(it.video_id)}
                        onChoose={(id) => setChoice((m) => new Map(m).set(it.video_id, id))}
                      />
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            </div>
          )}
        </Card>

        <Card title={ko.bulk.queueTitle}>
          <div className="stack" aria-live="polite">
            <p>{ko.bulk.selectedCount(queue.length, MAX_BULK)}</p>
            {needChoice > 0 && <p className="field__error">{ko.bulk.pendingChoice(needChoice)}</p>}
            {dupCount > 0 && <p className="muted">{ko.bulk.queueDup(dupCount)}</p>}
            {over && <p className="field__error">{ko.bulk.queueOver(queue.length, MAX_BULK)}</p>}
          </div>
          {queue.length === 0 ? (
            <p className="muted">{ko.bulk.queueEmpty}</p>
          ) : (
            <TableWrap label={ko.bulk.queueTitle}>
              <table className="table">
                <caption>{ko.bulk.queueCaption(queue.length)}</caption>
                <thead>
                  <tr>
                    <th scope="col">{ko.bulk.colVideo}</th>
                    <th scope="col">{ko.bulk.colCurrent}</th>
                    <th scope="col">{ko.bulk.colNew}</th>
                    <th scope="col">{ko.bulk.colVerdict}</th>
                    <th scope="col">{ko.bulk.colScore}</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.map((q) => (
                    <tr key={q.s.id}>
                      <td className="mono">{q.s.video_id}</td>
                      <td className="cell-title">{titleText(q.currentTitle)}</td>
                      <td className="cell-title">{q.s.title}</td>
                      <td>
                        <ValidationBadge result={q.s.validation_result} />
                      </td>
                      <td title={ko.suggestion.scoreHint}>
                        <Badge tone={scoreTone(suggestionScore(q.s))}>
                          {suggestionScore(q.s)}점
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
          <div className="row">
            <Button
              variant="primary"
              disabled={queue.length === 0 || over}
              onClick={() => setOpen(true)}
            >
              {ko.bulk.review}
            </Button>
            {queue.length === 0 && <span className="muted">{ko.bulk.reviewDisabledEmpty}</span>}
            {over && <span className="muted">{ko.bulk.queueOver(queue.length, MAX_BULK)}</span>}
          </div>
        </Card>
      </div>

      {open && (
        <Modal
          wide
          title={ko.bulk.dialogTitle(queue.length)}
          onClose={closeDialog}
          closeDisabled={approve.isPending}
          footer={
            <>
              <Button onClick={closeDialog} disabled={approve.isPending}>
                {ko.bulk.cancel}
              </Button>
              <Button
                variant="primary"
                busy={approve.isPending}
                disabled={gate.length > 0}
                onClick={() => {
                  if (gate.length === 0 && !approve.isPending) approve.mutate();
                }}
              >
                {approve.isPending ? ko.bulk.submitting : ko.bulk.submit(queue.length)}
              </Button>
            </>
          }
        >
          <div className="stack">
            <Callout tone="info">
              <p>{ko.bulk.onlyApprove}</p>
              <p>{ko.bulk.ttlNotice}</p>
            </Callout>
            <Field
              label={ko.bulk.approverLabel}
              hint={ko.bulk.approverHint}
              error={
                approverProblem(approver) === 'empty'
                  ? ko.bulk.approverEmpty
                  : approverProblem(approver) === 'invalid'
                    ? ko.bulk.approverInvalid
                    : undefined
              }
            >
              <input
                name="bulk-approver"
                className="input"
                value={approver}
                maxLength={200}
                data-autofocus
                onChange={(e) => setApprover(e.target.value)}
              />
            </Field>
            <TableWrap label={ko.bulk.dialogTitle(queue.length)}>
              <table className="table">
                <caption>{ko.bulk.queueCaption(queue.length)}</caption>
                <thead>
                  <tr>
                    <th scope="col">{ko.bulk.colVideo}</th>
                    <th scope="col">{ko.bulk.colCurrent}</th>
                    <th scope="col">{ko.bulk.colChange}</th>
                    <th scope="col">{ko.bulk.colAck}</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.map((q) => (
                    <tr key={q.s.id}>
                      <td className="mono">{q.s.video_id}</td>
                      <td>{titleText(q.currentTitle)}</td>
                      <td className="cell-title">
                        {q.s.title} <ValidationBadge result={q.s.validation_result} />
                        {isWarn(q.s) && (
                          <ul className="muted" aria-label={ko.bulk.warnReasonsLabel}>
                            {q.s.reasons
                              .filter((r) => r.severity !== 'info')
                              .map((r, i) => (
                                <li key={`${r.code}-${i}`}>{r.message}</li>
                              ))}
                          </ul>
                        )}
                      </td>
                      <td>
                        {isWarn(q.s) ? (
                          <label className="check-hit">
                            <input
                              id={`bulk-ack-${q.s.id}`}
                              name="bulk-ack"
                              type="checkbox"
                              aria-label={ko.bulk.ackOne(q.s.title)}
                              checked={acks.has(q.s.id)}
                              onChange={() =>
                                setAcks((s) => {
                                  const n = new Set(s);
                                  if (n.has(q.s.id)) n.delete(q.s.id);
                                  else n.add(q.s.id);
                                  return n;
                                })
                              }
                            />
                          </label>
                        ) : (
                          '-'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            {queue.some((q) => q.currentTitle === null) && !titleLoading && (
              <p className="field__error" role="status">
                {ko.bulk.titleMissingWarn}
              </p>
            )}
            {gate.length > 0 && (
              <div aria-live="polite">
                <p className="callout__title">{ko.bulk.gateTitle}</p>
                <ul>
                  {gate.map((g) => (
                    <li key={g}>{g}</li>
                  ))}
                </ul>
              </div>
            )}
            {approve.isError && <ErrorPanel error={approve.error} />}
          </div>
        </Modal>
      )}
    </>
  );
}

function ResolvedRow({
  it,
  chosen,
  onChoose,
}: {
  it: ResolvedVideo;
  chosen: number | undefined;
  onChoose: (id: number) => void;
}) {
  const state = !it.found
    ? ko.bulk.notFound
    : it.excluded_reasons.length > 0
      ? ko.bulk.excluded(it.excluded_reasons.join(', '))
      : it.candidates.length === 0
        ? ko.bulk.noCandidate
        : null;
  const ok = it.candidates.filter((c) => !blockWhy(c));
  const multi = !state && ok.length >= 2;
  return (
    <tr>
      <td className="mono">{it.video_id}</td>
      <td>
        {it.video_title && <div>{it.video_title}</div>}
        {state ? (
          <span className="field__error">{state}</span>
        ) : multi && chosen === undefined ? (
          <span className="field__error">{ko.bulk.needChoice}</span>
        ) : (
          <span className="muted">
            {chosen !== undefined && ok.length === 1 ? ko.bulk.preselected : ''}
          </span>
        )}
      </td>
      <td>
        {!state && multi ? (
          <fieldset className="stack">
            <legend className="sr-only">{ko.bulk.choiceGroup(it.video_id)}</legend>
            {ok.map((c) => (
              <label key={c.id} className="check-hit">
                <input
                  type="radio"
                  name={`bulk-choice-${it.video_id}`}
                  checked={chosen === c.id}
                  onChange={() => onChoose(c.id)}
                />{' '}
                {c.title} <ValidationBadge result={c.validation_result} />
              </label>
            ))}
          </fieldset>
        ) : (
          !state &&
          it.candidates.map((c) => (
            <div key={c.id}>
              {c.title} <ValidationBadge result={c.validation_result} />
              {blockWhy(c) && <p className="field__error">{blockWhy(c)}</p>}
            </div>
          ))
        )}
      </td>
    </tr>
  );
}
