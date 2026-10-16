import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, request } from '../src/api/client';
import { DICTS } from '../src/i18n';
import { canManageClub, isAdmin, isPro } from '../src/lib/roles';
import { COACH_DAILY_LIMIT, coachRemaining } from '../src/screens/coach/Coach';
import { visibleTiles } from '../src/screens/more/tiles';
import {
  LIMITS, parseFieldErrors, stepsFor, toPatch, validateField, validateFields, type FormValues,
} from '../src/screens/onboarding/validate';
import { addNote, buildParseRequest, buildSaveRequest, canSave, draftReducer, initialDraft, totalsOf } from '../src/screens/meals/draft';
import {
  joinDivisionChoice, parseCreateResponse, parseResultInput, serializeConfirmResults, serializeConfirmStages,
  serializeCreateEvent, serializeResultText, validDateInput,
} from '../src/screens/comps/serialize';
import { applyRoles, isBlocking, removeWarning, roleWarning } from '../src/screens/admin/logic';
import { statsChartConfig } from '../src/screens/admin/AdminStats';
import type { Me } from '../src/api/types';
import type { AdminUser } from '../src/api/admin';
import type { MealParseResult } from '../src/api/meals';
import { uploadFile } from '../src/api/rest';
import { mockFetch } from './helpers';

afterEach(() => vi.unstubAllGlobals());

const form = (o: Partial<FormValues> = {}): FormValues => ({
  nick: 'Аня', height_cm: '170', weight_kg: '60,5', sex: 'f', age: '30', gym: 'Universe', goal: 'maintain', city: 'Москва', lang: 'ru', ...o,
});

describe('валидаторы онбординга', () => {
  it('пределы совпадают с сервером', () => {
    expect(LIMITS.height).toEqual([100, 250]);
    expect(validateField('height_cm', '99')).not.toBeNull();
    expect(validateField('height_cm', '100')).toBeNull();
    expect(validateField('height_cm', '250')).toBeNull();
    expect(validateField('height_cm', '251')).not.toBeNull();
    expect(validateField('height_cm', '170.5')).not.toBeNull();
    expect(validateField('age', '9')).not.toBeNull();
    expect(validateField('age', '100')).toBeNull();
    expect(validateField('weight_kg', '19.9')).not.toBeNull();
    expect(validateField('weight_kg', '400')).toBeNull();
    expect(validateField('weight_kg', '400,1')).not.toBeNull();
    expect(validateField('weight_kg', '60,5')).toBeNull();
    expect(validateField('weight_kg', 'abc')).not.toBeNull();
  });
  it('ник, город, пол, зал', () => {
    expect(validateField('nick', '   ')).not.toBeNull();
    expect(validateField('nick', 'x'.repeat(41))).not.toBeNull();
    expect(validateField('nick', 'x'.repeat(40))).toBeNull();
    expect(validateField('city', 'y'.repeat(61))).not.toBeNull();
    expect(validateField('sex', 'z')).not.toBeNull();
    expect(validateField('sex', 'm')).toBeNull();
    expect(validateField('gym', 'Нет такого', { gyms: ['Universe', 'solo'] })).not.toBeNull();
    expect(validateField('gym', 'solo', { gyms: ['Universe', 'solo'] })).toBeNull();
    expect(validateField('goal', 'bulk')).toBeNull();
    expect(validateField('goal', 'x')).not.toBeNull();
  });
  it('ошибки несут ключ i18n и параметры диапазона', () => {
    const e = validateField('height_cm', '5', { ranges: { height: [100, 250], age: [10, 100], weight: [20, 400] } });
    expect(e).toEqual({ key: 'ob.err.height', params: { min: 100, max: 250 } });
    const all = validateFields(['height_cm', 'age', 'sex'], form({ height_cm: '', age: '5', sex: '' }));
    expect(Object.keys(all).sort()).toEqual(['age', 'height_cm', 'sex']);
  });
  it('toPatch приводит числа и запятую', () => {
    expect(toPatch(['height_cm', 'weight_kg', 'sex', 'nick'], form({ nick: ' Аня ' }))).toEqual({ height_cm: 170, weight_kg: 60.5, sex: 'f', nick: 'Аня' });
  });
  it('шаги мастера: только где чего-то не хватает + необязательный последним', () => {
    expect(stepsFor(['height_cm', 'age']).map((s) => s.id)).toEqual(['body', 'extra']);
    expect(stepsFor(['nick', 'gym']).map((s) => s.id)).toEqual(['nick', 'gym', 'extra']);
    expect(stepsFor([]).map((s) => s.id)).toEqual(['extra']);
  });
});

describe('разбор 422 {detail, fields}', () => {
  it('fields доходят до ApiError через клиент', async () => {
    mockFetch({
      'PATCH /api/profile': () => ({ status: 422, json: { detail: 'height_cm: ...; sex: ...', fields: { height_cm: 'рост: 100–250', sex: 'пол: m или f' } } }),
    });
    const err = (await request('/api/profile', { method: 'PATCH', body: { height_cm: 5 } }).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    const p = parseFieldErrors(err);
    expect(p.fields).toEqual({ height_cm: 'рост: 100–250', sex: 'пол: m или f' });
    expect(p.general).toBeNull();
  });
  it('без fields — общая строка; строковый detail не ломается', async () => {
    mockFetch({ 'PATCH /api/profile': () => ({ status: 422, json: { detail: 'что-то не так' } }) });
    const err = await request('/api/profile', { method: 'PATCH', body: {} }).catch((e) => e);
    expect(parseFieldErrors(err)).toEqual({ fields: {}, general: 'что-то не так' });
    expect(parseFieldErrors(new Error('boom')).general).toBe('boom');
  });
});

const parsed = (over: Partial<MealParseResult> = {}): MealParseResult => ({
  recognized: true, reason: null, notes: [],
  draft: { foods: [{ name: 'суп', grams: 300, kcal: 150, protein_g: 5, fat_g: 5, carb_g: 20 }], totals: { kcal: 150, protein_g: 5, fat_g: 5, carb_g: 20 }, question: null, quality: 2 },
  source: { kind: 'photo', upload_id: 'up1', url: '/api/uploads/up1', text: null },
  ...over,
});

describe('черновик приёма пищи', () => {
  it('фото: запрос без уточнений, потом накопление notes', () => {
    let s = draftReducer(initialDraft('u-1'), { type: 'start', source: { kind: 'photo', upload_id: 'up1' } });
    expect(s.status).toBe('parsing');
    expect(buildParseRequest(s)).toEqual({ upload_id: 'up1' });
    s = draftReducer(s, { type: 'parsed', result: parsed() });
    expect(s.status).toBe('ready');
    // первое уточнение: в запросе прошлые notes (пусто) + correction
    expect(buildParseRequest(s, ' без сливок ')).toEqual({ upload_id: 'up1', correction: 'без сливок', notes: [] });
    s = draftReducer(s, { type: 'parsed', result: parsed({ notes: ['без сливок'] }), correction: 'без сливок' });
    expect(s.notes).toEqual(['без сливок']);
    // второе: notes копятся и уходят вместе с новым correction
    expect(buildParseRequest(s, 'порция 400 г')).toEqual({ upload_id: 'up1', correction: 'порция 400 г', notes: ['без сливок'] });
    s = draftReducer(s, { type: 'parsed', result: parsed({ notes: ['без сливок', 'порция 400 г'] }), correction: 'порция 400 г' });
    expect(s.notes).toEqual(['без сливок', 'порция 400 г']);
  });
  it('если сервер не вернул notes — добавляем уточнение сами, без дублей', () => {
    let s = draftReducer(initialDraft(), { type: 'parsed', result: parsed() });
    s = draftReducer(s, { type: 'parsed', result: parsed(), correction: 'острое' });
    expect(s.notes).toEqual(['острое']);
    expect(addNote(s.notes, 'острое')).toBe(s.notes);
    expect(addNote(s.notes, '  ')).toBe(s.notes);
  });
  it('текстовый источник; провал уточнения не теряет черновик', () => {
    let s = draftReducer(initialDraft(), { type: 'start', source: { kind: 'text', text: 'овсянка' } });
    expect(buildParseRequest(s)).toEqual({ text: 'овсянка' });
    s = draftReducer(s, { type: 'parsed', result: parsed({ source: { kind: 'text', text: 'овсянка' } }) });
    s = draftReducer(s, { type: 'parsed', result: { recognized: false, reason: 'quota', draft: null, notes: [], source: { kind: 'text' } }, correction: 'x' });
    expect(s.status).toBe('ready');
    expect(s.reason).toBe('quota');
    expect(s.draft?.foods).toHaveLength(1);
    // первый разбор не удался — черновика нет
    const f = draftReducer(initialDraft(), { type: 'parsed', result: { recognized: false, reason: 'not_recognized', draft: null, notes: [], source: { kind: 'photo' } } });
    expect(f.status).toBe('failed');
    expect(f.draft).toBeNull();
  });
  it('правка блюд пересчитывает тоталы; сохранение с клиентским uuid', () => {
    let s = draftReducer(initialDraft('uuid-fixed'), { type: 'start', source: { kind: 'photo', upload_id: 'up1' } });
    s = draftReducer(s, { type: 'parsed', result: parsed() });
    s = draftReducer(s, { type: 'food', index: 0, patch: { kcal: 200, protein_g: 10 } });
    expect(s.draft?.totals).toEqual({ kcal: 200, protein_g: 10, fat_g: 5, carb_g: 20 });
    s = draftReducer(s, { type: 'addFood' });
    expect(canSave(s)).toBe(false); // у нового блюда нет имени
    s = draftReducer(s, { type: 'food', index: 1, patch: { name: 'хлеб', kcal: 80 } });
    expect(canSave(s)).toBe(true);
    expect(totalsOf(s.draft!.foods).kcal).toBe(280);
    const body = buildSaveRequest(s, '2026-09-29');
    expect(body).toMatchObject({ uuid: 'uuid-fixed', day: '2026-09-29', upload_id: 'up1' });
    expect(body.draft.foods).toHaveLength(2);
    s = draftReducer(s, { type: 'removeFood', index: 0 });
    expect(s.draft?.foods.map((f) => f.name)).toEqual(['хлеб']);
    // текстовый приём кладёт text (по нему работает перепарс)
    const t = draftReducer(initialDraft('u2'), { type: 'start', source: { kind: 'text', text: 'каша' } });
    expect(buildSaveRequest({ ...t, draft: parsed().draft }).text).toBe('каша');
  });
});

describe('соревнования: сериализация', () => {
  it('формат текстового результата', () => {
    expect(parseResultInput('5:30, 12, 40')).toEqual({ value: '5:30', place: 12, field_size: 40 });
    expect(parseResultInput('5:30,12')).toEqual({ value: '5:30', place: 12, field_size: null });
    expect(parseResultInput('5:30')).toBeNull();
    expect(parseResultInput('5:30, x')).toBeNull();
    expect(parseResultInput('5:30, 12, 10')).toBeNull(); // место больше поля
    expect(parseResultInput('1, 2, 3, 4')).toBeNull();
  });
  it('тело результата текстом: пустое не шлём, «Я» — по умолчанию', () => {
    expect(serializeResultText({ text: ' 5:30, 12 ' })).toEqual({ text: '5:30, 12' });
    expect(serializeResultText({ text: '5:30, 12', athlete: 'Я', stageIdx: 2, divisionId: 12 })).toEqual({ text: '5:30, 12', stage_idx: 2, division_id: 12 });
    expect(serializeResultText({ text: '5:30, 12', athlete: 'Иван' })).toEqual({ text: '5:30, 12', athlete: 'Иван' });
  });
  it('confirm результатов: строки без этапа отбрасываются, типы приведены', () => {
    const body = serializeConfirmResults(7, [
      { stage: 1, value: ' 4:10 ', place: '5' as unknown as number, stage_id: '89' as unknown as number, stage_idx: 2, stage_name: 'Grace' },
      { stage: 2, value: '9:00', place: null, stage_id: null },
      { stage: 3, value: '', place: 3, stage_id: 90 },
    ], { athlete: 'Я', divisionId: null });
    expect(body).toEqual({ event_id: 7, rows: [{ stage: 1, value: '4:10', place: 5, stage_id: 89, stage_idx: 2, stage_name: 'Grace' }] });
    expect(serializeConfirmResults(7, [], { athlete: 'Иван', divisionId: 12 })).toEqual({ event_id: 7, rows: [], athlete: 'Иван', division_id: 12 });
  });
  it('confirm этапов и создание старта', () => {
    const b = serializeConfirmStages(7, [{ idx: 1, name: ' Fran ', prescription: '21-15-9 ', source_ref: 'upload:x#1' }, { idx: 2, name: ' ', prescription: '' }], 12);
    expect(b).toEqual({ event_id: 7, division_id: 12, stages: [{ idx: 1, name: 'Fran', prescription: '21-15-9', source_ref: 'upload:x#1' }] });
    expect(serializeCreateEvent({ name: ' Кубок ', date: '12.04.2026', city: ' Тула ', category: 'rx', division: '' })).toEqual({ name: 'Кубок', date: '12.04.2026', city: 'Тула', category: 'rx' });
    expect(serializeCreateEvent({ name: 'К', date: '12.04', city: 'Т', category: 'custom', division: ' Мастера 40+ ' }, true)).toEqual({ name: 'К', date: '12.04', city: 'Т', division: 'Мастера 40+', force_new: true });
    expect(validDateInput('12.04.2026') && validDateInput('12.04') && validDateInput('2026-04-12')).toBe(true);
    expect(validDateInput('апрель')).toBe(false);
  });
  it('ответ дедупа старта', () => {
    const dup = parseCreateResponse({
      created: false, duplicate: true,
      candidates: [{ id: 7, name: 'Кубок Тулы', city: 'Тула', date_start: '2026-04-12', date_end: '2026-04-12', divisions: [{ id: 12, name: 'RX', field_size: 40, participant_id: null }] }],
    });
    expect(dup.kind).toBe('duplicate');
    if (dup.kind === 'duplicate') {
      expect(dup.candidates[0].id).toBe(7);
      expect(joinDivisionChoice(dup.candidates[0])).toBe(12);
      expect(joinDivisionChoice({ ...dup.candidates[0], divisions: [] })).toBeNull();
      expect(joinDivisionChoice({ ...dup.candidates[0], divisions: [...dup.candidates[0].divisions, { id: 13, name: 'PRO', field_size: null, participant_id: null }] })).toBe('choose');
    }
    expect(parseCreateResponse({ created: true, duplicate: false, event_id: 7, division_id: 12, participant_id: 31 })).toEqual({ kind: 'created', eventId: 7, divisionId: 12 });
    // кандидаты без divisions не ломают разбор
    expect(parseCreateResponse({ duplicate: true, candidates: [{ id: 1, name: 'a' }] } as never)).toMatchObject({ kind: 'duplicate', candidates: [{ id: 1, divisions: [] }] });
    expect(parseCreateResponse({ duplicate: true })).toEqual({ kind: 'duplicate', candidates: [] });
  });
});

const ME = (roles: Partial<Me['roles']>): Me => ({
  id: 1, nick: 'x', lang: 'ru', roles: { admin: false, pro: false, coach: false, ...roles }, gym: null, has_passkey: false, garmin: null, public_url: null,
});

describe('показ управления по ролям', () => {
  it('предикаты', () => {
    expect([isAdmin(ME({})), isPro(ME({})), canManageClub(ME({}))]).toEqual([false, false, false]);
    expect([isAdmin(ME({ pro: true })), isPro(ME({ pro: true })), canManageClub(ME({ pro: true }))]).toEqual([false, true, false]);
    expect(canManageClub(ME({ coach: true }))).toBe(true);
    expect(canManageClub(ME({ admin: true }))).toBe(true);
    expect(isPro(ME({ admin: true }))).toBe(true);
    expect(canManageClub(null)).toBe(false);
  });
  it('плитки «Ещё» по ролям', () => {
    const keys = (me: Me | null) => visibleTiles(me).map((t) => t.to);
    const athlete = keys(ME({}));
    expect(athlete).toContain('/comps');
    expect(athlete).toContain('/club');
    for (const hidden of ['/meals', '/coach', '/admin', '/club/pending']) expect(athlete).not.toContain(hidden);
    const pro = keys(ME({ pro: true }));
    expect(pro).toEqual(expect.arrayContaining(['/meals', '/coach']));
    expect(pro).not.toContain('/admin');
    const coach = keys(ME({ coach: true }));
    expect(coach).toContain('/club/pending');
    expect(coach).not.toContain('/admin');
    const admin = keys(ME({ admin: true }));
    expect(admin).toEqual(expect.arrayContaining(['/admin', '/club/pending', '/meals', '/coach']));
  });
});

const U = (id: number, roles: Partial<AdminUser['roles']> = {}): AdminUser => ({
  id, nick: `u${id}`, gym: null, created_at: null,
  roles: { allowlist: true, pro: false, admin: false, coach: false, coach_gym: null, coach_gyms: [], ...roles },
});

describe('админка: правила ролей', () => {
  it('последний админ', () => {
    const users = [U(1, { admin: true }), U(2)];
    expect(roleWarning(users, users[0], { admin: false })).toBe('last_admin');
    expect(isBlocking(roleWarning(users, users[0], { admin: false }))).toBe(true);
    expect(roleWarning(users, users[1], { pro: true })).toBeNull();
    expect(removeWarning(users, users[0])).toBe('last_admin');
    const two = [U(1, { admin: true }), U(2, { admin: true })];
    expect(roleWarning(two, two[0], { admin: false }, 2)).toBeNull();
    expect(roleWarning(two, two[0], { admin: false }, 1)).toBe('self_admin');
    expect(isBlocking('self_admin')).toBe(false);
    expect(roleWarning(two, two[0], { allowlist: false })).toBe('drop_allowlist_admin');
    expect(removeWarning(two, two[0])).toBe('remove_admin');
    expect(removeWarning(two, U(3))).toBeNull();
  });
  it('applyRoles и график статистики', () => {
    const users = [U(1), U(2)];
    const next = applyRoles(users, 2, { ...users[1].roles, pro: true });
    expect(next[1].roles.pro).toBe(true);
    expect(next[0]).toBe(users[0]);
    const cfg = statsChartConfig({ days: 7, since: null, total: 9, users: [{ id: 1, nick: 'a', total: 2, actions: [] }, { id: 2, nick: null, total: 7, actions: [] }] });
    expect((cfg.data as { labels: string[] }).labels).toEqual(['#2', 'a']);
  });
});

describe('тренер: лимит', () => {
  it('осталось вопросов', () => {
    const rec = [{ ts: '2026-09-29T10:00:00' }, { ts: '2026-09-29T11:00:00' }, { ts: '2026-09-28T09:00:00' }];
    expect(coachRemaining(rec, false, '2026-09-29')).toEqual({ used: 2, left: COACH_DAILY_LIMIT - 2 });
    expect(coachRemaining([...rec, { ts: '2026-09-29T12:00:00' }], false, '2026-09-29').left).toBe(0);
    expect(coachRemaining(rec, true, '2026-09-29').left).toBeNull();
  });
});

describe('i18n фазы 5', () => {
  const DYNAMIC = [
    'ob.gym.solo', 'ob.gym.other', 'ob.sex.m', 'ob.sex.f', 'goal.cut', 'goal.maintain', 'goal.bulk', 'goal.recomp',
    'ob.step.nick', 'ob.step.body', 'ob.step.gym', 'ob.step.extra',
    'meal.mode.photo', 'meal.mode.text', 'meal.reason.quota', 'meal.reason.no_vision', 'meal.reason.not_recognized',
    'comp5.cat.newbie', 'comp5.cat.pro', 'comp5.cat.int', 'comp5.cat.rx', 'comp5.tab.stage', 'comp5.tab.result', 'comp5.tab.total',
    'set.watch.garmin', 'set.watch.samsung', 'set.watch.whoop', 'set.watch.apple',
    'adm.warn.last_admin', 'adm.warn.self_admin', 'adm.warn.drop_allowlist_admin', 'adm.warn.remove_admin',
    'adm.role.allowlist', 'adm.role.pro', 'adm.role.admin', 'q.meal.1', 'q.meal.2', 'q.meal.3', 'q.meal.4', 'lang.ru', 'lang.en',
  ];
  function walk(dir: string, out: string[] = []): string[] {
    for (const n of readdirSync(dir)) {
      const p = join(dir, n);
      if (statSync(p).isDirectory()) walk(p, out);
      else if (/\.tsx?$/.test(n)) out.push(p);
    }
    return out;
  }
  it('все литеральные ключи t(...) экранов фазы 5 есть в RU и EN', () => {
    const root = join(__dirname, '..', 'src', 'screens');
    const files = ['onboarding', 'settings', 'meals', 'comps', 'coach', 'club', 'admin', 'more'].flatMap((d) => walk(join(root, d))).concat(join(root, 'ui5.tsx'));
    const used = new Set<string>(DYNAMIC);
    for (const f of files) {
      for (const m of readFileSync(f, 'utf8').matchAll(/\bt\(\s*'([\w.]+)'/g)) used.add(m[1]);
      for (const m of readFileSync(f, 'utf8').matchAll(/key: '([\w.]+)'/g)) used.add(m[1]); // ошибки валидаторов и плитки
    }
    const missing = [...used].filter((k) => !(k in DICTS.ru) || !(k in DICTS.en));
    expect(missing).toEqual([]);
  });
});

describe('загрузка файла', () => {
  it('multipart без ручного Content-Type, поля file и kind', async () => {
    const fn = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const fd = init!.body as FormData;
      expect(fd).toBeInstanceOf(FormData);
      expect(fd.get('kind')).toBe('meal');
      expect((fd.get('file') as File).name).toBe('x.jpg');
      expect((init!.headers as Record<string, string>)['Content-Type']).toBeUndefined();
      return new Response(JSON.stringify({ id: 'u1', url: '/api/uploads/u1', mime: 'image/jpeg', size: 3, kind: 'meal' }), { status: 200 });
    });
    vi.stubGlobal('fetch', fn);
    const r = await uploadFile(new Blob(['abc'], { type: 'image/jpeg' }), 'meal', 'x.jpg');
    expect(r.id).toBe('u1');
    expect(fn).toHaveBeenCalledOnce();
  });
});
