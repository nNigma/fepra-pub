import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import { endpoints } from '../api/endpoints';
import type { LlmStatus } from '../api/types';
import { useT } from '../i18n';
import { useSession } from '../lib/session';
import { ReviewText } from './Review';

type Phase =
  | { k: 'loading' }
  | { k: 'idle' }
  | { k: 'thinking' }
  | { k: 'pending' }
  | { k: 'pending_long' }
  | { k: 'error'; msg: string }
  | { k: 'done' };

interface Props {
  kind: string;
  refKey: string;
  pro: boolean;
  /** вызывается после генерации (сводка обновляет совет) */
  onDone?: () => void;
  pollMs?: number;
  maxPolls?: number;
}

/** Разбор ИИ: GET статус -> кнопка -> POST запуск -> поллинг GET, пока кэш не наполнится. */
export function LlmBlock({ kind, refKey, pro, onDone, pollMs = 4000, maxPolls = 50 }: Props) {
  const t = useT();
  const { asUser, epoch } = useSession();
  const [phase, setPhase] = useState<Phase>({ k: 'loading' });
  const [cached, setCached] = useState<LlmStatus['cached']>(null);
  const [stale, setStale] = useState(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    if (!pro) return;
    let ok = true;
    setPhase({ k: 'loading' });
    endpoints.llmStatus(kind, refKey).then(
      (d) => {
        if (!ok) return;
        setCached(d.cached);
        setStale(!!d.stale);
        setPhase(d.cached ? { k: 'done' } : { k: 'idle' });
      },
      () => ok && setPhase({ k: 'idle' }),
    );
    return () => {
      ok = false;
    };
  }, [kind, refKey, pro, asUser, epoch]);

  const run = useCallback(
    async (refresh: boolean) => {
      setPhase({ k: 'thinking' });
      let res;
      try {
        res = await endpoints.llmRun(kind, refKey, refresh);
      } catch (e) {
        const err = e as ApiError;
        if (err.status === 403) return setPhase({ k: 'error', msg: t('llm.need_pro') });
        if (err.status === 429)
          return setPhase({ k: 'error', msg: t('llm.limit_prefix', { detail: err.detail || t('llm.limit_default') }) });
        return setPhase({ k: 'error', msg: t('llm.unavailable') });
      }
      if (res.text) {
        setCached({ text: res.text, engine: res.engine ?? '' });
        setStale(false);
        setPhase({ k: 'done' });
        onDone?.();
        return;
      }
      if (!res.pending) return setPhase({ k: 'error', msg: t('llm.unavailable') });
      setPhase({ k: 'pending' });
      for (let i = 0; i < maxPolls; i++) {
        await new Promise((r) => setTimeout(r, pollMs));
        if (!alive.current) return;
        try {
          const d = await endpoints.llmStatus(kind, refKey);
          if (d.cached?.text) {
            setCached(d.cached);
            setStale(false);
            setPhase({ k: 'done' });
            onDone?.();
            return;
          }
        } catch {
          /* следующая попытка */
        }
      }
      if (alive.current) setPhase({ k: 'pending_long' });
    },
    [kind, refKey, t, onDone, pollMs, maxPolls],
  );

  if (!pro) return <div className="mut" style={{ margin: '10px 2px', fontSize: 12 }}>{t('llm.pro_only')}</div>;

  const head = <div className="llmhead">{t('llm.head')}</div>;
  const engine = cached?.engine;
  const sig = engine
    ? engine === 'claude' || engine === 'agent'
      ? t('llm.by_claude')
      : t('llm.by_gemini')
    : '';

  let body;
  switch (phase.k) {
    case 'loading':
      body = <div className="mut">{t('common.loading')}</div>;
      break;
    case 'thinking':
      body = <div className="mut">{t('llm.thinking')}</div>;
      break;
    case 'pending':
      body = <div className="mut">{t('llm.pending')}</div>;
      break;
    case 'pending_long':
      body = <div className="mut">{t('llm.pending_long')}</div>;
      break;
    case 'error':
      body = <div className="mut">{phase.msg}</div>;
      break;
    case 'done':
      body = (
        <>
          {stale && <span className="review-stale">🟡 {t('llm.stale')}</span>}
          {sig && <div className="mut" style={{ fontSize: 11.5, margin: '1px 0 7px' }}>{sig}</div>}
          {cached && <ReviewText text={cached.text} className="llmtext" />}
          <button type="button" className="llmbtn" onClick={() => void run(true)}>{t('llm.refresh')}</button>
        </>
      );
      break;
    default:
      body = <button type="button" className="llmbtn" onClick={() => void run(false)}>{t('llm.run')}</button>;
  }
  return <div className="llmwrap" data-testid={`llm-${kind}`}>{head}{body}</div>;
}
