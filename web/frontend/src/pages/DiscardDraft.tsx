import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useApi } from '../api/context';
import { Button, ErrorPanel, Modal, useToast } from '../components';
import { ko } from '../i18n/ko';

/** 초안 배치를 버린다(서버 cancel). 초안에는 반영된 변경이 없어 제목은 바뀌지 않고, 담긴 제안은 다시 쓸 수 있게 풀린다. */
export function DiscardDraftButton({ batchId, size }: { batchId: number; size?: 'sm' | 'md' }) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const m = useMutation({
    mutationFn: () => api.cancelBatch(batchId),
    onSuccess: (b) => {
      qc.setQueryData(['batch', batchId], b);
      setOpen(false);
      toast.push('success', ko.batches.discardedToast);
      void qc.invalidateQueries({ queryKey: ['batch', batchId] });
      void qc.invalidateQueries({ queryKey: ['batches'] });
      void qc.invalidateQueries({ queryKey: ['suggestions'] });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
  const close = () => {
    if (m.isPending) return;
    setOpen(false);
    m.reset();
  };
  return (
    <>
      <Button size={size} onClick={() => setOpen(true)}>
        {ko.batches.discard}
        <span className="sr-only">{ko.batches.discardAria(batchId)}</span>
      </Button>
      {open && (
        <Modal
          title={ko.batches.discardTitle}
          onClose={close}
          closeDisabled={m.isPending}
          footer={
            <>
              <Button onClick={close} disabled={m.isPending}>
                {ko.app.cancel}
              </Button>
              <Button variant="danger" busy={m.isPending} onClick={() => m.mutate()}>
                {ko.batches.discardConfirm}
              </Button>
            </>
          }
        >
          <p>{ko.batches.discardBody}</p>
          {m.isError && <ErrorPanel error={m.error} />}
        </Modal>
      )}
    </>
  );
}
