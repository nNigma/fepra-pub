import { ApiError } from '../../api/client';

type TFn = (key: string, params?: Record<string, string | number | null | undefined>) => string;

const QUOTA_RE = /квот|лимит|quota|limit|429/i;

export type ErrKind = 'network' | 'quota' | 'timeout' | 'forbidden' | 'validation' | 'other';

export function classifyError(e: unknown): ErrKind {
  if (e instanceof ApiError) {
    if (e.status === 0) return 'network';
    if (e.status === 429) return 'quota';
    if (e.status === 403) return 'forbidden';
    if (e.status === 422 || e.status === 400) return 'validation';
    return 'other';
  }
  const m = e instanceof Error ? e.message : String(e);
  if (m === 'timeout') return 'timeout';
  if (QUOTA_RE.test(m)) return 'quota';
  return 'other';
}

/** Человеческое сообщение об ошибке запроса/задачи. */
export function errText(e: unknown, t: TFn): string {
  const k = classifyError(e);
  const detail = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e);
  switch (k) {
    case 'network': return t('rec.err.network');
    case 'quota': return t('rec.err.quota');
    case 'timeout': return t('rec.err.timeout');
    case 'forbidden': return detail ? t('rec.err.forbidden_detail', { msg: detail }) : t('err.forbidden');
    case 'validation': return t('rec.err.validation', { msg: detail });
    default: return t('err.generic', { msg: detail });
  }
}
