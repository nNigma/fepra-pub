import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError, onNetworkError, onUnauthorized, setAsUser } from '../api/client';
import { endpoints } from '../api/endpoints';
import type { Me } from '../api/types';
import { useI18n } from '../i18n';

export type SessionStatus = 'loading' | 'anon' | 'authed';

interface SessionCtx {
  status: SessionStatus;
  me: Me | null;
  offline: boolean;
  /** счётчик перезагрузок: ключ для перемонтирования экранов после «Повторить» */
  epoch: number;
  /** id пользователя в админ-режиме ?as= */
  asUser: string | null;
  setAs: (id: string | null) => void;
  refresh: () => Promise<void>;
  retry: () => void;
  signedOut: () => void;
}

const Ctx = createContext<SessionCtx | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const { setLang } = useI18n();
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [me, setMe] = useState<Me | null>(null);
  const [offline, setOffline] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const [asUser, setAsState] = useState<string | null>(null);

  const setAs = useCallback((id: string | null) => {
    setAsUser(id);
    setAsState(id);
  }, []);

  const signedOut = useCallback(() => {
    setMe(null);
    setAs(null);
    setStatus('anon');
  }, [setAs]);

  const refresh = useCallback(async () => {
    try {
      const m = await endpoints.me();
      setMe(m);
      if (m.lang === 'ru' || m.lang === 'en') setLang(m.lang);
      if (!m.roles?.admin) setAs(null);
      setStatus('authed');
      setOffline(false);
    } catch (e) {
      if (e instanceof ApiError && e.isNetwork) return; // экран «нет соединения» покажет networkHandler
      setMe(null);
      setStatus('anon');
    }
  }, [setLang, setAs]);

  useEffect(() => {
    onUnauthorized(() => signedOut());
    onNetworkError(() => setOffline(true));
    void refresh();
    const online = () => setOffline(false);
    window.addEventListener('online', online);
    return () => {
      onUnauthorized(null);
      onNetworkError(null);
      window.removeEventListener('online', online);
    };
  }, [refresh, signedOut]);

  const retry = useCallback(() => {
    setOffline(false);
    setEpoch((n) => n + 1);
    void refresh();
  }, [refresh]);

  const value = useMemo<SessionCtx>(
    () => ({ status, me, offline, epoch, asUser, setAs, refresh, retry, signedOut }),
    [status, me, offline, epoch, asUser, setAs, refresh, retry, signedOut],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('SessionProvider отсутствует');
  return v;
}
