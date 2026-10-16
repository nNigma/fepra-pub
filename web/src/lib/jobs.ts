import { endpoints } from '../api/endpoints';
import type { Job } from '../api/types';

/** Поллинг задачи до done/error. Бросает Error(текст) при status=error или таймауте. */
export async function pollJob(
  id: string,
  opts: { intervalMs?: number; maxTries?: number; signal?: { cancelled: boolean } } = {},
): Promise<Job> {
  const { intervalMs = 2000, maxTries = 150, signal } = opts;
  for (let i = 0; i < maxTries; i++) {
    if (signal?.cancelled) throw new Error('cancelled');
    const j = await endpoints.job(id);
    if (j.status === 'done') return j;
    if (j.status === 'error') throw new Error(j.error || 'error');
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error('timeout');
}

export function inviteUrl(inv: { url?: string; token?: string }, base?: string | null): string {
  if (inv.url) return inv.url;
  const origin = (base || window.location.origin).replace(/\/$/, '');
  return `${origin}/app/#/invite/${inv.token ?? ''}`;
}
