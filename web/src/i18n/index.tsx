import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import legacyRu from './legacy.ru.json';
import legacyEn from './legacy.en.json';
import { ru } from './ru';
import { en } from './en';
import { ru5, en5 } from './phase5';
import type { Lang } from '../api/types';

// Словари экранов лежат рядом файлами `<область>.json` вида {"ru": {...}, "en": {...}}
// (programs.json, record.json, …). Подхватываются автоматически: новая область не
// требует правки этого файла.
const areaModules = import.meta.glob<{ ru: Record<string, string>; en: Record<string, string> }>(
  ['./*.json', '!./legacy.*.json'],
  { eager: true, import: 'default' },
);
const areaRu: Record<string, string> = {};
const areaEn: Record<string, string> = {};
for (const m of Object.values(areaModules)) {
  Object.assign(areaRu, m.ru);
  Object.assign(areaEn, m.en);
}

export const DICTS: Record<Lang, Record<string, string>> = {
  ru: { ...(legacyRu as Record<string, string>), ...ru, ...areaRu, ...ru5 },
  en: { ...(legacyEn as Record<string, string>), ...en, ...areaEn, ...en5 },
};

export type Params = Record<string, string | number | null | undefined>;

export function translate(lang: Lang, key: string, params?: Params): string {
  const raw = DICTS[lang][key] ?? DICTS.ru[key] ?? key;
  if (!params) return raw;
  return raw.replace(/\{(\w+)\}/g, (m, k: string) => (params[k] == null ? m : String(params[k])));
}

const LS_KEY = 'fepra.lang';

export function detectLang(): Lang {
  try {
    const v = localStorage.getItem(LS_KEY);
    if (v === 'ru' || v === 'en') return v;
  } catch {
    /* localStorage недоступен */
  }
  return 'ru'; // RU по умолчанию
}

interface Ctx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, params?: Params) => string;
}

const I18nCtx = createContext<Ctx>({ lang: 'ru', setLang: () => {}, t: (k) => k });

export function I18nProvider({ children, initial }: { children: ReactNode; initial?: Lang }) {
  const [lang, setLangState] = useState<Lang>(initial ?? detectLang());
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(LS_KEY, l);
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  const value = useMemo<Ctx>(
    () => ({ lang, setLang, t: (k, p) => translate(lang, k, p) }),
    [lang, setLang],
  );
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n(): Ctx {
  return useContext(I18nCtx);
}
export function useT() {
  return useContext(I18nCtx).t;
}
