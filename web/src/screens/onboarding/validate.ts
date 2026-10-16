// Клиентская валидация профиля: те же пределы, что в tj/services/profile.py (validate_fields).
import type { ApiError } from '../../api/client';

export const LIMITS = {
  nickMax: 40,
  cityMax: 60,
  height: [100, 250] as [number, number],
  age: [10, 100] as [number, number],
  weight: [20, 400] as [number, number],
};
export const SEX = ['m', 'f'] as const;
export const GOALS = ['cut', 'maintain', 'bulk', 'recomp'] as const;
export const LANGS = ['ru', 'en'] as const;

export type FieldKey = 'nick' | 'height_cm' | 'weight_kg' | 'sex' | 'age' | 'gym' | 'goal' | 'city' | 'lang';

export interface FormValues {
  nick: string; height_cm: string; weight_kg: string; sex: string; age: string;
  gym: string; goal: string; city: string; lang: string;
}
export interface Ranges {
  height: [number, number]; age: [number, number]; weight: [number, number];
}

/** ключ i18n ошибки + параметры */
export interface FieldError {
  key: string;
  params?: Record<string, string | number>;
}

function num(s: string): number {
  const t = String(s ?? '').trim().replace(',', '.');
  if (t === '' || !/^-?\d+(\.\d+)?$/.test(t)) return NaN;
  return Number(t);
}

export function validateField(
  key: FieldKey,
  raw: string,
  opts: { gyms?: string[]; ranges?: Ranges } = {},
): FieldError | null {
  const r = opts.ranges ?? LIMITS;
  const v = String(raw ?? '').trim();
  switch (key) {
    case 'nick':
      return v && v.length <= LIMITS.nickMax ? null : { key: 'ob.err.nick', params: { max: LIMITS.nickMax } };
    case 'city':
      return v && v.length <= LIMITS.cityMax ? null : { key: 'ob.err.city', params: { max: LIMITS.cityMax } };
    case 'height_cm': {
      const n = num(v);
      return Number.isInteger(n) && n >= r.height[0] && n <= r.height[1] ? null : { key: 'ob.err.height', params: { min: r.height[0], max: r.height[1] } };
    }
    case 'age': {
      const n = num(v);
      return Number.isInteger(n) && n >= r.age[0] && n <= r.age[1] ? null : { key: 'ob.err.age', params: { min: r.age[0], max: r.age[1] } };
    }
    case 'weight_kg': {
      const n = num(v);
      return Number.isFinite(n) && n >= r.weight[0] && n <= r.weight[1] ? null : { key: 'ob.err.weight', params: { min: r.weight[0], max: r.weight[1] } };
    }
    case 'sex':
      return (SEX as readonly string[]).includes(v) ? null : { key: 'ob.err.sex' };
    case 'gym':
      return v && (!opts.gyms || opts.gyms.includes(v)) ? null : { key: 'ob.err.gym' };
    case 'goal':
      return (GOALS as readonly string[]).includes(v) ? null : { key: 'ob.err.goal' };
    case 'lang':
      return (LANGS as readonly string[]).includes(v) ? null : { key: 'ob.err.lang' };
  }
}

export function validateFields(
  keys: FieldKey[],
  values: FormValues,
  opts: { gyms?: string[]; ranges?: Ranges } = {},
): Partial<Record<FieldKey, FieldError>> {
  const out: Partial<Record<FieldKey, FieldError>> = {};
  for (const k of keys) {
    const e = validateField(k, values[k], opts);
    if (e) out[k] = e;
  }
  return out;
}

/** значения формы -> тело PATCH (только перечисленные поля, числа приведены) */
export function toPatch(keys: FieldKey[], values: FormValues): Record<string, string | number> {
  const p: Record<string, string | number> = {};
  for (const k of keys) {
    const v = String(values[k] ?? '').trim();
    if (k === 'height_cm' || k === 'age') p[k] = Math.round(num(v));
    else if (k === 'weight_kg') p[k] = Math.round(num(v) * 100) / 100;
    else p[k] = v;
  }
  return p;
}

/** Разбор 422 `{detail, fields}`: поля -> сообщения; общая строка только если полей нет. */
export function parseFieldErrors(err: unknown): { fields: Record<string, string>; general: string | null } {
  const e = err as Partial<ApiError> | undefined;
  const fields = e && e.fields && typeof e.fields === 'object' ? { ...e.fields } : {};
  if (Object.keys(fields).length > 0) return { fields, general: null };
  return { fields, general: e?.detail || (e as Error | undefined)?.message || null };
}

/** Шаги мастера: шаг показывается, если в нём чего-то не хватает; шаг «extra» необязательный, но идёт последним всегда. */
export const STEPS: { id: string; fields: FieldKey[]; optional?: boolean }[] = [
  { id: 'nick', fields: ['nick'] },
  { id: 'body', fields: ['height_cm', 'weight_kg', 'sex', 'age'] },
  { id: 'gym', fields: ['gym'] },
  { id: 'extra', fields: ['goal', 'city', 'lang'], optional: true },
];

export function stepsFor(missing: string[]): typeof STEPS {
  return STEPS.filter((s) => s.optional || s.fields.some((f) => missing.includes(f)));
}
