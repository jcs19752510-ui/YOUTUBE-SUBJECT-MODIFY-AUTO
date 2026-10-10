import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useApi, useApiClient, useConnection } from '../api/context';
import type { SettingsData } from '../api/types';
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorPanel,
  Field,
  Modal,
  PageHead,
  Pagination,
  QueryView,
  TableWrap,
  describeError,
  Tabs,
  useToast,
} from '../components';
import { ko } from '../i18n/ko';
import { fmtDateTime } from '../lib/format';

const T = ko.settings;

function SafetyForm({ data }: { data: SettingsData }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const [cap, setCap] = useState(String(data.daily_apply_cap));
  const [per, setPer] = useState(String(data.suggestions_per_video));
  const [tone, setTone] = useState(data.tone);

  const range = (v: string, a: number, b: number) => {
    const n = Number(v);
    return v.trim() !== '' && Number.isInteger(n) && n >= a && n <= b
      ? undefined
      : T.rangeError(a, b);
  };
  const capErr = range(cap, 1, 20);
  const perErr = range(per, 1, 5);
  const toneErr = tone.trim() === '' ? T.toneEmpty : undefined;
  const changed =
    Number(cap) !== data.daily_apply_cap ||
    Number(per) !== data.suggestions_per_video ||
    tone.trim() !== data.tone;

  const m = useMutation({
    mutationFn: () =>
      api.patchSettings({
        daily_apply_cap: Number(cap),
        suggestions_per_video: Number(per),
        tone: tone.trim(),
      }),
    onSuccess: (d) => {
      qc.setQueryData(['settings'], d);
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
      toast.push('success', T.saved);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!capErr && !perErr && !toneErr && changed && !m.isPending) m.mutate();
  };
  return (
    <form className="stack" onSubmit={submit}>
      <Card title={T.safetyTitle}>
        <div className="stack form-narrow">
          <Field label={T.dailyCap} hint={T.dailyCapHint} error={capErr}>
            <input
              className="input"
              type="number"
              inputMode="numeric"
              min={1}
              max={20}
              value={cap}
              onChange={(e) => setCap(e.target.value)}
            />
          </Field>
          <Field label={T.perVideo} hint={T.perVideoHint} error={perErr}>
            <input
              className="input"
              type="number"
              inputMode="numeric"
              min={1}
              max={5}
              value={per}
              onChange={(e) => setPer(e.target.value)}
            />
          </Field>
          <Field label={T.tone} hint={T.toneHint} error={toneErr}>
            <input
              className="input"
              value={tone}
              maxLength={40}
              onChange={(e) => setTone(e.target.value)}
            />
          </Field>
          {m.isError && <ErrorPanel error={m.error} />}
          <div>
            <Button
              type="submit"
              variant="primary"
              busy={m.isPending}
              disabled={!changed || Boolean(capErr || perErr || toneErr)}
            >
              {ko.app.save}
            </Button>
          </div>
        </div>
      </Card>
      <Card title={T.readonlyTitle}>
        <Callout tone="info">
          <p>{T.readonlyWhy}</p>
        </Callout>
        <dl className="kv readonly-kv">
          <dt>{T.liveLabel}</dt>
          <dd>
            <Badge
              tone={data.live_enabled ? 'danger' : 'success'}
              icon={data.live_enabled ? '▲' : '✓'}
            >
              {data.live_enabled ? T.liveOn : T.liveOff}
            </Badge>{' '}
            <span className="muted">{T.readonlyNote}</span>
          </dd>
          <dt>{T.allowedLabel}</dt>
          <dd>
            {data.allowed_video_ids.length === 0 ? (
              T.allowedNone
            ) : (
              <ul className="reasons">
                {data.allowed_video_ids.map((id) => (
                  <li key={id} className="mono">
                    {id}
                  </li>
                ))}
              </ul>
            )}{' '}
            <span className="muted">{T.readonlyNote}</span>
          </dd>
        </dl>
      </Card>
    </form>
  );
}

function PinCard({ data }: { data: SettingsData }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const [pin, setPin] = useState('');
  const [again, setAgain] = useState('');
  const [clearOpen, setClearOpen] = useState(false);
  const pinErr = pin !== '' && pin.length < 4 ? T.pinShort : undefined;
  const againErr = again !== '' && again !== pin ? T.pinMismatch : undefined;
  const ok = pin.length >= 4 && pin === again;
  const save = useMutation({
    mutationFn: () => api.patchSettings({ pin }),
    onSuccess: (d) => {
      qc.setQueryData(['settings'], d);
      setPin('');
      setAgain('');
      toast.push('success', T.pinSaved);
    },
  });
  const clear = useMutation({
    mutationFn: () => api.patchSettings({ pin: null }),
    onSuccess: (d) => {
      qc.setQueryData(['settings'], d);
      setClearOpen(false);
      toast.push('success', T.pinCleared);
    },
  });
  return (
    <Card title={T.pinTitle}>
      <form
        className="stack form-narrow"
        onSubmit={(e) => {
          e.preventDefault();
          if (ok && !save.isPending) save.mutate();
        }}
      >
        <p>
          <Badge tone={data.pin_set ? 'success' : 'neutral'} icon={data.pin_set ? '✓' : '–'}>
            {T.pinState(data.pin_set)}
          </Badge>
        </p>
        <Field label={T.pinNew} hint={T.pinNewHint} error={pinErr}>
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
          />
        </Field>
        <Field label={T.pinConfirm} error={againErr}>
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={again}
            onChange={(e) => setAgain(e.target.value)}
          />
        </Field>
        {save.isError && <ErrorPanel error={save.error} />}
        <div className="row">
          <Button type="submit" variant="primary" busy={save.isPending} disabled={!ok}>
            {data.pin_set ? T.pinChange : T.pinSet}
          </Button>
          {data.pin_set && (
            <Button variant="danger" onClick={() => setClearOpen(true)}>
              {T.pinClear}
            </Button>
          )}
        </div>
      </form>
      {clearOpen && (
        <Modal
          title={T.pinClearTitle}
          onClose={() => setClearOpen(false)}
          footer={
            <>
              <Button onClick={() => setClearOpen(false)}>{ko.app.cancel}</Button>
              <Button variant="danger" busy={clear.isPending} onClick={() => clear.mutate()}>
                {T.pinClear}
              </Button>
            </>
          }
        >
          <p>{T.pinClearBody}</p>
          {clear.isError && <ErrorPanel error={clear.error} />}
        </Modal>
      )}
    </Card>
  );
}

function SessionCard() {
  const api = useApi();
  const client = useApiClient();
  const conn = useConnection();
  const toast = useToast();
  const g = useQuery({ queryKey: ['google'], queryFn: () => api.google() });
  return (
    <Card title={T.sessionTitle}>
      <dl className="kv">
        <dt>{T.sessionServer}</dt>
        <dd>
          <Badge
            tone={conn.state === 'online' ? 'success' : 'danger'}
            icon={conn.state === 'online' ? '●' : '○'}
          >
            {conn.state === 'online' ? ko.conn.online : ko.conn.offline}
          </Badge>
        </dd>
        <dt>{T.sessionMode}</dt>
        <dd>{T.sessionModeDemo}</dd>
        <dt>{T.sessionGoogle}</dt>
        <dd>
          {g.isPending ? (
            ko.app.loading
          ) : g.isError ? (
            <ErrorPanel error={g.error} />
          ) : (
            <>{g.data.message}</>
          )}
        </dd>
      </dl>
      <p />
      <Button
        onClick={() =>
          void client
            .logout()
            .catch((e: unknown) =>
              toast.push('error', describeError(e).detail || describeError(e).title),
            )
        }
      >
        {T.sessionLogout}
      </Button>
    </Card>
  );
}

function AuditCard() {
  const api = useApi();
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ['audit', page],
    queryFn: () => api.audit({ page, page_size: 50 }),
    placeholderData: (p) => p,
  });
  return (
    <Card title={T.auditTitle}>
      <QueryView query={q} lines={5}>
        {(d) => (
          <div className="stack">
            <Badge tone={d.chain_ok ? 'success' : 'danger'} icon={d.chain_ok ? '✓' : '✕'}>
              {d.chain_ok ? T.auditChainOk : T.auditChainBad}
            </Badge>
            {d.items.length === 0 ? (
              <EmptyState title={T.auditEmpty} />
            ) : (
              <>
                <TableWrap label={T.auditTitle}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">{T.colTime}</th>
                        <th scope="col">{T.colActor}</th>
                        <th scope="col">{T.colAction}</th>
                        <th scope="col">{T.colTarget}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.items.map((a) => (
                        <tr key={a.id}>
                          <td className="nowrap">{fmtDateTime(a.ts)}</td>
                          <td>{a.actor}</td>
                          <td>{a.action}</td>
                          <td className="mono">
                            {[a.target_type, a.target_id].filter(Boolean).join(' ')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TableWrap>
                <Pagination page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} />
              </>
            )}
          </div>
        )}
      </QueryView>
    </Card>
  );
}

const TAB_IDS = ['safety', 'pin', 'session', 'audit'] as const;

export function SettingsPage() {
  const api = useApi();
  const [sp, setSp] = useSearchParams();
  const raw = sp.get('tab') ?? 'safety';
  const tab = (TAB_IDS as readonly string[]).includes(raw) ? raw : 'safety';
  const q = useQuery({ queryKey: ['settings'], queryFn: () => api.settings() });
  const items = TAB_IDS.map((id) => ({ id, label: T.tabs[id] }));
  return (
    <>
      <PageHead title={T.title} subtitle={T.subtitle} />
      <Tabs
        items={items}
        value={tab}
        label={T.tabsLabel}
        onChange={(id) => setSp({ tab: id }, { replace: true })}
      >
        {tab === 'session' ? (
          <SessionCard />
        ) : tab === 'audit' ? (
          <AuditCard />
        ) : (
          <QueryView query={q} lines={5}>
            {(d) =>
              tab === 'pin' ? (
                <PinCard data={d} />
              ) : (
                <SafetyForm
                  key={`${d.daily_apply_cap}|${d.suggestions_per_video}|${d.tone}`}
                  data={d}
                />
              )
            }
          </QueryView>
        )}
      </Tabs>
    </>
  );
}
