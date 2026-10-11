import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

/** 영상 목록의 일괄 선택. 페이지를 넘겨도 유지되도록 목록 컴포넌트 밖(메모리)에 둔다. */
interface SelectionApi {
  ids: string[];
  has: (id: string) => boolean;
  toggle: (id: string, title: string) => void;
  setMany: (items: { id: string; title: string }[], on: boolean) => void;
  clear: () => void;
  titleOf: (id: string) => string | undefined;
}
const Ctx = createContext<SelectionApi | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [map, setMap] = useState<Map<string, string>>(new Map());
  const toggle = useCallback((id: string, title: string) => {
    setMap((m) => {
      const n = new Map(m);
      if (n.has(id)) n.delete(id);
      else n.set(id, title);
      return n;
    });
  }, []);
  const setMany = useCallback((items: { id: string; title: string }[], on: boolean) => {
    setMap((m) => {
      const n = new Map(m);
      for (const it of items) {
        if (on) n.set(it.id, it.title);
        else n.delete(it.id);
      }
      return n;
    });
  }, []);
  const clear = useCallback(() => setMap(new Map()), []);
  const api = useMemo<SelectionApi>(
    () => ({
      ids: Array.from(map.keys()),
      has: (id) => map.has(id),
      toggle,
      setMany,
      clear,
      titleOf: (id) => map.get(id),
    }),
    [map, toggle, setMany, clear],
  );
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export function useSelection(): SelectionApi {
  const v = useContext(Ctx);
  if (!v) throw new Error('SelectionProvider 가 필요합니다');
  return v;
}
