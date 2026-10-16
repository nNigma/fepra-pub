import { beforeEach, describe, expect, it } from 'vitest';
import {
  countPrograms, findNode, isOpenableProgram, isPlanned, isStale, pathTo, sourceKey, visibleChildren,
} from '../src/screens/programs/tree';
import {
  diffPlanned, groupDiffs, emptyLocal, loadLocal, overlayLocal, pendingPuts, progress, currentSet, pruneLocal, saveLocal, clearLocal,
} from '../src/screens/programs/benchState';
import { buildEnrollBody, isEnrollReady, parseKg, availableLevels } from '../src/screens/programs/enrollForm';
import { urlBase64ToUint8Array } from '../src/api/pushClient';
import { parsePushPayload, targetUrl } from '../src/push-utils';
import { setRow, session, TREE } from './programs-fixtures';

beforeEach(() => localStorage.clear());

describe('дерево каталога', () => {
  const ta = TREE[1];
  it('planned-узлы: «скоро», в программу не открываются', () => {
    expect(isPlanned(TREE[0])).toBe(true);
    expect(isPlanned(TREE[2])).toBe(true);
    expect(isPlanned(ta)).toBe(false);
    const stub = TREE[0].children[0];
    expect(isPlanned(stub)).toBe(true);
    expect(isOpenableProgram(stub)).toBe(false);
    const prog = findNode(TREE, 'bulgarian-peak-8w')!;
    expect(isOpenableProgram(prog)).toBe(true);
    // система и спорт — не «программа», карточкой не открываются
    expect(isOpenableProgram(ta)).toBe(false);
  });
  it('скрытые узлы не показываются, порядок по sort', () => {
    const sys = findNode(TREE, 'bulgarian')!;
    expect(visibleChildren(sys).map((n) => n.slug)).toEqual(['bulgarian-adaptation', 'bulgarian-peak-8w']);
    expect(visibleChildren({ children: TREE }).map((n) => n.slug)).toEqual(['crossfit', 'weightlifting', 'running']);
  });
  it('хлебные крошки и счётчики', () => {
    expect(pathTo(TREE, 'bulgarian-peak-8w').map((n) => n.slug)).toEqual(['weightlifting', 'bulgarian', 'bulgarian-peak-8w']);
    expect(pathTo(TREE, 'нет')).toEqual([]);
    expect(countPrograms(ta)).toBe(2); // скрытая не считается
    expect(countPrograms(TREE[0], true)).toBe(0);
  });
});

describe('источник опорного веса', () => {
  it('ключи и «устарел»', () => {
    expect(sourceKey({ source: 'best' })).toBe('pg.src.best');
    expect(sourceKey({ source: 'derived' })).toBe('pg.src.derived');
    expect(sourceKey({ source: 'starter' })).toBe('pg.src.starter');
    expect(sourceKey({ source: 'needs_input' })).toBe('pg.src.needs_input');
    expect(sourceKey({ source: 'что-то' as never })).toBe('pg.src.unknown');
    expect(isStale({ source: 'best', stale: true })).toBe(true);
    expect(isStale({ source: 'starter', stale: true })).toBe(false);
  });
});

describe('форма записи', () => {
  it('parseKg', () => {
    expect(parseKg('82,5')).toBe(82.5);
    expect(parseKg('')).toBeNull();
    expect(parseKg('abc')).toBeNull();
    expect(parseKg('900')).toBeNull();
  });
  it('тело: ручные максы -> base_maxes, уровень -> level', () => {
    const b = buildEnrollBody({ startDay: '2026-09-29', level: 'normal', manual: { squat_snatch: '60', jerk: 'x' }, id: 'u1' });
    expect(b).toEqual({ start_day: '2026-09-29', id: 'u1', base_maxes: { squat_snatch: 60 }, level: 'normal' });
  });
  it('готовность: каждому лифту нужен ввод или общий уровень', () => {
    const st = { startDay: '2026-09-29', level: null, manual: { a: '50' }, id: 'x' };
    expect(isEnrollReady(['a', 'b'], st)).toBe(false);
    expect(isEnrollReady(['a', 'b'], { ...st, level: 'careful' })).toBe(true);
    expect(isEnrollReady([], st)).toBe(true);
  });
  it('уровни есть только при options', () => {
    expect(availableLevels([{ lift: 'a', kg: null, source: 'needs_input' }])).toEqual([]);
    expect(availableLevels([{ lift: 'a', kg: null, source: 'needs_input', options: { careful: 34, normal: 48, experienced: 66 } }])).toEqual(['careful', 'normal', 'experienced']);
  });
});

describe('пересчёт после «не вышло»', () => {
  it('diffPlanned показывает только изменённые id с прежним и новым весом', () => {
    const before = session({}, [setRow('a', 0, 60, { ok: false, done_kg: 60 }), setRow('b', 1, 65), setRow('c', 2, 70)]);
    const after = session({}, [setRow('a', 0, 60, { ok: false, done_kg: 60 }), setRow('b', 1, 60), setRow('c', 2, 65)]);
    expect(diffPlanned(before, after, ['b', 'c'])).toEqual([
      { id: 'b', lift: 'squat_snatch', from: 65, to: 60 },
      { id: 'c', lift: 'squat_snatch', from: 70, to: 65 },
    ]);
    expect(diffPlanned(before, after, ['c']).map((d) => d.id)).toEqual(['c']);
    expect(diffPlanned(before, before)).toEqual([]);
    expect(groupDiffs([{ id: '1', lift: 'a', from: 5, to: 4 }, { id: '2', lift: 'a', from: 5, to: 4 }, { id: '3', lift: 'b', from: 5, to: 4 }]))
      .toEqual([{ lift: 'a', from: 5, to: 4, count: 2 }, { lift: 'b', from: 5, to: 4, count: 1 }]);
  });
});

describe('локальное состояние сессии', () => {
  it('сохранение и восстановление, очистка', () => {
    const l = emptyLocal('sess1', 'act-1');
    l.sets.s1 = { done_kg: 40, ok: true, ts: '2026-09-29T10:00:00Z', pending: true };
    l.restEnd = 123456;
    saveLocal(l);
    const back = loadLocal('sess1')!;
    expect(back.sets.s1.done_kg).toBe(40);
    expect(back.restEnd).toBe(123456);
    expect(back.activityId).toBe('act-1');
    clearLocal('sess1');
    expect(loadLocal('sess1')).toBeNull();
  });
  it('битый JSON не ломает загрузку', () => {
    localStorage.setItem('fepra.bench.zzz', '{oops');
    expect(loadLocal('zzz')).toBeNull();
  });
  it('overlay: pending-отметка накладывается на ответ сервера, подтверждённая — уступает серверу', () => {
    const srv = session();
    const l = emptyLocal('sess1', 'a');
    l.sets.s1 = { done_kg: 40, ok: true, ts: 't', pending: true };
    const view = overlayLocal(srv, l);
    expect(view.blocks[0].exercises[0].sets[0].ok).toBe(true);
    expect(progress(view)).toEqual({ done: 1, total: 3 });
    expect(currentSet(view)!.id).toBe('s2');
    // сервер уже знает другое значение, у нас pending=false -> сервер выигрывает
    const srv2 = session({}, [setRow('s1', 0, 40, { ok: false, done_kg: 40 }), setRow('s2', 1, 50), setRow('s3', 2, 60)]);
    l.sets.s1.pending = false;
    expect(overlayLocal(srv2, l).blocks[0].exercises[0].sets[0].ok).toBe(false);
  });
  it('pendingPuts: что дослать после перезагрузки', () => {
    const l = emptyLocal('sess1', 'a');
    l.sets.s1 = { done_kg: 40, ok: true, ts: 't1', pending: true };
    l.sets.s2 = { done_kg: 50, ok: true, ts: 't2', pending: false };
    const puts = pendingPuts(session(), l);
    expect(puts).toHaveLength(1);
    expect(puts[0]).toMatchObject({ setId: 's1', body: { done_kg: 40, ok: true, ts: 't1' } });
    // сервер уже принял — слать не надо
    const srv = session({}, [setRow('s1', 0, 40, { ok: true, done_kg: 40 }), setRow('s2', 1, 50), setRow('s3', 2, 60)]);
    expect(pendingPuts(srv, l)).toEqual([]);
  });
  it('pruneLocal удаляет старые сессии', () => {
    const l = emptyLocal('old', 'a');
    localStorage.setItem('fepra.bench.old', JSON.stringify({ ...l, updated: 1 }));
    saveLocal(emptyLocal('fresh', 'b'));
    pruneLocal();
    expect(loadLocal('old')).toBeNull();
    expect(loadLocal('fresh')).not.toBeNull();
  });
});

describe('VAPID и payload push', () => {
  it('base64url -> Uint8Array (без паддинга, с - и _)', () => {
    // 0xfb 0xff 0xfe -> base64 "+//+" -> base64url "-__-"
    expect([...urlBase64ToUint8Array('-__-')]).toEqual([0xfb, 0xff, 0xfe]);
    expect([...urlBase64ToUint8Array('AQID')]).toEqual([1, 2, 3]);
    expect([...urlBase64ToUint8Array('AQI')]).toEqual([1, 2]);
    expect([...urlBase64ToUint8Array('AQ')]).toEqual([1]);
  });
  it('публичный ключ VAPID: 65 байт, начинается с 0x04', () => {
    const bytes = new Uint8Array(65);
    bytes[0] = 4;
    for (let i = 1; i < 65; i++) bytes[i] = (i * 37) & 255;
    const b64url = btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const back = urlBase64ToUint8Array(b64url);
    expect(back.length).toBe(65);
    expect([...back]).toEqual([...bytes]);
  });
  it('payload: JSON и обычный текст', () => {
    const j = { json: () => ({ title: 'T', body: 'B', url: '/app/#/garmin', tag: 'x' }), text: () => '' };
    expect(parsePushPayload(j)).toEqual({ title: 'T', body: 'B', url: '/app/#/garmin', tag: 'x' });
    const txt = { json: () => { throw new Error('no'); }, text: () => 'привет' };
    expect(parsePushPayload(txt)).toEqual({ body: 'привет' });
    expect(parsePushPayload(null)).toEqual({});
  });
  it('url уведомления: только свой origin и /app/', () => {
    const o = 'https://fepra.example';
    expect(targetUrl('/app/#/garmin', o)).toBe('https://fepra.example/app/#/garmin');
    expect(targetUrl('https://evil.example/app/', o)).toBe('https://fepra.example/app/');
    expect(targetUrl('/api/secret', o)).toBe('https://fepra.example/app/');
    expect(targetUrl(undefined, o)).toBe('https://fepra.example/app/');
  });
});
