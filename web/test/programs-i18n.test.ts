import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import programs from '../src/i18n/programs.json';
import { DICTS } from '../src/i18n';

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : /\.tsx?$/.test(f) ? [p] : [];
  });
}

describe('i18n программ', () => {
  it('RU и EN совпадают по ключам, нет пустых строк', () => {
    expect(Object.keys(programs.ru).sort()).toEqual(Object.keys(programs.en).sort());
    for (const v of [...Object.values(programs.ru), ...Object.values(programs.en)]) expect(v.length).toBeGreaterThan(0);
  });
  it('все статические ключи pg.* / push.* / notice.* из кода есть в словарях', () => {
    const used = new Set<string>();
    for (const f of [...files('src/screens/programs'), 'src/components/Shell.tsx']) {
      for (const m of readFileSync(f, 'utf8').matchAll(/\bt\('((?:pg|push|notice|tab)\.[a-z_.0-9]+)'/g)) used.add(m[1]);
    }
    expect(used.size).toBeGreaterThan(50);
    for (const k of used) {
      expect(DICTS.ru[k], k).toBeTruthy();
      expect(DICTS.en[k], k).toBeTruthy();
    }
  });
  it('динамические семейства ключей заведены', () => {
    for (const fam of [
      ['pg.level.', ['careful', 'normal', 'experienced']], ['pg.week.', ['volume', 'medium', 'high', 'deload', 'test']],
      ['pg.status.', ['active', 'paused', 'cancelled', 'done']], ['pg.today.', ['today', 'in_progress', 'upcoming', 'overdue', 'none', 'paused', 'cancelled', 'done']],
      ['pg.trend.', ['up', 'flat', 'down', 'none']], ['pg.ci.', ['joint', 'tired', 'sleepy', 'ill']],
      ['pg.src.', ['best', 'derived', 'starter', 'needs_input', 'user', 'test', 'unknown']], ['push.err.', ['unsupported', 'denied', 'no_key', 'failed']],
    ] as [string, string[]][]) {
      for (const s of fam[1]) expect(DICTS.ru[fam[0] + s], fam[0] + s).toBeTruthy();
    }
  });
});
