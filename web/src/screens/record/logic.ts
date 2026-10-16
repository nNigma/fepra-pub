// Чистая логика формы записи: маска времени, разбор «вес×повторы», сборка тела PUT.
import {
  BOARD_SPORTS, type CardioUnit, type FieldType, type TimeUnit, type FormField, type FormValue, type PutBody, type ResultForm,
} from '../../api/record';
import type { Draft } from './draft';

// ---------- время мм:сс ----------

/** Маска ввода: «412» -> «4:12», «1234» -> «12:34»; при ручном «:» цифры не перестраиваем. */
export function maskTime(raw: string): string {
  const s = raw.replace(/[^\d:]/g, '');
  if (s.includes(':')) {
    const [m, ...rest] = s.split(':');
    const secRaw = rest.join('');
    // секунд больше двух: цифры дописывали к уже расставленной маске («1:50» + «0» = «1:500»).
    // Это не ручной ввод — пересчитываем все цифры заново: «1:500» -> «15:00», а не «1:50».
    if (secRaw.length > 2) return maskTime(s.replace(/:/g, ''));
    return `${m.slice(0, 3)}:${secRaw}`;
  }
  const d = s.slice(0, 5);
  return d.length <= 2 ? d : `${d.slice(0, -2)}:${d.slice(-2)}`;
}

/** «4:12» / «12:34» / «1:02:03» / «7» (= 7 минут) -> секунды. Невалидное -> null. */
export function timeToSeconds(raw: string): number | null {
  const s = raw.trim();
  if (!s) return null;
  if (/^\d{1,2}$/.test(s)) return Number(s) * 60;
  if (/^\d{3,5}$/.test(s)) return Number(s.slice(0, -2)) * 60 + Number(s.slice(-2));
  const m = /^(?:(\d{1,2}):)?(\d{1,3}):(\d{1,2})$/.exec(s);
  if (!m) return null;
  const h = m[1] ? Number(m[1]) : 0;
  const mm = Number(m[2]);
  const ss = Number(m[3]);
  if (ss > 59 || (m[1] && mm > 59)) return null;
  return h * 3600 + mm * 60 + ss;
}

export function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** Канонический вид «м:сс» или '' если не разобрали. */
export function normalizeTime(raw: string): string {
  const sec = timeToSeconds(raw);
  return sec == null ? '' : formatTime(sec);
}

// ---------- вес × повторы ----------

const SEP = /[x×хХX*]/; // латинская x, ×, кириллическая х, *

const num = (s: string) => Number(s.replace(',', '.'));
const fmtNum = (n: number) => String(Math.round(n * 100) / 100);

export interface WeightReps {
  weight: number;
  reps: number | null;
}

/** «100x5», «82,5 × 3», «100 х 5», «100» (повторы не указаны). */
export function parseWeightReps(raw: string): WeightReps | null {
  const m = /^\s*(\d+(?:[.,]\d+)?)\s*(?:[x×хХX*]\s*(\d{1,4}))?\s*$/.exec(raw);
  if (!m) return null;
  const weight = num(m[1]);
  const reps = m[2] != null ? Number(m[2]) : null;
  if (weight > 1000 || (reps != null && (reps < 1 || reps > 1000))) return null;
  return { weight, reps };
}

export function canonWeightReps(w: WeightReps): string {
  return w.reps == null ? fmtNum(w.weight) : `${fmtNum(w.weight)}x${w.reps}`;
}

/** Разбить значение поля на два инпута: «100x5» -> ['100','5']. Вставка «100x5» в поле веса тоже делится. */
export function splitPair(v: string, sep: 'x' | '+'): [string, string] {
  const re = sep === 'x' ? SEP : /\+/;
  const i = v.search(re);
  if (i < 0) return [v, ''];
  return [v.slice(0, i).trim(), v.slice(i + 1).trim()];
}
export function joinPair(a: string, b: string, sep: 'x' | '+'): string {
  const x = a.trim();
  const y = b.trim();
  if (!x && !y) return '';
  if (sep === '+') return y ? `${x || '0'}+${y}` : x;
  return y ? `${x}x${y}` : x;
}

// ---------- rounds+reps ----------

export function parseRoundsReps(raw: string): string | number | null {
  const m = /^\s*(\d{1,4})\s*(?:\+\s*(\d{1,4}))?\s*$/.exec(raw);
  if (!m) return null;
  return m[2] != null ? `${Number(m[1])}+${Number(m[2])}` : Number(m[1]);
}

// ---------- сборка form_result ----------

export type FieldError =
  | 'weight_reps' | 'weight' | 'time' | 'int' | 'rounds_reps' | 'text'
  | 'cardio' | 'weight_distance' | 'reps_load';

export interface BuiltForm {
  result: Record<string, FormValue>;
  errors: Record<string, FieldError>;
  filled: number;
}

// ---------- составные поля (кардио, сани, повторы с весом) ----------
// В состоянии формы это строки: кардио «kcal:22» / «m:250» / «time:0:40»; пары «вес|второе».

export const CARDIO_UNITS: CardioUnit[] = ['kcal', 'm', 'sec', 'min'];
export const TIME_UNITS: TimeUnit[] = ['sec', 'min'];

export function parseCardio(raw: string, def?: CardioUnit | null): { unit: CardioUnit; value: string } {
  const m = /^(kcal|m|sec|min):(.*)$/.exec(raw ?? '');
  if (m) return { unit: m[1] as CardioUnit, value: m[2] };
  const old = /^time:(\d{1,3}):(\d{2})$/.exec(raw ?? '');   // прежний формат «время мм:сс» -> секунды
  if (old) return { unit: 'sec', value: String(Number(old[1]) * 60 + Number(old[2])) };
  return { unit: def ?? 'kcal', value: raw ?? '' };
}
/** Прежнее «время мм:сс» (первые сохранения кардио) -> секунды. */
function legacyTime(mmss: string): string {
  const m = /^(\d{1,3}):(\d{2})$/.exec(mmss.trim());
  return m ? joinCardio('sec', String(Number(m[1]) * 60 + Number(m[2]))) : '';
}
export function joinCardio(unit: CardioUnit, value: string): string {
  return `${unit}:${value}`;
}

export function splitBar(v: string): [string, string] {
  const i = (v ?? '').indexOf('|');
  return i < 0 ? [v ?? '', ''] : [v.slice(0, i).trim(), v.slice(i + 1).trim()];
}
export function joinBar(a: string, b: string): string {
  const x = a.trim();
  const y = b.trim();
  return !x && !y ? '' : `${x}|${y}`;
}

export function buildCardio(raw: string, def?: CardioUnit | null): { value: FormValue | null; error?: FieldError } {
  const { unit, value } = parseCardio(raw, def);
  const v = value.trim();
  if (!v) return { value: null };
  const n = parseDecimal(v);
  return n == null ? { value: null, error: 'cardio' } : { value: { unit, value: n } };
}

/** Сани: «вес|метры|время|ед.времени» (ед. времени: sec | min). */
export function splitSled(v: string): [string, string, string, TimeUnit] {
  const p = (v ?? '').split('|');
  const u = (p[3] ?? '').trim();
  return [(p[0] ?? '').trim(), (p[1] ?? '').trim(), (p[2] ?? '').trim(), u === 'min' ? 'min' : 'sec'];
}
export function joinSled(w: string, d: string, t: string, u: TimeUnit): string {
  return !w.trim() && !d.trim() && !t.trim() ? '' : `${w.trim()}|${d.trim()}|${t.trim()}|${u}`;
}

export function buildWeightDistance(raw: string): { value: FormValue | null; error?: FieldError } {
  const [w, d, t, u] = splitSled(raw);
  if (!w && !d && !t) return { value: null };
  const wn = w ? parseDecimal(w) : null;
  const dn = d ? parseDecimal(d) : null;
  const tn = t ? parseDecimal(t) : null;
  if ((w && wn == null) || (d && dn == null) || (t && tn == null)) return { value: null, error: 'weight_distance' };
  const out: Record<string, number | string> = {};
  if (wn != null) out.weight = wn;
  if (dn != null) out.meters = dn;
  if (tn != null) { out.time = tn; out.time_unit = u; }
  return { value: out };
}

export function buildRepsLoad(raw: string): { value: FormValue | null; error?: FieldError } {
  const [w, r] = splitBar(raw);
  if (!w && !r) return { value: null };
  const rn = r && /^\d{1,4}$/.test(r) ? Number(r) : null;
  const wn = w ? parseDecimal(w) : null;
  if (rn == null || rn < 1 || (w && wn == null)) return { value: null, error: 'reps_load' };
  return { value: wn != null ? { reps: rn, weight: wn } : { reps: rn } };
}

export function buildFieldValue(
  type: FieldType,
  raw: string,
  repsDefault?: number | null,
  defaultUnit?: CardioUnit | null,
): { value: FormValue | null; error?: FieldError } {
  if (type === 'cardio') return buildCardio(raw ?? '', defaultUnit);
  if (type === 'weight_distance') return buildWeightDistance(raw ?? '');
  if (type === 'reps_load') return buildRepsLoad(raw ?? '');
  const v = (raw ?? '').trim();
  if (!v) return { value: null };
  switch (type) {
    case 'weight_reps': {
      if (/^[x×хХX*]\s*\d*$/.test(v)) return { value: null };   // веса нет — подход не выполнялся
      const p = parseWeightReps(v);
      if (!p) return { value: null, error: 'weight_reps' };
      // повторы не трогали — берём по схеме; изменили — уйдёт то, что ввёл атлет
      if (p.reps == null && repsDefault) p.reps = repsDefault;
      return { value: canonWeightReps(p) };
    }
    case 'weight': {
      if (/^\d+(?:[.,]\d+)?$/.test(v)) return { value: num(v) };
      // «16/24», «2x16» — как написал атлет, сервер принимает строку
      return /^[\d.,/\-+x×хХX\s]{1,24}$/.test(v) ? { value: v } : { value: null, error: 'weight' };
    }
    case 'time': {
      const n = normalizeTime(v);
      return n ? { value: n } : { value: null, error: 'time' };
    }
    case 'int':
      return /^\d{1,5}$/.test(v) ? { value: Number(v) } : { value: null, error: 'int' };
    case 'rounds_reps': {
      const r = parseRoundsReps(v);
      return r == null ? { value: null, error: 'rounds_reps' } : { value: r };
    }
    default:
      return { value: v.slice(0, 500) };
  }
}

/** Значения формы (строки как в инпутах) -> тело form_result. Пустые поля не присылаем. */
export function buildFormResult(form: ResultForm | null | undefined, values: Record<string, string>): BuiltForm {
  const out: BuiltForm = { result: {}, errors: {}, filled: 0 };
  for (const b of form?.blocks ?? []) {
    for (const f of b.fields) {
      const r = buildFieldValue(f.type, values[f.key] ?? '', f.reps_default, f.default_unit);
      if (r.error) out.errors[f.key] = r.error;
      else if (r.value != null) {
        out.result[f.key] = r.value;
        out.filled++;
      }
    }
  }
  return out;
}

/** Обратно: то, что сервер хранит в form_values, -> строка для инпута. */
export function valueToString(type: FieldType, v: unknown): string {
  if (v == null || v === '') return '';
  if (type === 'weight_reps') {
    if (Array.isArray(v)) return joinPair(String(v[0] ?? ''), String(v[1] ?? ''), 'x');
    if (typeof v === 'object') {
      const o = v as { weight?: unknown; reps?: unknown };
      return joinPair(String(o.weight ?? ''), String(o.reps ?? ''), 'x');
    }
    return String(v);
  }
  if (type === 'cardio') {
    if (typeof v === 'object' && !Array.isArray(v)) {
      const o = v as { unit?: unknown; value?: unknown };
      const u = String(o.unit ?? 'kcal');
      if (u === 'time') return legacyTime(String(o.value ?? ''));
      return joinCardio(CARDIO_UNITS.includes(u as CardioUnit) ? (u as CardioUnit) : 'kcal', String(o.value ?? ''));
    }
    const m = /^\s*([\d.,:]+)\s*(ккал|м|сек|мин|время)?\s*$/i.exec(String(v));
    if (!m) return String(v);
    const w = m[2]?.toLowerCase();
    if (w === 'время') return legacyTime(m[1]);
    const unit: CardioUnit = w === 'м' ? 'm' : w === 'сек' ? 'sec' : w === 'мин' ? 'min' : 'kcal';
    return joinCardio(unit, m[1]);
  }
  if (type === 'weight_distance') {
    if (typeof v === 'object' && !Array.isArray(v)) {
      const o = v as { weight?: unknown; meters?: unknown; time?: unknown; time_unit?: unknown };
      return joinSled(String(o.weight ?? ''), String(o.meters ?? ''), String(o.time ?? ''), o.time_unit === 'min' ? 'min' : 'sec');
    }
    return String(v);
  }
  if (type === 'reps_load') {
    if (typeof v === 'object' && !Array.isArray(v)) {
      const o = v as { reps?: unknown; weight?: unknown };
      return joinBar(String(o.weight ?? ''), String(o.reps ?? ''));
    }
    const p = parseWeightReps(String(v));
    return p && p.reps != null ? joinBar(String(p.weight), String(p.reps)) : joinBar('', String(v));
  }
  if (type === 'time') {
    if (typeof v === 'number') return formatTime(v);
    return String(v);
  }
  if (type === 'rounds_reps' && typeof v === 'object' && !Array.isArray(v)) {
    const o = v as { rounds?: unknown; reps?: unknown };
    return joinPair(String(o.rounds ?? ''), String(o.reps ?? ''), '+');
  }
  return String(v);
}

export function valuesFromServer(form: ResultForm | null | undefined, fv: Record<string, unknown> | null | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  if (!form || !fv) return out;
  for (const b of form.blocks) for (const f of b.fields) if (f.key in fv) out[f.key] = valueToString(f.type, fv[f.key]);
  return out;
}

// ---------- группировка полей блока ----------

export function groupFields(fields: FormField[]): { group: string | null; fields: FormField[] }[] {
  const out: { group: string | null; fields: FormField[] }[] = [];
  for (const f of fields) {
    const g = f.group ?? null;
    const last = out[out.length - 1];
    if (last && last.group === g) last.fields.push(f);
    else out.push({ group: g, fields: [f] });
  }
  return out;
}

// ---------- тело PUT ----------

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

export function parseDecimal(s: string): number | null {
  const v = s.trim().replace(',', '.');
  if (!/^\d+(\.\d+)?$/.test(v)) return null;
  return Number(v);
}

export function isBoardSport(s: string): boolean {
  return (BOARD_SPORTS as string[]).includes(s);
}

export interface PutBuild {
  body: PutBody;
  errors: Record<string, FieldError>;
}

/** Черновик -> тело PUT /api/workouts/{uuid}. Правила — docs/pwa/api-workouts-examples.md §3. */
export function buildPutBody(d: Draft): PutBuild {
  const body: PutBody = { day: d.day, sport: d.sport };
  let errors: Record<string, FieldError> = {};
  if (HHMM.test(d.startTime)) body.start_time = d.startTime;
  if (d.rpe != null) body.rpe = d.rpe;
  if (d.scaling) body.scaling = d.scaling;
  const bw = parseDecimal(d.bodyweight);
  if (bw != null) body.bodyweight = bw;

  if (isBoardSport(d.sport)) {
    if (d.source === 'free') {
      if (d.freeText.trim()) body.form_result = d.freeText.trim();
    } else if (d.source === 'gym') {
      body.board = { source: 'gym', ...(d.gymName ? { gym: d.gymName } : {}) };
      const b = buildFormResult(d.parse?.form, d.values);
      errors = b.errors;
      if (b.filled) body.form_result = b.result;
    } else if (d.parse) {
      body.board = {
        text: d.parse.board_text ?? d.boardText,
        source: 'own',
        format: d.parse.format ?? undefined,
        blocks: d.parse.blocks,
        blocks_verified: d.parse.blocks_verified,
      };
      const b = buildFormResult(d.parse.form, d.values);
      errors = b.errors;
      if (b.filled) body.form_result = b.result;
    }
  } else {
    const dur = parseDecimal(d.duration);
    if (dur != null) body.duration_min = dur;
    const dist = parseDecimal(d.distance);
    if (dist != null) body.distance_km = dist;
    if (d.freeText.trim()) body.form_result = d.freeText.trim();
  }
  return { body, errors };
}
