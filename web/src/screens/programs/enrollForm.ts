import type { EnrollBody, Reference, StartLevel } from '../../api/programs';

export const LEVELS: StartLevel[] = ['careful', 'normal', 'experienced'];

/** Разбор веса из поля: «82,5» и «82.5» -> 82.5; вне 0..500 или мусор -> null. */
export function parseKg(s: string | undefined): number | null {
  if (!s) return null;
  const v = Number(s.replace(',', '.').trim());
  return Number.isFinite(v) && v > 0 && v <= 500 ? v : null;
}

export interface EnrollState {
  startDay: string;
  level: StartLevel | null;
  manual: Record<string, string>;
  id: string;
}

/** Тело POST enroll: ручные максимумы -> base_maxes, выбранный уровень -> level. */
export function buildEnrollBody(s: EnrollState): EnrollBody {
  const body: EnrollBody = { start_day: s.startDay, id: s.id };
  const bm: Record<string, number> = {};
  for (const [lift, raw] of Object.entries(s.manual)) {
    const kg = parseKg(raw);
    if (kg != null) bm[lift] = kg;
  }
  if (Object.keys(bm).length) body.base_maxes = bm;
  if (s.level) body.level = s.level;
  return body;
}

/** Готово ли к записи: для каждого лифта, где нужен ввод, есть ручной вес или выбран уровень. */
export function isEnrollReady(ask: string[], s: EnrollState): boolean {
  if (!s.startDay) return false;
  return ask.every((l) => parseKg(s.manual[l]) != null || s.level != null);
}

/** Какие стартовые уровни есть хотя бы у одного лифта (нет веса тела в профиле -> options нет). */
export function availableLevels(refs: Reference[]): StartLevel[] {
  return LEVELS.filter((lv) => refs.some((r) => r.options?.[lv] != null));
}
