import { useState, type FormEvent } from 'react';
import { ApiError } from '../api/client';
import { useApiClient } from '../api/context';
import { Button, Callout, Field } from '../components';
import { describeError } from '../components/ErrorPanel';
import { ko } from '../i18n/ko';

export function PinForm({ onDone }: { onDone?: () => void }) {
  const client = useApiClient();
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || !pin) return;
    setBusy(true);
    setErr(null);
    try {
      await client.submitPin(pin);
      setPin('');
      onDone?.();
    } catch (x) {
      setErr(x);
    } finally {
      setBusy(false);
    }
  };

  const wrongPin = err instanceof ApiError && (err.status === 401 || err.status === 403);
  return (
    <form onSubmit={(e) => void submit(e)} className="stack">
      <Field label={ko.conn.pinLabel} error={wrongPin ? ko.conn.pinWrong : undefined}>
        <input
          className="input"
          type="password"
          inputMode="numeric"
          autoComplete="current-password"
          value={pin}
          data-autofocus=""
          onChange={(e) => setPin(e.target.value)}
        />
      </Field>
      {err !== null && !wrongPin && (
        <Callout tone="danger" role="alert" title={describeError(err).title}>
          <p>{describeError(err).detail || describeError(err).hint}</p>
        </Callout>
      )}
      <Button type="submit" variant="primary" busy={busy} disabled={!pin}>
        {ko.conn.pinSubmit}
      </Button>
    </form>
  );
}
