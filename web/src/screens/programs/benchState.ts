import type { ExerciseBlock, FinishResult, SessionView, SetPut, SetRow } from '../../api/programs';

// Локальное состояние сессии «у помоста». Сервер — источник правды; здесь лежат только
// отметки, которые ещё не подтверждены (pending), таймер отдыха и черновик финиша.

const PREFIX = 'fepra.bench.';
const MAX_AGE_MS = 7 * 24 * 3600 * 1000;

export interface LocalSet {
  done_kg: number | null;
  ok: boolean | null;
  ts: string;
  /** PUT ещё не подтверждён сервером: при загрузке отправим повторно */
  pending: boolean;
}
export interface LocalSession {
  v: 1;
  sid: string;
  sets: Record<string, LocalSet>;
  restEnd: number | null;
  restLabel: string | null;
  checkinSkipped: boolean;
  activityId: string;
  finished: FinishResult | null;
  updated: number;
}

export function emptyLocal(sid: string, activityId: string): LocalSession {
  return { v: 1, sid, sets: {}, restEnd: null, restLabel: null, checkinSkipped: false, activityId, finished: null, updated: Date.now() };
}

export function loadLocal(sid: string): LocalSession | null {
  try {
    const raw = localStorage.getItem(PREFIX + sid);
    if (!raw) return null;
    const j = JSON.parse(raw) as LocalSession;
    return j && j.v === 1 && j.sid === sid ? j : null;
  } catch {
    return null;
  }
}

export function saveLocal(s: LocalSession): void {
  try {
    localStorage.setItem(PREFIX + s.sid, JSON.stringify({ ...s, updated: Date.now() }));
  } catch {
    /* хранилище недоступно или переполнено: сервер всё равно источник правды */
  }
}

export function clearLocal(sid: string): void {
  try {
    localStorage.removeItem(PREFIX + sid);
  } catch {
    /* ignore */
  }
}

/** Удалить старые локальные сессии (вызывается при открытии экрана). */
export function pruneLocal(now = Date.now()): void {
  try {
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (!k?.startsWith(PREFIX)) continue;
      try {
        const j = JSON.parse(localStorage.getItem(k) ?? '{}') as { updated?: number };
        if (!j.updated || now - j.updated > MAX_AGE_MS) localStorage.removeItem(k);
      } catch {
        localStorage.removeItem(k);
      }
    }
  } catch {
    /* ignore */
  }
}

export function allSets(s: Pick<SessionView, 'blocks' | 'extra_sets'>): SetRow[] {
  return [...s.blocks.flatMap((b) => b.exercises.flatMap((e) => e.sets)), ...(s.extra_sets ?? [])];
}

/** Накладываем непринятые локальные отметки на ответ сервера (сервер выигрывает, если у него отметка уже есть и у нас нет pending). */
export function overlayLocal(session: SessionView, local: LocalSession | null): SessionView {
  if (!local) return session;
  const patch = (row: SetRow): SetRow => {
    const l = local.sets[row.id];
    if (!l) return row;
    if (row.ok != null && !l.pending) return row;
    return { ...row, done_kg: l.done_kg, ok: l.ok, ts: l.ts };
  };
  return {
    ...session,
    blocks: session.blocks.map((b) => ({ ...b, exercises: b.exercises.map((e): ExerciseBlock => ({ ...e, sets: e.sets.map(patch) })) })),
    extra_sets: (session.extra_sets ?? []).map(patch),
  };
}

/** Отметки, которые нужно отправить повторно: pending и (на сервере ещё нет отметки или она отличается). */
export function pendingPuts(session: SessionView, local: LocalSession | null): { setId: string; body: SetPut }[] {
  if (!local) return [];
  const out: { setId: string; body: SetPut }[] = [];
  for (const row of allSets(session)) {
    const l = local.sets[row.id];
    if (!l?.pending) continue;
    if (row.ok === l.ok && row.done_kg === l.done_kg) continue; // сервер уже в курсе
    out.push({ setId: row.id, body: { done_kg: l.done_kg, ok: l.ok, reps: row.reps, ts: l.ts } });
  }
  return out;
}

export interface PlanDiff {
  id: string;
  lift: string;
  from: number;
  to: number;
}

/**
 * Что бэкенд пересчитал после «не вышло»: сравниваем плановые веса до и после (в ответе PUT
 * приходят только id изменённых подходов — `changed`, новые веса берём из повторного GET).
 */
export function diffPlanned(before: SessionView, after: SessionView, changed?: string[]): PlanDiff[] {
  const prev = new Map<string, number | null>();
  for (const s of allSets(before)) prev.set(s.id, s.planned_kg);
  const out: PlanDiff[] = [];
  for (const b of after.blocks) {
    for (const ex of b.exercises) {
      for (const s of ex.sets) {
        if (changed && !changed.includes(s.id)) continue;
        const was = prev.get(s.id);
        if (was != null && s.planned_kg != null && was !== s.planned_kg) {
          out.push({ id: s.id, lift: ex.lift, from: was, to: s.planned_kg });
        }
      }
    }
  }
  return out;
}

/** Первый неотмеченный подход — «текущий». */
export function currentSet(s: SessionView): SetRow | null {
  return allSets(s).find((r) => r.ok == null) ?? null;
}

export function progress(s: SessionView): { done: number; total: number } {
  const all = allSets(s);
  return { done: all.filter((r) => r.ok != null).length, total: all.length };
}

export interface DiffGroup extends Omit<PlanDiff, 'id'> {
  count: number;
}

/** Одинаковые изменения (лифт, было, стало) сворачиваем: «42.5 → 37.5 ×4». */
export function groupDiffs(diffs: PlanDiff[]): DiffGroup[] {
  const out: DiffGroup[] = [];
  for (const d of diffs) {
    const g = out.find((x) => x.lift === d.lift && x.from === d.from && x.to === d.to);
    if (g) g.count++;
    else out.push({ lift: d.lift, from: d.from, to: d.to, count: 1 });
  }
  return out;
}
