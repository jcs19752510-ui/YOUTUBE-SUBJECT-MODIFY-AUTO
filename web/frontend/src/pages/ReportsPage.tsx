import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useApi } from '../api/context';
import type { VideoReport } from '../api/types';
import {
  Badge,
  Button,
  Callout,
  Card,
  DateRangeFilter,
  EmptyState,
  ErrorPanel,
  Field,
  PageHead,
  QueryView,
  TableWrap,
  useDateRange,
  useToast,
} from '../components';
import { ko } from '../i18n/ko';
import { fmtDate, fmtNum, fmtPct } from '../lib/format';

function metricFmt(key: string, v: number | null): string {
  if (v === null) return '-';
  return key === 'ctr' ? fmtPct(v <= 1 ? v * 100 : v, 2) : fmtNum(Math.round(v * 100) / 100);
}

function ReportCard({ r }: { r: VideoReport }) {
  return (
    <Card title={r.title ?? r.video_id}>
      <p className="muted mono">{r.video_id}</p>
      {r.status === 'no_change' && (
        <>
          <Badge icon="–">{ko.reports.noChange}</Badge>
          <p>{ko.reports.noChangeBody}</p>
        </>
      )}
      {r.status === 'insufficient' && (
        <div className="stack">
          <Badge tone="warning" icon="▲">
            {ko.reports.insufficient}
          </Badge>
          <div>
            <p className="field__label">{ko.reports.insufficientWhy}</p>
            <ul>
              {r.reasons.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
              {r.baseline_missing && <li>{ko.reports.baselineMissing}</li>}
            </ul>
          </div>
          {r.expected_after_date && (
            <p>{ko.reports.expectedAfter(fmtDate(r.expected_after_date))}</p>
          )}
        </div>
      )}
      {r.status === 'ok' && (
        <div className="stack">
          <Badge tone="success" icon="✓">
            {ko.reports.okBadge}
          </Badge>
          <TableWrap label={r.title ?? r.video_id}>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{ko.reports.metric}</th>
                  <th scope="col" className="num">
                    {ko.reports.before}
                  </th>
                  <th scope="col" className="num">
                    {ko.reports.after}
                  </th>
                  <th scope="col" className="num">
                    {ko.reports.delta}
                  </th>
                  <th scope="col" className="num">
                    {ko.reports.pct}
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.metrics.map((m) => (
                  <tr key={m.key}>
                    <th scope="row">{m.label}</th>
                    <td className="num">{metricFmt(m.key, m.before)}</td>
                    <td className="num">{metricFmt(m.key, m.after)}</td>
                    <td className="num">
                      {m.delta === null
                        ? '-'
                        : `${m.delta > 0 ? '+' : ''}${metricFmt(m.key, m.delta)}`}
                    </td>
                    <td className="num">
                      {m.pct === null ? '-' : `${m.pct > 0 ? '+' : ''}${fmtPct(m.pct)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          {r.before?.period_start && r.after?.period_start && (
            <p className="muted">
              {ko.reports.before}:{' '}
              {ko.reports.period(fmtDate(r.before.period_start), fmtDate(r.before.period_end))}
              <br />
              {ko.reports.after}:{' '}
              {ko.reports.period(fmtDate(r.after.period_start), fmtDate(r.after.period_end))}
            </p>
          )}
        </div>
      )}
      {r.notes.length > 0 && (
        <ul className="muted">
          {r.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function ReportsPage() {
  const api = useApi();
  const toast = useToast();
  const [input, setInput] = useState('');
  const [videoId, setVideoId] = useState('');
  const range = useDateRange();
  const q = useQuery({
    queryKey: ['reports', videoId, range.from, range.to],
    queryFn: () => api.reports(videoId || undefined, range.query),
    enabled: range.valid,
  });
  const exp = useMutation({
    mutationFn: async () => {
      if (!range.valid) throw new Error(ko.dateRange.invalid);
      const blob = await api.reportCsv(range.query);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'youtube-title-report.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
    onSuccess: () => toast.push('success', ko.reports.exported),
  });
  return (
    <>
      <PageHead
        title={ko.reports.title}
        subtitle={ko.reports.subtitle}
        actions={
          <Button busy={exp.isPending} disabled={!range.valid} onClick={() => exp.mutate()}>
            {exp.isPending ? ko.reports.exporting : ko.reports.export}
          </Button>
        }
      />
      {exp.isError && <ErrorPanel error={exp.error} />}
      <DateRangeFilter range={range} basis="제목 변경 시각 기준" />
      {!range.valid && <Callout tone="danger" title={ko.dateRange.groupLabel}>{ko.dateRange.invalid}</Callout>}
      {range.valid && <QueryView query={q} lines={6}>
        {(d) => (
          <div className="stack">
            <Callout tone="warning" title={ko.reports.notesTitle}>
              {(d.notes.length > 0 ? d.notes : [ko.reports.fallbackNote]).map((n, i) => (
                <p key={i}>{n}</p>
              ))}
              {/* 서버가 같은 면책 문장을 이미 내려 주면 두 번 보이지 않게 한다 */}
              {!d.notes.some((n) => /법률 자문/.test(n)) && <p>{ko.legal.disclaimer}</p>}
              <p>{ko.legal.reportsNote}</p>
            </Callout>
            <form
              className="toolbar"
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                setVideoId(input.trim());
              }}
            >
              <Field label={ko.reports.filterVideo} className="field--grow">
                <input className="input" value={input} onChange={(e) => setInput(e.target.value)} />
              </Field>
              <Button type="submit" variant="primary">
                {ko.videos.searchButton}
              </Button>
            </form>
            {d.items.length === 0 ? (
              <EmptyState title={ko.reports.emptyTitle}>
                {range.isAll || videoId ? ko.reports.emptyBody : ko.dateRange.none}
              </EmptyState>
            ) : (
              d.items.map((r) => <ReportCard key={r.video_id} r={r} />)
            )}
          </div>
        )}
      </QueryView>}
    </>
  );
}
