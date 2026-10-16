import { useEffect, useRef } from 'react';
import { pollJob } from './jobs';

export interface CancelFlag {
  cancelled: boolean;
}

/** Флаг «экран закрыт»: поллинг задач прерывается при размонтировании. */
export function useCancelFlag(): CancelFlag {
  const ref = useRef<CancelFlag>({ cancelled: false });
  useEffect(() => {
    const f = ref.current;
    f.cancelled = false;
    return () => {
      f.cancelled = true;
    };
  }, []);
  return ref.current;
}

/** Запустить задачу (POST -> job_id) и дождаться результата. */
export async function runJob<T>(
  start: () => Promise<{ job_id: string }>,
  opts: { intervalMs?: number; maxTries?: number; signal?: CancelFlag } = {},
): Promise<T> {
  const { job_id } = await start();
  const j = await pollJob(job_id, { intervalMs: 1500, ...opts });
  return j.result as T;
}
