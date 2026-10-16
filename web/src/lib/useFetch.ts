import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import { useSession } from './session';

export interface FetchState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Загрузка данных экрана. Перезапрашивает при смене `key`, админ-режима ?as= и
 * после «Повторить» (epoch). Устаревшие ответы отбрасываются.
 */
export function useFetch<T>(load: (() => Promise<T>) | null, key: string): FetchState<T> {
  const { asUser, epoch } = useSession();
  const [state, setState] = useState<{ data: T | null; error: ApiError | null; loading: boolean }>({
    data: null,
    error: null,
    loading: load != null,
  });
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const fn = loadRef.current;
    if (!fn) return;
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn().then(
      (data) => alive && setState({ data, error: null, loading: false }),
      (e) =>
        alive &&
        setState({
          data: null,
          error: e instanceof ApiError ? e : new ApiError(-1, String(e)),
          loading: false,
        }),
    );
    return () => {
      alive = false;
    };
  }, [key, asUser, epoch, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { ...state, reload };
}
