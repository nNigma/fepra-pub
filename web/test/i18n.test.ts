import { describe, expect, it } from 'vitest';
import { DICTS, translate } from '../src/i18n';
import { mdLite, splitAstro } from '../src/lib/markdown';

const ph = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',');

describe('i18n RU/EN', () => {
  it('наборы ключей совпадают', () => {
    const ru = Object.keys(DICTS.ru).sort();
    const en = Object.keys(DICTS.en).sort();
    expect(ru.filter((k) => !(k in DICTS.en))).toEqual([]);
    expect(en.filter((k) => !(k in DICTS.ru))).toEqual([]);
  });
  it('плейсхолдеры {x} совпадают в парах', () => {
    const bad = Object.keys(DICTS.ru).filter((k) => ph(DICTS.ru[k]) !== ph(DICTS.en[k] ?? ''));
    expect(bad).toEqual([]);
  });
  it('нет пустых строк', () => {
    for (const l of ['ru', 'en'] as const) {
      const empty = Object.entries(DICTS[l]).filter(([, v]) => !v.trim()).map(([k]) => k);
      expect(empty).toEqual([]);
    }
  });
  it('подстановка параметров и fallback на ключ', () => {
    expect(translate('ru', 'garmin.error', { msg: 'x' })).toContain('x');
    expect(translate('en', 'нет.такого.ключа')).toBe('нет.такого.ключа');
    expect(translate('ru', 'garmin.error', {})).toContain('{msg}');
  });
  it('текст про Garmin содержит обещание про пароль', () => {
    expect(DICTS.ru['garmin.privacy']).toMatch(/пароль не сохраняется/i);
    expect(DICTS.en['garmin.privacy']).toMatch(/not stored/i);
  });
});

describe('markdown-lite', () => {
  it('секции, списки, жирный', () => {
    const s = mdLite('## Итог\n**Хорошо** идёшь\n- раз\n- два');
    expect(s).toHaveLength(1);
    expect(s[0].heading).toBe('Итог');
    expect(s[0].blocks[0]).toMatchObject({ kind: 'p' });
    expect(s[0].blocks[1]).toMatchObject({ kind: 'ul' });
  });
  it('HTML не интерпретируется (остаётся текстом)', () => {
    const s = mdLite('<img src=x onerror=alert(1)>');
    expect((s[0].blocks[0] as any).parts[0].text).toContain('<img');
  });
  it('астро-блок вырезается', () => {
    const r = splitAstro('Основа\n🔮 Астро-разбор от Месье Клода:\nзвёзды\nСОВЕТ: спать');
    expect(r.astro).toBe('звёзды');
    expect(r.main).toContain('СОВЕТ: спать');
  });
});
