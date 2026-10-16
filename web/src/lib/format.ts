import type { Level } from '../api/types';

export const LEVEL_COLORS: Record<Level, [string, string]> = {
  green: ['var(--greenb)', 'var(--green)'],
  amber: ['var(--amberb)', 'var(--amber)'],
  red: ['var(--redb)', 'var(--red)'],
};

export function levelColors(level: string | undefined): [string, string] {
  return LEVEL_COLORS[(level as Level) ?? 'green'] ?? LEVEL_COLORS.green;
}

/** цвет по readiness 0..100 */
export function tier(r: number | null | undefined): [string, string] {
  if (r == null) return ['var(--card)', 'var(--mut)'];
  return r >= 70 ? LEVEL_COLORS.green : r >= 45 ? LEVEL_COLORS.amber : LEVEL_COLORS.red;
}

export const fmt = (x: number | null | undefined): string | number =>
  x == null ? '—' : Math.round(x * 10) / 10;

export const delta = (d: number | null | undefined): string =>
  d == null ? '' : `${d >= 0 ? '+' : ''}${fmt(d)}`;

export function deltaColor(d: number | null | undefined, hiBad: boolean): string {
  if (d == null) return 'var(--mut)';
  const bad = hiBad ? d > 0 : d < 0;
  return bad ? 'var(--red)' : 'var(--green)';
}

/** «мм:сс» -> секунды */
export function scoreSec(s: string | null | undefined): number | null {
  const m = /^(\d+):(\d{2})$/.exec(s ?? '');
  return m ? +m[1] * 60 + +m[2] : null;
}

export function mmss(secs: number | null | undefined): string {
  if (secs == null || secs < 0) return '—';
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

export function shortDate(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

/** эмодзи-префикс строки «🟢 Хорошо» */
export function splitEmoji(s: string): { emoji: string; label: string } {
  const i = s.indexOf(' ');
  return i > 0 ? { emoji: s.slice(0, i), label: s.slice(i + 1) } : { emoji: s, label: s };
}

export const AXES_KEYS = ['Движок', 'Сила', 'Гимнастика', 'Над головой', 'Спринт', 'Хват/тяга'];
export const AXES_T_KEYS = [
  'axis.engine',
  'axis.strength',
  'axis.gymnastics',
  'axis.overhead',
  'axis.sprint',
  'axis.grip_pull',
];
export const METRIC_IDS = [
  'readiness', 'hrv', 'rhr', 'sleep', 'bb', 'sleep_score', 'spo2', 'respiration',
  'sleep_deep', 'sleep_rem', 'vo2max', 'acwr', 'load_debt', 'monotony', 'strain',
];
