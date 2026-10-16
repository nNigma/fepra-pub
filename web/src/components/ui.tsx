import type { ReactNode } from 'react';
import { ApiError } from '../api/client';
import { useT } from '../i18n';
import type { FetchState } from '../lib/useFetch';

export function Loading() {
  const t = useT();
  return <div className="loading" role="status">{t('common.loading')}</div>;
}

export function ErrorBox({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const t = useT();
  let text: string;
  if (error.status === 403) text = error.detail && /pro/i.test(error.detail) ? t('err.pro') : t('err.forbidden');
  else if (error.status === 404) text = t('err.not_found');
  else text = t('err.generic', { msg: error.detail || error.status });
  return (
    <div className="msg err" role="alert">
      {text}
      {onRetry && error.status !== 403 && error.status !== 404 && (
        <div style={{ marginTop: 8 }}>
          <button type="button" className="btn" onClick={onRetry}>{t('net.retry')}</button>
        </div>
      )}
    </div>
  );
}

/** Обёртка экрана: загрузка / ошибка / данные. */
export function Async<T>({ state, children }: { state: FetchState<T>; children: (d: T) => ReactNode }) {
  if (state.loading && !state.data) return <Loading />;
  if (state.error) return <ErrorBox error={state.error} onRetry={state.reload} />;
  if (!state.data) return null;
  return <>{children(state.data)}</>;
}

export function Card({ children, style, className = '' }: { children: ReactNode; style?: React.CSSProperties; className?: string }) {
  return <div className={`card ${className}`} style={{ marginBottom: 8, ...style }}>{children}</div>;
}

export function SecTitle({ children }: { children: ReactNode }) {
  return (
    <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.5px', opacity: 0.55, margin: '14px 0 8px' }}>
      {children}
    </div>
  );
}

export function Narrative({ blocks }: { blocks: { title: string; body: string; kind?: string }[] }) {
  const kindColor: Record<string, string> = {
    risk: 'var(--red)', advice: '#6f9bd9', verdict: 'var(--green)', section: '#6f9bd9',
    alert: 'var(--red)', warn: 'var(--amber)', info: '#6f9bd9', ok: 'var(--green)',
  };
  return (
    <>
      {blocks.map((n, i) => {
        const col = kindColor[n.kind ?? ''] ?? 'var(--mut)';
        return (
          <div key={i} className="narr-card" style={{ borderLeftColor: col, marginBottom: 7 }}>
            <div className="narr-title" style={{ color: col }}>{n.title}</div>
            <div className="narr-body">{n.body}</div>
          </div>
        );
      })}
    </>
  );
}
