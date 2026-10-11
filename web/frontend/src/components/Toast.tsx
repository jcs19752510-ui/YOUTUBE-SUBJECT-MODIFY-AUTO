import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { ko } from '../i18n/ko';

type ToastTone = 'info' | 'success' | 'error';
interface ToastItem {
  id: number;
  tone: ToastTone;
  text: string;
}
interface ToastApi {
  push: (tone: ToastTone, text: string) => void;
  /** 화면을 옮길 때 오래된 성공·안내 알림을 치운다(오류 알림은 남긴다) */
  clearTransient: () => void;
}
const AUTO_CLOSE_MS = 5000;
const Ctx = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);
  const remove = useCallback((id: number) => setItems((l) => l.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (tone: ToastTone, text: string) => {
      const id = ++seq.current;
      setItems((l) => [...l.slice(-3), { id, tone, text }]);
      if (tone !== 'error') window.setTimeout(() => remove(id), AUTO_CLOSE_MS);
    },
    [remove],
  );
  const clearTransient = useCallback(
    () => setItems((l) => l.filter((t) => t.tone === 'error')),
    [],
  );
  const api = useMemo(() => ({ push, clearTransient }), [push, clearTransient]);
  return (
    <Ctx.Provider value={api}>
      {children}
      {createPortal(
        <div className="toasts">
          {/* 상태 알림은 live region 에 둬서 스크린리더가 읽는다. 오류는 assertive */}
          <div aria-live="polite" role="status">
            {items
              .filter((t) => t.tone !== 'error')
              .map((t) => (
                <div key={t.id} className={`toast toast--${t.tone}`}>
                  <span>{t.text}</span>
                  <button
                    type="button"
                    className="toast__close"
                    onClick={() => remove(t.id)}
                    aria-label={ko.app.close}
                  >
                    ✕
                  </button>
                </div>
              ))}
          </div>
          <div role="alert">
            {items
              .filter((t) => t.tone === 'error')
              .map((t) => (
                <div key={t.id} className="toast toast--error">
                  <span>{t.text}</span>
                  <button
                    type="button"
                    className="toast__close"
                    onClick={() => remove(t.id)}
                    aria-label={ko.app.close}
                  >
                    ✕
                  </button>
                </div>
              ))}
          </div>
        </div>,
        document.body,
      )}
    </Ctx.Provider>
  );
}

export function useToast(): ToastApi {
  const v = useContext(Ctx);
  if (!v) throw new Error('ToastProvider 가 필요합니다');
  return v;
}
