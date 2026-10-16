// Черновик записи тренировки в localStorage: обновление страницы не теряет введённое.
import type { Engine, ParseResult, SaveResponse, Scaling, Sport } from '../../api/record';

export type Step = 'setup' | 'board' | 'check' | 'result' | 'done';
export type Source = 'photo' | 'text' | 'gym' | 'free';

export interface Draft {
  v: 1;
  uuid: string;
  step: Step;
  day: string;
  sport: Sport;
  startTime: string;
  source: Source | null;
  engine: Engine;
  uploadId: string | null;
  uploadName: string;
  boardText: string;
  parse: ParseResult | null;
  gymDay: string | null;
  gymName?: string | null;
  values: Record<string, string>;
  rpe: number | null;
  scaling: Scaling;
  bodyweight: string;
  freeText: string;
  duration: string;
  distance: string;
  saved: SaveResponse | null;
  savedAt: number;
}

export const DRAFT_KEY = 'fepra.record.draft.v1';
const TTL_MS = 3 * 24 * 3600 * 1000;

export function newUuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  // запасной вариант для очень старых браузеров (не-secure контекст)
  const h = (n: number) => Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join('');
  return `${h(8)}-${h(4)}-4${h(3)}-${'89ab'[Math.floor(Math.random() * 4)]}${h(3)}-${h(12)}`;
}

export function isoDay(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${dd}`;
}
export function todayIso(now = new Date()): string {
  return isoDay(now);
}
export function yesterdayIso(now = new Date()): string {
  const d = new Date(now);
  d.setDate(d.getDate() - 1);
  return isoDay(d);
}
export function nowHHMM(now = new Date()): string {
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}

export function newDraft(now = new Date(), sport: Sport = 'crossfit'): Draft {
  return {
    v: 1,
    uuid: newUuid(),
    step: 'setup',
    day: todayIso(now),
    sport,
    startTime: nowHHMM(now),
    source: null,
    engine: 'fast',
    uploadId: null,
    uploadName: '',
    boardText: '',
    parse: null,
    gymDay: null,
    values: {},
    rpe: null,
    scaling: null,
    bodyweight: '',
    freeText: '',
    duration: '',
    distance: '',
    saved: null,
    savedAt: now.getTime(),
  };
}

export function saveDraft(d: Draft, now = Date.now()): void {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...d, savedAt: now }));
  } catch {
    /* переполнено или недоступно — черновик необязателен */
  }
}

export function loadDraft(now = Date.now()): Draft | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const d = JSON.parse(raw) as Draft;
    if (!d || d.v !== 1 || typeof d.uuid !== 'string' || typeof d.day !== 'string') return null;
    if (now - (d.savedAt ?? 0) > TTL_MS) {
      clearDraft();
      return null;
    }
    return d;
  } catch {
    return null;
  }
}

export function clearDraft(): void {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* ignore */
  }
}

/** Есть ли в черновике что-то, ради чего стоит предлагать «продолжить». */
export function draftHasContent(d: Draft): boolean {
  return (
    d.step !== 'setup' ||
    Object.values(d.values).some((v) => v) ||
    !!d.boardText ||
    !!d.freeText ||
    !!d.uploadId ||
    d.rpe != null
  );
}
