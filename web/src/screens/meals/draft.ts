// Состояние черновика приёма пищи. Сервер без состояния: клиент держит черновик и накопленные уточнения (notes).
import type { Food, MealDraft, MealParseResult, ParseRequest, SaveRequest } from '../../api/meals';

export interface DraftSource {
  kind: 'photo' | 'text';
  upload_id?: string | null;
  url?: string | null;
  text?: string | null;
  meal_id?: number;
}

export interface DraftState {
  source: DraftSource | null;
  draft: MealDraft | null;
  notes: string[];
  status: 'idle' | 'parsing' | 'ready' | 'failed';
  reason: MealParseResult['reason'];
  uuid: string;
}

export type DraftAction =
  | { type: 'start'; source: DraftSource }
  | { type: 'parsing' }
  | { type: 'parsed'; result: MealParseResult; correction?: string }
  | { type: 'failed'; reason?: MealParseResult['reason'] }
  | { type: 'load'; draft: MealDraft; source: DraftSource }
  | { type: 'food'; index: number; patch: Partial<Food> }
  | { type: 'addFood' }
  | { type: 'removeFood'; index: number }
  | { type: 'reset' };

export function newUuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  const h = (n: number) => Math.floor(Math.random() * 16 ** n).toString(16).padStart(n, '0');
  return `${h(8)}-${h(4)}-4${h(3)}-a${h(3)}-${h(12)}`;
}

export const initialDraft = (uuid = newUuid()): DraftState => ({
  source: null, draft: null, notes: [], status: 'idle', reason: null, uuid,
});

const NUM_KEYS = ['kcal', 'protein_g', 'fat_g', 'carb_g'] as const;
const round1 = (x: number) => Math.round(x * 10) / 10;

/** пересчёт тоталов из блюд (сервер пересчитает сам, здесь — для показа) */
export function totalsOf(foods: Food[]): NonNullable<MealDraft['totals']> {
  const t = { kcal: 0, protein_g: 0, fat_g: 0, carb_g: 0 };
  for (const f of foods) for (const k of NUM_KEYS) t[k] += Number(f[k]) || 0;
  return { kcal: Math.round(t.kcal), protein_g: round1(t.protein_g), fat_g: round1(t.fat_g), carb_g: round1(t.carb_g) };
}

/** уточнения копятся без дублей подряд и пустых строк */
export function addNote(notes: string[], correction: string | undefined): string[] {
  const c = (correction ?? '').trim();
  if (!c || notes[notes.length - 1] === c) return notes;
  return [...notes, c];
}

const withTotals = (d: MealDraft, foods: Food[]): MealDraft => ({ ...d, foods, totals: totalsOf(foods) });

export function draftReducer(s: DraftState, a: DraftAction): DraftState {
  switch (a.type) {
    case 'start':
      return { ...initialDraft(s.uuid), source: a.source, status: 'parsing' };
    case 'parsing':
      return { ...s, status: 'parsing', reason: null };
    case 'parsed': {
      const r = a.result;
      // не разобралось: прежний черновик (если был) остаётся, причина — для показа
      if (!r.recognized || !r.draft) return { ...s, status: s.draft ? 'ready' : 'failed', reason: r.reason ?? 'not_recognized' };
      // сервер отдаёт обновлённый notes; если не отдал — добавляем уточнение сами
      const notes = Array.isArray(r.notes) && r.notes.length ? r.notes : addNote(s.notes, a.correction);
      return {
        ...s, draft: r.draft, notes, status: 'ready', reason: null,
        source: { ...(s.source ?? { kind: r.source.kind }), ...r.source },
      };
    }
    case 'failed':
      // ранее разобранный черновик не теряем: уточнение не удалось, но прошлый результат остаётся
      return { ...s, status: s.draft ? 'ready' : 'failed', reason: a.reason ?? 'not_recognized' };
    case 'load':
      return { ...initialDraft(s.uuid), draft: a.draft, source: a.source, status: 'ready' };
    case 'food': {
      if (!s.draft) return s;
      const foods = s.draft.foods.map((f, i) => (i === a.index ? { ...f, ...a.patch } : f));
      return { ...s, draft: withTotals(s.draft, foods) };
    }
    case 'addFood': {
      if (!s.draft) return s;
      const foods = [...s.draft.foods, { name: '', grams: null, kcal: 0, protein_g: 0, fat_g: 0, carb_g: 0 }];
      return { ...s, draft: withTotals(s.draft, foods) };
    }
    case 'removeFood': {
      if (!s.draft) return s;
      return { ...s, draft: withTotals(s.draft, s.draft.foods.filter((_, i) => i !== a.index)) };
    }
    case 'reset':
      return initialDraft();
  }
}

/** Тело POST /api/meals/parse: источник + уточнение + накопленные notes. */
export function buildParseRequest(s: DraftState, correction?: string): ParseRequest {
  const src = s.source;
  const body: ParseRequest = {};
  if (src?.kind === 'photo' && src.upload_id) body.upload_id = src.upload_id;
  if (src?.text) body.text = src.text;      // текст-описание: сам по себе или к фото
  const c = (correction ?? '').trim();
  if (c) {
    body.correction = c;
    body.notes = s.notes;
  }
  return body;
}

/** Тело POST /api/meals: клиентский UUID делает повтор запроса идемпотентным. */
export function buildSaveRequest(s: DraftState, day?: string): SaveRequest {
  const body: SaveRequest = { draft: s.draft as MealDraft, uuid: s.uuid };
  if (day) body.day = day;
  const src = s.source;
  if (src?.kind === 'photo' && src.upload_id) body.upload_id = src.upload_id;
  if (src?.text) body.text = src.text;
  return body;
}

/** валидность черновика для кнопки «Сохранить»: есть блюдо, у каждого имя */
export function canSave(s: DraftState): boolean {
  return s.status === 'ready' && !!s.draft && s.draft.foods.length > 0 && s.draft.foods.every((f) => f.name.trim() !== '');
}
