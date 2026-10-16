import type { SessionView, SetRow, TreeNode } from '../src/api/programs';

const node = (o: Partial<TreeNode> & { slug: string }): TreeNode => ({
  parent: null, kind: 'program', title_ru: o.slug, title_en: o.slug, status: 'active', soon: false, sort: 10,
  template_slug: null, children: [], ...o,
});

export const TREE: TreeNode[] = [
  node({
    slug: 'crossfit', kind: 'sport', title_ru: 'Кроссфит', title_en: 'CrossFit', status: 'planned', soon: true, sort: 10,
    children: [node({ slug: 'crossfit-strength-531', parent: 'crossfit', title_ru: 'Силовой цикл', status: 'planned', soon: true })],
  }),
  node({
    slug: 'weightlifting', kind: 'sport', title_ru: 'ТА', title_en: 'Weightlifting', sort: 20,
    children: [node({
      slug: 'bulgarian', kind: 'system', parent: 'weightlifting', title_ru: 'Болгарская система', title_en: 'Bulgarian system',
      children: [
        node({ slug: 'bulgarian-adaptation', parent: 'bulgarian', title_ru: 'Адаптация', template_slug: 'bulgarian-adaptation', sort: 10 }),
        node({ slug: 'bulgarian-peak-8w', parent: 'bulgarian', title_ru: 'Цикл до теста', template_slug: 'bulgarian-peak-8w', sort: 20 }),
        node({ slug: 'bulgarian-secret', parent: 'bulgarian', title_ru: 'Скрытая', status: 'hidden', sort: 30 }),
      ],
    })],
  }),
  node({ slug: 'running', kind: 'sport', title_ru: 'Бег', title_en: 'Running', status: 'planned', soon: true, sort: 30 }),
];

export function setRow(id: string, n: number, kg: number, o: Partial<SetRow> = {}): SetRow {
  return { id, n, kind: 'ladder', pct: 50 + n * 10, planned_kg: kg, rest_sec: 90, reps: 1, done_kg: null, ok: null, note: null, ts: null, ...o };
}

export function session(o: Partial<SessionView> = {}, sets?: SetRow[]): SessionView {
  const rows = sets ?? [setRow('s1', 0, 40), setRow('s2', 1, 50), setRow('s3', 2, 60)];
  return {
    id: 'sess1', enrollment_id: 'enr1', planned_day: '2026-09-29', week: 3, idx: 1, kind: 'normal', status: 'planned',
    week_type: 'medium', week_title: { ru: 'Неделя 3', en: 'Week 3' }, week_note: null,
    title: { ru: 'Рывок + присед', en: 'Snatch + squat' }, minutes: 40, checkin: { tired: false }, // чек-ин уже был
    adjust: { level: 'none', delta_pct: 0, cap_pct: null, signals: [], postpone_advised: false },
    why: null, why_en: null, activity_id: null,
    blocks: [{ title: { ru: 'Основная часть', en: 'Main' }, exercises: [{ id: 'snatch', lift: 'squat_snatch', name: { ru: 'Рывок в сед', en: 'Squat snatch' }, sets: rows }] }],
    extra_sets: [], misses: [], ...o,
  };
}
