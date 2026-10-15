import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { useApi } from '../api/context';
import { ApiError } from '../api/client';
import type { VideoDetail } from '../api/types';
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorPanel,
  PageHead,
  QueryView,
  TableWrap,
  useToast,
} from '../components';
import { ko } from '../i18n/ko';
import { fmtDateTime, fmtNum, fmtDuration } from '../lib/format';
import {
  changeResultLabel,
  changeTypeLabel,
  limitReasonText,
  privacyLabel,
  resultTone,
  workflowLabel,
  workflowTone,
} from '../lib/labels';
import { SuggestionCard } from './SuggestionCard';
import { suggestionScore } from '../lib/score';

function Detail({ v }: { v: VideoDetail }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const suggest = useMutation({
    mutationFn: () => api.suggestForVideo(v.video_id),
    onSuccess: (list) => {
      toast.push('success', ko.detail.suggestedToast(list.length));
      void qc.invalidateQueries({ queryKey: ['video', v.video_id] });
      void qc.invalidateQueries({ queryKey: ['videos'] });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
  const limitReasons = v.limits.reasons.map(limitReasonText);
  return (
    <div className="stack">
      <Card title={ko.detail.currentTitle}>
        <p className="stat">{v.title}</p>
        <div className="row">
          <Badge tone={workflowTone(v.workflow_status)}>{workflowLabel(v.workflow_status)}</Badge>
          <span className="mono muted">{v.video_id}</span>
        </div>
        <dl className="kv detail-kv">
          <dt>{ko.detail.meta.privacy}</dt>
          <dd>
            {privacyLabel(v.privacy_status)}
            {v.is_short ? ` · ${ko.videos.shortBadge}` : ''}
          </dd>
          <dt>{ko.detail.meta.duration}</dt>
          <dd>{fmtDuration(v.duration_sec)}</dd>
          <dt>{ko.detail.meta.views}</dt>
          <dd>{fmtNum(v.views)}</dd>
          <dt>{ko.detail.meta.lastChange}</dt>
          <dd>{fmtDateTime(v.last_change_at)}</dd>
          <dt>{ko.detail.description}</dt>
          <dd>{v.description_excerpt || ko.detail.descriptionNone}</dd>
        </dl>
      </Card>

      {v.excluded && (
        <Callout tone="warning" title={ko.detail.excludedTitle}>
          <p>{ko.detail.excludedBody}</p>
          <ul>
            {v.exclusion_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </Callout>
      )}

      <Card title={ko.detail.limitsTitle}>
        {v.limits.allowed ? (
          <Badge tone="success" icon="✓">
            {ko.detail.limitOk}
          </Badge>
        ) : (
          <Callout tone="warning" title={ko.detail.limitNo}>
            {limitReasons.length > 0 && (
              <ul>
                {limitReasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            )}
            {v.limits.next_allowed_at && (
              <p>{ko.detail.limitNext(fmtDateTime(v.limits.next_allowed_at))}</p>
            )}
          </Callout>
        )}
      </Card>

      <section aria-labelledby="sg-title" className="stack">
        <div className="row row--between">
          <h2 id="sg-title">{ko.detail.suggestionsTitle}</h2>
          <Button
            variant="primary"
            busy={suggest.isPending}
            disabled={v.excluded}
            onClick={() => suggest.mutate()}
          >
            {suggest.isPending ? ko.detail.suggesting : ko.detail.suggest}
          </Button>
        </div>
        <div className="legal-note muted">
          <p>{ko.legal.validationNote}</p>
          <p>{ko.legal.disclaimer}</p>
        </div>
        {suggest.isError && <ErrorPanel error={suggest.error} />}
        {v.suggestions.length === 0 ? (
          <EmptyState title={ko.detail.suggestionsEmpty}>
            {ko.detail.suggestionsEmptyHint}
          </EmptyState>
        ) : (
          [...v.suggestions]
            .sort((a, b) => suggestionScore(b) - suggestionScore(a) || b.id - a.id)
            .map((s) => (
            <SuggestionCard key={s.id} s={s} currentTitle={v.title} disabled={v.excluded} />
          ))
        )}
      </section>

      <section aria-labelledby="ch-title" className="stack">
        <h2 id="ch-title">{ko.detail.changesTitle}</h2>
        {v.changes.length === 0 ? (
          <p className="muted">{ko.detail.changesEmpty}</p>
        ) : (
          <TableWrap label={ko.detail.changesTitle}>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{ko.history.colTime}</th>
                  <th scope="col">{ko.history.colType}</th>
                  <th scope="col">{ko.history.colChange}</th>
                  <th scope="col">{ko.history.colResult}</th>
                </tr>
              </thead>
              <tbody>
                {v.changes.map((c) => (
                  <tr key={c.id}>
                    <td className="nowrap">{fmtDateTime(c.applied_at)}</td>
                    <td>{changeTypeLabel(c.change_type)}</td>
                    <td>
                      {c.previous_title} → <strong>{c.new_title}</strong>
                    </td>
                    <td>
                      <Badge tone={resultTone(c.result)}>{changeResultLabel(c.result)}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
      </section>
    </div>
  );
}

export function VideoDetailPage() {
  const { videoId = '' } = useParams();
  const api = useApi();
  const q = useQuery({
    queryKey: ['video', videoId],
    queryFn: () => api.video(videoId),
    enabled: videoId !== '',
  });
  const notFound = q.error instanceof ApiError && q.error.status === 404;
  return (
    <>
      <p>
        <Link to="/videos">{ko.detail.back}</Link>
      </p>
      <PageHead title={ko.detail.pageTitle} subtitle={videoId} />
      {notFound ? (
        <EmptyState
          title={ko.detail.notFoundTitle}
          action={<Link to="/videos">{ko.detail.back}</Link>}
        >
          {ko.detail.notFoundBody}
        </EmptyState>
      ) : (
        <QueryView query={q} lines={6}>
          {(v) => <Detail v={v} />}
        </QueryView>
      )}
    </>
  );
}
