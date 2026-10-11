import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useApi } from '../api/context';
import type { Suggestion } from '../api/types';
import {
  Badge,
  Button,
  Callout,
  ErrorPanel,
  Field,
  Modal,
  TitleDiff,
  ValidationBadge,
  useToast,
} from '../components';
import { useApproverName } from '../hooks/approver';
import { ko } from '../i18n/ko';
import { charCount, fmtDateTime } from '../lib/format';
import { suggestionStatusLabel } from '../lib/labels';

const MAX_TITLE = 100;
type Dialog = null | 'edit' | 'approve' | 'reject';

export function SuggestionCard({
  s,
  currentTitle,
  disabled,
}: {
  s: Suggestion;
  currentTitle: string;
  disabled?: boolean;
}) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [title, setTitle] = useState(s.title);
  const [approver, setApprover] = useApproverName();
  const [ack, setAck] = useState(false);

  const done = (msg: string) => {
    toast.push('success', msg);
    setDialog(null);
    void qc.invalidateQueries({ queryKey: ['video', s.video_id] });
    void qc.invalidateQueries({ queryKey: ['videos'] });
    void qc.invalidateQueries({ queryKey: ['dashboard'] });
    void qc.invalidateQueries({ queryKey: ['suggestions'] });
  };
  const edit = useMutation({
    mutationFn: () => api.editSuggestion(s.id, title.trim()),
    onSuccess: () => done(ko.suggestion.editSaved),
  });
  const approve = useMutation({
    mutationFn: () => api.approve(s.id, approver.trim()),
    onSuccess: () => done(ko.suggestion.approvedToast),
  });
  const reject = useMutation({
    mutationFn: () => api.reject(s.id),
    onSuccess: () => done(ko.suggestion.rejectedToast),
  });

  const closeDialog = () => {
    setDialog(null);
    edit.reset();
    approve.reset();
    reject.reset();
    setAck(false);
  };

  // 서버 규칙과 같다: 차단이거나, 엄격 모드(건강·금융 등)에서 통과가 아니면 승인할 수 없다
  const blocked =
    s.status === 'blocked' ||
    s.validation_result === 'block' ||
    (s.strict && s.validation_result !== 'pass');
  const warned = !blocked && s.validation_result === 'warn';
  // 차단(blocked) 제안도 서버는 수정·반려를 허용한다. 승인만 막는다.
  const open = s.status === 'candidate' || s.status === 'expired' || s.status === 'blocked';
  const canReject = open || s.status === 'approved';
  const canEdit = open || s.status === 'approved';
  const isAi = s.source !== 'manual';
  const blockReasons = s.reasons.filter((r) => r.severity === 'error' || r.severity === 'block');
  const whyList = blockReasons.length > 0 ? blockReasons : s.strict ? s.reasons : [];

  const titleError =
    title.trim() === ''
      ? ko.suggestion.editEmpty
      : title.trim() === s.title
        ? ko.suggestion.editSame
        : charCount(title.trim()) > MAX_TITLE
          ? ko.suggestion.editTooLong
          : undefined;
  const approverError = approver.trim() === '' ? ko.suggestion.approverEmpty : undefined;

  const submitEdit = (e: FormEvent) => {
    e.preventDefault();
    if (!titleError && !edit.isPending) edit.mutate();
  };
  const submitApprove = (e: FormEvent) => {
    e.preventDefault();
    if (!approverError && (!warned || ack) && !blocked && !approve.isPending) approve.mutate();
  };

  const headingId = `sg-${s.id}`;
  return (
    <article className="card suggestion" aria-labelledby={headingId}>
      <div className="suggestion__head">
        <h3 id={headingId} className="card__title">
          {s.title}
        </h3>
      </div>
      <div className="suggestion__head">
        <ValidationBadge result={blocked ? 'block' : s.validation_result} />
        <Badge
          tone={s.status === 'approved' ? 'info' : s.status === 'rejected' ? 'danger' : 'neutral'}
        >
          {suggestionStatusLabel(s.status)}
        </Badge>
        <Badge>
          {s.source === 'manual'
            ? ko.suggestion.manual
            : s.source.endsWith('+edited')
              ? ko.suggestion.aiEdited
              : ko.suggestion.ai}
        </Badge>
        {s.topic && (
          <Badge>{`${ko.suggestion.topic}: ${ko.suggestion.topics[s.topic] ?? s.topic}`}</Badge>
        )}
        {s.strict && (
          <Badge tone="warning" icon="▲">
            {ko.suggestion.strict}
          </Badge>
        )}
        <span className="muted">
          {ko.suggestion.length(s.length)}
          {s.match_ratio !== null && ` · ${ko.suggestion.match(s.match_ratio)}`}
        </span>
      </div>
      {s.strict && <p className="muted">{ko.suggestion.strictHint}</p>}
      {s.strict && (
        <Callout tone="warning">
          <p>{ko.legal.strictCaution}</p>
        </Callout>
      )}
      <div className="legal-note muted">
        {isAi && <p>{ko.legal.aiNotice}</p>}
        <p>{ko.legal.aiLimit}</p>
      </div>

      <div>
        <p className="field__label">{ko.suggestion.compare}</p>
        <TitleDiff before={currentTitle} after={s.title} />
      </div>

      <div>
        <p className="field__label">{ko.suggestion.reasons}</p>
        {s.reasons.length === 0 ? (
          <p className="muted">{ko.suggestion.noReasons}</p>
        ) : (
          <ul className="reasons">
            {s.reasons.map((r, i) => (
              <li key={`${r.code}-${i}`}>
                <span className="sev">[{ko.suggestion.sev[r.severity] ?? r.severity}]</span>{' '}
                {r.message}
              </li>
            ))}
          </ul>
        )}
      </div>
      {s.evidence && (
        <p className="muted">
          <strong>{ko.suggestion.evidence}:</strong> {s.evidence}
        </p>
      )}
      {s.approval && (
        <p>
          <Badge tone="info" icon="✓">
            {ko.suggestion.approvedBy(s.approval.approver, fmtDateTime(s.approval.expires_at))}
          </Badge>
        </p>
      )}
      <p className="muted">{ko.suggestion.createdAt(fmtDateTime(s.created_at))}</p>

      <div className="row">
        {canEdit && (
          <Button
            disabled={disabled}
            onClick={() => {
              setTitle(s.title);
              setDialog('edit');
            }}
          >
            {ko.suggestion.edit}
          </Button>
        )}
        {open && (
          <Button
            variant="primary"
            disabled={disabled || blocked}
            aria-describedby={blocked ? `${headingId}-blocked` : undefined}
            onClick={() => setDialog('approve')}
          >
            {ko.suggestion.approve}
          </Button>
        )}
        {canReject && (
          <Button variant="danger" disabled={disabled} onClick={() => setDialog('reject')}>
            {ko.suggestion.reject}
          </Button>
        )}
      </div>
      {open && blocked && (
        <Callout id={`${headingId}-blocked`} tone="danger" title={ko.suggestion.cannotApproveTitle}>
          <p>{ko.suggestion.approveBlocked}</p>
          {whyList.length > 0 ? (
            <ul>
              {whyList.map((r, i) => (
                <li key={`${r.code}-${i}`}>{r.message}</li>
              ))}
            </ul>
          ) : (
            <p>{ko.suggestion.cannotApproveNoReason}</p>
          )}
          {s.strict && blockReasons.length === 0 && <p>{ko.suggestion.cannotApproveStrict}</p>}
          {canEdit && <p>{ko.suggestion.blockedStatusHint}</p>}
        </Callout>
      )}

      {dialog === 'edit' && (
        <Modal
          title={ko.suggestion.editTitle}
          onClose={closeDialog}
          footer={
            <>
              <Button onClick={closeDialog}>{ko.app.cancel}</Button>
              <Button
                variant="primary"
                type="submit"
                form={`${headingId}-edit`}
                busy={edit.isPending}
                disabled={Boolean(titleError)}
              >
                {ko.app.save}
              </Button>
            </>
          }
        >
          <form id={`${headingId}-edit`} className="stack" onSubmit={submitEdit}>
            <Field
              label={ko.suggestion.editLabel}
              hint={`${ko.suggestion.editHint} (${charCount(title.trim())}/${MAX_TITLE})`}
              error={title !== s.title ? titleError : undefined}
            >
              <input
                className="input"
                value={title}
                data-autofocus=""
                onChange={(e) => setTitle(e.target.value)}
              />
            </Field>
            {edit.isError && <ErrorPanel error={edit.error} />}
          </form>
        </Modal>
      )}
      {dialog === 'approve' && (
        <Modal
          title={ko.suggestion.approveTitle}
          onClose={closeDialog}
          footer={
            <>
              <Button onClick={closeDialog}>{ko.app.cancel}</Button>
              <Button
                variant="primary"
                type="submit"
                form={`${headingId}-approve`}
                busy={approve.isPending}
                disabled={Boolean(approverError) || (warned && !ack)}
              >
                {ko.suggestion.approve}
              </Button>
            </>
          }
        >
          <form id={`${headingId}-approve`} className="stack" onSubmit={submitApprove}>
            <TitleDiff before={currentTitle} after={s.title} />
            <div className="legal-note">
              {isAi && <p>{ko.legal.aiNotice}</p>}
              <p>{ko.legal.aiLimit}</p>
              {s.strict && <p>{ko.legal.strictCaution}</p>}
              <p>{ko.legal.disclaimer}</p>
            </div>
            {warned && (
              <Callout tone="warning" title={ko.validation.warn}>
                <ul>
                  {s.reasons.map((r, i) => (
                    <li key={i}>{r.message}</li>
                  ))}
                </ul>
                <label className="check">
                  <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                  {ko.suggestion.warnAck}
                </label>
              </Callout>
            )}
            <Field
              label={ko.suggestion.approverLabel}
              hint={ko.suggestion.approverHint}
              error={approverError}
            >
              <input
                className="input"
                value={approver}
                data-autofocus=""
                onChange={(e) => setApprover(e.target.value)}
                maxLength={40}
              />
            </Field>
            {approve.isError && <ErrorPanel error={approve.error} />}
          </form>
        </Modal>
      )}
      {dialog === 'reject' && (
        <Modal
          title={ko.suggestion.rejectTitle}
          onClose={closeDialog}
          footer={
            <>
              <Button onClick={closeDialog}>{ko.app.cancel}</Button>
              <Button variant="danger" busy={reject.isPending} onClick={() => reject.mutate()}>
                {ko.suggestion.reject}
              </Button>
            </>
          }
        >
          <p>{ko.suggestion.rejectBody}</p>
          <p className="diff__text">{s.title}</p>
          {reject.isError && <ErrorPanel error={reject.error} />}
        </Modal>
      )}
    </article>
  );
}
