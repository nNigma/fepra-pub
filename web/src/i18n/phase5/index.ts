// Строки фазы 5: по файлу на область (settings, meals, comps, coach, club, admin), RU и EN отдельно.
// Файлы подхватываются автоматически — общие словари не правим.
const ruMods = import.meta.glob('./ru/*.json', { eager: true, import: 'default' }) as Record<string, Record<string, string>>;
const enMods = import.meta.glob('./en/*.json', { eager: true, import: 'default' }) as Record<string, Record<string, string>>;

const merge = (m: Record<string, Record<string, string>>) => Object.assign({}, ...Object.values(m)) as Record<string, string>;

export const ru5 = merge(ruMods);
export const en5 = merge(enMods);
