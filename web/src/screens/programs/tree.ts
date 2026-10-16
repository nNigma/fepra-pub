import type { Reference, TreeNode } from '../../api/programs';

export function nodeTitle(n: { title_ru: string; title_en: string }, lang: string): string {
  return lang === 'en' ? n.title_en || n.title_ru : n.title_ru || n.title_en;
}

/** Узел «скоро»: показывается приглушённо, в программу не ведёт. */
export function isPlanned(n: TreeNode): boolean {
  return n.soon || n.status === 'planned';
}

/** Программу можно открыть карточкой, только если она активна и это лист-программа. */
export function isOpenableProgram(n: TreeNode): boolean {
  return n.kind === 'program' && !isPlanned(n) && !!n.template_slug;
}

/** Скрытые узлы не показываем; порядок — по `sort`. */
export function visibleChildren(n: { children: TreeNode[] }): TreeNode[] {
  return n.children.filter((c) => c.status !== 'hidden').sort((a, b) => a.sort - b.sort);
}

export function findNode(tree: TreeNode[], slug: string): TreeNode | null {
  for (const n of tree) {
    if (n.slug === slug) return n;
    const r = findNode(n.children ?? [], slug);
    if (r) return r;
  }
  return null;
}

/** Цепочка от корня до узла (для хлебных крошек); пусто, если узла нет. */
export function pathTo(tree: TreeNode[], slug: string): TreeNode[] {
  for (const n of tree) {
    if (n.slug === slug) return [n];
    const sub = pathTo(n.children ?? [], slug);
    if (sub.length) return [n, ...sub];
  }
  return [];
}

/** Сколько активных программ под узлом (для подписи «N программ»). */
export function countPrograms(n: TreeNode, onlyActive = false): number {
  if (n.status === 'hidden') return 0;
  if (n.kind === 'program') return onlyActive && isPlanned(n) ? 0 : 1;
  return n.children.reduce((s, c) => s + countPrograms(c, onlyActive), 0);
}

export type SourceKind = 'best' | 'derived' | 'starter' | 'needs_input' | 'user' | 'test';

/** Ключ i18n подписи источника опорного веса. */
export function sourceKey(ref: Pick<Reference, 'source'>): string {
  const known: SourceKind[] = ['best', 'derived', 'starter', 'needs_input', 'user', 'test'];
  return known.includes(ref.source as SourceKind) ? `pg.src.${ref.source}` : 'pg.src.unknown';
}

/** Пометка «устарел» только для результатов, которые реально измерены/выведены. */
export function isStale(ref: Pick<Reference, 'source' | 'stale'>): boolean {
  return !!ref.stale && (ref.source === 'best' || ref.source === 'derived');
}

/** Локализованное поле {ru, en}; на входе может быть и обычная строка. */
export function loc(v: { ru?: string; en?: string } | string | null | undefined, lang: string): string {
  if (v == null) return '';
  if (typeof v === 'string') return v;
  return (lang === 'en' ? v.en || v.ru : v.ru || v.en) ?? '';
}

export function fmtKg(kg: number | null | undefined): string {
  if (kg == null) return '—';
  return Number.isInteger(kg) ? String(kg) : String(Math.round(kg * 10) / 10);
}

export function fmtDay(iso: string | null | undefined): string {
  return iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}` : '';
}
