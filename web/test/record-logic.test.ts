import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { beforeEach, describe, expect, it } from 'vitest';
import type { ParseResult, ResultForm } from '../src/api/record';
import { DICTS } from '../src/i18n';
import { DRAFT_KEY, clearDraft, draftHasContent, isoDay, loadDraft, newDraft, saveDraft, yesterdayIso } from '../src/screens/record/draft';
import {
  buildFieldValue, buildFormResult, buildPutBody, canonWeightReps, formatTime, joinPair, maskTime, normalizeTime, parseRoundsReps,
  parseWeightReps, splitPair, timeToSeconds, valueToString, valuesFromServer,
} from '../src/screens/record/logic';
import { buildPatch } from '../src/screens/record/WorkoutManage';
import { targetFor } from '../src/screens/record/GoalsManage';
import { shortScore } from '../src/screens/record/RecentWorkouts';

describe('маска времени', () => {
  it('цифры превращаются в мм:сс', () => {
    expect(maskTime('4')).toBe('4');
    expect(maskTime('41')).toBe('41');
    expect(maskTime('412')).toBe('4:12');
    expect(maskTime('1234')).toBe('12:34');
    expect(maskTime('12345')).toBe('123:45');
    expect(maskTime('123456')).toBe('123:45'); // лишнее отрезаем
  });
  it('ручное двоеточие сохраняется, мусор вычищается', () => {
    expect(maskTime('4:1')).toBe('4:1');
    expect(maskTime('4:123')).toBe('41:23'); // цифры дописывали к маске: пересчитываем
    expect(maskTime('ab4c:1x2')).toBe('4:12');
  });
  it('разбор в секунды и обратно', () => {
    expect(timeToSeconds('4:12')).toBe(252);
    expect(timeToSeconds('412')).toBe(252);
    expect(timeToSeconds('12:05')).toBe(725);
    expect(timeToSeconds('7')).toBe(420); // одна-две цифры = минуты
    expect(timeToSeconds('1:02:03')).toBe(3723);
    expect(timeToSeconds('4:75')).toBeNull();
    expect(timeToSeconds('')).toBeNull();
    expect(timeToSeconds('abc')).toBeNull();
    expect(formatTime(252)).toBe('4:12');
    expect(formatTime(60)).toBe('1:00');
    expect(normalizeTime('4:5')).toBe('4:05');
    expect(normalizeTime('9')).toBe('9:00');
    expect(normalizeTime('x')).toBe('');
  });
});

describe('вес × повторы', () => {
  it('разные записи разделителя', () => {
    expect(parseWeightReps('100x5')).toEqual({ weight: 100, reps: 5 });
    expect(parseWeightReps('100×5')).toEqual({ weight: 100, reps: 5 });
    expect(parseWeightReps('82,5 х 3')).toEqual({ weight: 82.5, reps: 3 }); // кириллическая х
    expect(parseWeightReps(' 60 * 10 ')).toEqual({ weight: 60, reps: 10 });
    expect(parseWeightReps('100')).toEqual({ weight: 100, reps: null });
  });
  it('мусор отвергается', () => {
    for (const bad of ['', 'abc', '100x', 'x5', '100x0', '5000x1', '100x5x3', '-5x3']) expect(parseWeightReps(bad)).toBeNull();
  });
  it('каноническая запись и деление поля на два инпута', () => {
    expect(canonWeightReps({ weight: 82.5, reps: 3 })).toBe('82.5x3');
    expect(canonWeightReps({ weight: 100, reps: null })).toBe('100');
    expect(splitPair('100x5', 'x')).toEqual(['100', '5']);
    expect(splitPair('100×5', 'x')).toEqual(['100', '5']);
    expect(splitPair('100', 'x')).toEqual(['100', '']);
    expect(splitPair('5+3', '+')).toEqual(['5', '3']);
    expect(joinPair('100', '5', 'x')).toBe('100x5');
    expect(joinPair('', '', 'x')).toBe('');
    expect(joinPair('', '3', '+')).toBe('0+3');
  });
  it('круги+повторы', () => {
    expect(parseRoundsReps('5+3')).toBe('5+3');
    expect(parseRoundsReps('5 + 03')).toBe('5+3');
    expect(parseRoundsReps('7')).toBe(7);
    expect(parseRoundsReps('5+')).toBeNull();
    expect(parseRoundsReps('a')).toBeNull();
  });
});

const FORM: ResultForm = {
  version: 1,
  blocks: [
    { index: 0, title: 'присед', format: 'emom_strength', kind: 'strength', fields: [
      { key: '0.0', label: 'раунд 1', type: 'weight_reps', unit: 'кг×повт', group: null, movement: 'присед' },
      { key: '0.1', label: 'раунд 2', type: 'weight_reps', group: null, movement: 'присед' },
    ] },
    { index: 1, title: 'WOD 1', format: 'for_time', kind: 'metcon', fields: [
      { key: '1.0', label: 'вес гантели', type: 'weight' },
      { key: '1.1', label: 'время', type: 'time' },
      { key: '1.2', label: 'ккал', type: 'int', group: 'ladder' },
      { key: '1.3', label: 'AMRAP', type: 'rounds_reps', group: 'ladder' },
      { key: '1.4', label: 'коммент', type: 'text' },
    ] },
  ],
};

describe('сборка form_result', () => {
  it('все типы полей; пустые не отправляются', () => {
    const r = buildFormResult(FORM, {
      '0.0': '100х5', '0.1': '', '1.0': '22,5', '1.1': '836', '1.2': '42', '1.3': '5+3', '1.4': ' ок ',
    });
    expect(r.errors).toEqual({});
    expect(r.result).toEqual({ '0.0': '100x5', '1.0': 22.5, '1.1': '8:36', '1.2': 42, '1.3': '5+3', '1.4': 'ок' });
    expect(r.filled).toBe(6);
  });
  it('weight принимает «16/24» как строку', () => {
    expect(buildFormResult(FORM, { '1.0': '16/24' }).result['1.0']).toBe('16/24');
  });
  it('ошибки по ключам, значение не попадает в тело', () => {
    const r = buildFormResult(FORM, { '0.0': 'abc', '1.0': 'много', '1.1': '4:99', '1.2': '4.5', '1.3': '5+' });
    expect(r.errors).toEqual({ '0.0': 'weight_reps', '1.0': 'weight', '1.1': 'time', '1.2': 'int', '1.3': 'rounds_reps' });
    expect(r.result).toEqual({});
  });
  it('пустая/отсутствующая форма', () => {
    expect(buildFormResult(null, {}).filled).toBe(0);
    expect(buildFormResult({ blocks: [] }, { x: '1' }).result).toEqual({});
  });
  it('значения сервера превращаются в строки инпутов', () => {
    expect(valueToString('weight_reps', [70, 3])).toBe('70x3');
    expect(valueToString('weight_reps', { weight: 70, reps: 3 })).toBe('70x3');
    expect(valueToString('weight_reps', '70x3')).toBe('70x3');
    expect(valueToString('time', 252)).toBe('4:12');
    expect(valueToString('rounds_reps', { rounds: 5, reps: 3 })).toBe('5+3');
    expect(valueToString('int', 42)).toBe('42');
    expect(valueToString('int', null)).toBe('');
    expect(valuesFromServer(FORM, { '0.0': '100x5', '1.1': 300, zzz: 1 })).toEqual({ '0.0': '100x5', '1.1': '5:00' });
  });
});

describe('тело PUT', () => {
  const parse: ParseResult = {
    recognized: true, reason: null, board_text: 'WOD', format: 'for_time', blocks: [{ header: 'WOD 1' }],
    blocks_verified: false, form: FORM,
  };
  const base = () => ({ ...newDraft(new Date(2026, 8, 1, 9, 5)), day: '2026-09-01', startTime: '09:05' });

  it('своя доска: board + form_result + rpe/scaling/вес тела', () => {
    const d = { ...base(), sport: 'weightlifting' as const, source: 'photo' as const, parse: { ...parse }, values: { '0.0': '70x3', '1.1': '6:00' }, rpe: 8, scaling: 'rx' as const, bodyweight: '80,5' };
    const { body, errors } = buildPutBody(d);
    expect(errors).toEqual({});
    expect(body).toEqual({
      day: '2026-09-01', sport: 'weightlifting', start_time: '09:05', rpe: 8, scaling: 'rx', bodyweight: 80.5,
      board: { text: 'WOD', source: 'own', format: 'for_time', blocks: [{ header: 'WOD 1' }], blocks_verified: false },
      form_result: { '0.0': '70x3', '1.1': '6:00' },
    });
  });
  it('зальная программа: без текста и блоков', () => {
    const { body } = buildPutBody({ ...base(), source: 'gym', parse: { ...parse }, values: { '1.1': '7:00' } });
    expect(body.board).toEqual({ source: 'gym' });
    expect(body.form_result).toEqual({ '1.1': '7:00' });
  });
  it('без доски: свободный текст', () => {
    const { body } = buildPutBody({ ...base(), source: 'free', freeText: ' Присед 100x3\nRPE 8 ' });
    expect(body.board).toBeUndefined();
    expect(body.form_result).toBe('Присед 100x3\nRPE 8');
  });
  it('бег: длительность, дистанция, заметка; доски нет', () => {
    const { body } = buildPutBody({ ...base(), sport: 'run', duration: '30', distance: '5,2', freeText: 'легко', rpe: 6 });
    expect(body).toMatchObject({ sport: 'run', duration_min: 30, distance_km: 5.2, form_result: 'легко', rpe: 6 });
    expect(body.board).toBeUndefined();
  });
  it('ошибки формы возвращаются, кривое время старта не отправляется', () => {
    const { body, errors } = buildPutBody({ ...base(), startTime: '25:99', source: 'photo', parse: { ...parse }, values: { '1.1': '4:99' } });
    expect(errors['1.1']).toBe('time');
    expect(body.start_time).toBeUndefined();
    expect(body.form_result).toBeUndefined();
  });
  it('даты: вчера и локальный день', () => {
    expect(isoDay(new Date(2026, 0, 5))).toBe('2026-01-05');
    expect(yesterdayIso(new Date(2026, 2, 1))).toBe('2026-02-28');
  });
});

describe('PATCH: только изменённое', () => {
  const w = {
    id: 'u1', day: '2026-09-01', sport: 'weightlifting', rpe: 7, scaling: 'rx', bodyweight: 80, board_text: 'WOD', board_editable: true,
    form: FORM, form_values: { '1.1': '6:00' }, editable: true,
  };
  const same = { values: { '1.1': '6:00' }, rpe: 7, scaling: 'rx' as const, bodyweight: '80', boardText: 'WOD', resultText: '' };
  it('без изменений — пусто', () => {
    expect(buildPatch(w, same).changes).toEqual({});
  });
  it('rpe, scaling, вес, счёт', () => {
    const r = buildPatch(w, { ...same, rpe: 9, scaling: 'scaled', bodyweight: '79,5', values: { '1.1': '5:30' } });
    expect(r.changes).toEqual({ rpe: 9, scaling: 'scaled', bodyweight: 79.5, form_result: { '1.1': '5:30' } });
  });
  it('доска уходит только когда правится и разрешена; тогда form_result не шлём', () => {
    expect(buildPatch(w, { ...same, boardText: 'WOD2', values: { '1.1': '1:00' } }).changes).toEqual({ board: { text: 'WOD2' } });
    expect(buildPatch({ ...w, board_editable: false }, { ...same, boardText: 'WOD2' }).changes).toEqual({});
  });
  it('rpe можно снять', () => {
    expect(buildPatch(w, { ...same, rpe: null }).changes).toEqual({ rpe: null });
  });
});

describe('цели и ПМ', () => {
  it('значение цели под единицы', () => {
    expect(targetFor('kg', '140')).toBe('140');
    expect(targetFor('kg', '82,5')).toBe('82.5');
    expect(targetFor('kg', '0')).toBeNull();
    expect(targetFor('time', '430')).toBe('4:30');
    expect(targetFor('time', 'abc')).toBeNull();
    expect(targetFor('rounds', '25')).toBe('25');
    expect(targetFor('rounds', '2.5')).toBeNull();
  });
});

describe('локальный черновик', () => {
  beforeEach(() => localStorage.clear());
  it('сохраняется и восстанавливается вместе с введённым', () => {
    const d = { ...newDraft(), step: 'result' as const, values: { '1.1': '8:36' }, rpe: 8, freeText: 'x' };
    saveDraft(d);
    const back = loadDraft();
    expect(back?.uuid).toBe(d.uuid);
    expect(back?.values).toEqual({ '1.1': '8:36' });
    expect(back?.rpe).toBe(8);
    expect(draftHasContent(back!)).toBe(true);
  });
  it('пустой черновик содержательным не считается', () => {
    expect(draftHasContent(newDraft())).toBe(false);
  });
  it('протухший, битый и очищенный не возвращаются', () => {
    saveDraft(newDraft(), Date.now() - 4 * 24 * 3600 * 1000);
    expect(loadDraft()).toBeNull();
    localStorage.setItem(DRAFT_KEY, '{oops');
    expect(loadDraft()).toBeNull();
    saveDraft(newDraft());
    clearDraft();
    expect(loadDraft()).toBeNull();
  });
  it('uuid у каждой новой тренировки свой и похож на UUID', () => {
    const a = newDraft().uuid, b = newDraft().uuid;
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  });
});

describe('i18n записи', () => {
  it('все ключи rec.* из кода есть в RU и EN', () => {
    const dir = join(__dirname, '../src/screens/record');
    const used = new Set<string>();
    for (const f of readdirSync(dir).filter((x) => /\.tsx?$/.test(x))) {
      const src = readFileSync(join(dir, f), 'utf8');
      for (const m of src.matchAll(/'((?:rec|err|common|workout)\.[a-z_0-9.]+)'/g)) used.add(m[1]);
    }
    for (const sport of ['crossfit', 'weightlifting', 'hyrox', 'run', 'bike']) used.add(`rec.sport.${sport}`);
    for (const k of ['weight_reps', 'weight', 'time', 'int', 'rounds_reps']) used.add(`rec.fmt.${k}`);
    for (const k of ['barbell', 'dumbbell', 'gym', 'cardio', 'time', 'amrap', 'scaling']) used.add(`rec.how.${k}`);
    for (const k of ['quota', 'no_vision', 'not_recognized', 'no_gym']) used.add(`rec.notice.${k}`);
    for (const k of ['fast', 'slow']) used.add(`rec.engine.${k}`);
    const missing = [...used].filter((k) => !(k in DICTS.ru) || !(k in DICTS.en));
    expect(missing).toEqual([]);
  });
});

describe('список записей', () => {
  it('многострочный счёт сокращается до первой строки', () => {
    expect(shortScore('AMRAP:\n  кругов: 5')).toBe('AMRAP:');
    expect(shortScore('x'.repeat(50))).toHaveLength(32);
    expect(shortScore(null)).toBeNull();
    expect(shortScore('  \n ')).toBeNull();
  });
});

describe('повторы по схеме (reps_default)', () => {
  it('только вес: повторы берутся по схеме', () => {
    expect(buildFieldValue('weight_reps', '22.5', 21)).toEqual({ value: '22.5x21' });
    expect(buildFieldValue('weight_reps', '80', 5)).toEqual({ value: '80x5' });
  });
  it('повторы изменены: уходит число атлета', () => {
    expect(buildFieldValue('weight_reps', '22.5x12', 21)).toEqual({ value: '22.5x12' });
  });
  it('без схемы поведение прежнее', () => {
    expect(buildFieldValue('weight_reps', '100')).toEqual({ value: '100' });
  });
  it('пусто остаётся пустым, даже если есть схема', () => {
    expect(buildFieldValue('weight_reps', '', 5)).toEqual({ value: null });
  });
  it('buildFormResult передаёт reps_default поля', () => {
    const form = { blocks: [{ index: 0, title: 'x', fields: [
      { key: '0.0', label: 'раунд 1', type: 'weight_reps' as const, reps_default: 5 },
    ] }] };
    expect(buildFormResult(form, { '0.0': '60' }).result['0.0']).toBe('60x5');
  });
});

describe('кардио, сани и повторы с весом', () => {
  it('кардио: ккал, метры, секунды или минуты — одно из четырёх', () => {
    expect(buildFieldValue('cardio', 'kcal:22')).toEqual({ value: { unit: 'kcal', value: 22 } });
    expect(buildFieldValue('cardio', 'm:250')).toEqual({ value: { unit: 'm', value: 250 } });
    expect(buildFieldValue('cardio', 'sec:40')).toEqual({ value: { unit: 'sec', value: 40 } });
    expect(buildFieldValue('cardio', 'min:1,5')).toEqual({ value: { unit: 'min', value: 1.5 } });
  });
  it('кардио: пусто и ошибки', () => {
    expect(buildFieldValue('cardio', 'm:')).toEqual({ value: null });
    expect(buildFieldValue('cardio', 'kcal:abc')).toEqual({ value: null, error: 'cardio' });
  });
  it('кардио без единицы берёт единицу по умолчанию', () => {
    expect(buildFieldValue('cardio', '20', null, 'm')).toEqual({ value: { unit: 'm', value: 20 } });
  });
  it('сани: вес, дистанция и время (сек/мин), хотя бы одно', () => {
    expect(buildFieldValue('weight_distance', '100|20||sec')).toEqual({ value: { weight: 100, meters: 20 } });
    expect(buildFieldValue('weight_distance', '100|20|45|sec')).toEqual({ value: { weight: 100, meters: 20, time: 45, time_unit: 'sec' } });
    expect(buildFieldValue('weight_distance', '||2|min')).toEqual({ value: { time: 2, time_unit: 'min' } });
    expect(buildFieldValue('weight_distance', '|30||sec')).toEqual({ value: { meters: 30 } });
    expect(buildFieldValue('weight_distance', '||')).toEqual({ value: null });
    expect(buildFieldValue('weight_distance', 'a|5||sec')).toEqual({ value: null, error: 'weight_distance' });
  });
  it('повторы с весом по желанию', () => {
    expect(buildFieldValue('reps_load', '|25')).toEqual({ value: { reps: 25 } });
    expect(buildFieldValue('reps_load', '10|18')).toEqual({ value: { reps: 18, weight: 10 } });
    expect(buildFieldValue('reps_load', '10|')).toEqual({ value: null, error: 'reps_load' });
    expect(buildFieldValue('reps_load', '')).toEqual({ value: null });
  });
  it('значения с сервера возвращаются в поля', () => {
    expect(valueToString('cardio', { unit: 'm', value: 250 })).toBe('m:250');
    expect(valueToString('cardio', { unit: 'min', value: 2 })).toBe('min:2');
    expect(valueToString('cardio', '22 ккал')).toBe('kcal:22');
    expect(valueToString('cardio', '40 сек')).toBe('sec:40');
    expect(valueToString('cardio', '2 мин')).toBe('min:2');
    // прежний формат «время мм:сс» превращается в секунды
    expect(valueToString('cardio', { unit: 'time', value: '0:40' })).toBe('sec:40');
    expect(valueToString('cardio', '1:35 время')).toBe('sec:95');
    expect(valueToString('weight_distance', { weight: 100, meters: 20, time: 45, time_unit: 'sec' })).toBe('100|20|45|sec');
    expect(valueToString('weight_distance', { time: 2, time_unit: 'min' })).toBe('||2|min');
    expect(valueToString('reps_load', { reps: 18, weight: 10 })).toBe('10|18');
    expect(valueToString('reps_load', '22.5x30')).toBe('22.5|30');
    expect(valueToString('reps_load', '25')).toBe('|25');
  });
});

describe('вес в for-time и AMRAP: повторы по желанию', () => {
  it('только вес и вес с повторами', () => {
    expect(buildFieldValue('weight_reps', '22.5')).toEqual({ value: '22.5' });
    expect(buildFieldValue('weight_reps', '22.5x12')).toEqual({ value: '22.5x12' });
  });
});

describe('предзаполненные повторы без веса', () => {
  it('повторы без веса — подход не выполнялся, не ошибка', () => {
    expect(buildFieldValue('weight_reps', 'x9', 9)).toEqual({ value: null });
    expect(buildFieldValue('weight_reps', 'x', 9)).toEqual({ value: null });
  });
  it('вес с изменёнными повторами уходит как ввёл атлет', () => {
    expect(buildFieldValue('weight_reps', '45x18', 21)).toEqual({ value: '45x18' });
  });
});

describe('маска времени: набор цифр подряд', () => {
  // регресс: с 1:50 нельзя было набрать 15:00 — четвёртая цифра пропадала
  const typeDigits = (digits: string) => {
    let v = '';
    for (const d of digits) v = maskTime(v + d);
    return v;
  };
  it('15:00 набирается цифрами 1-5-0-0', () => {
    expect(typeDigits('1500')).toBe('15:00');
  });
  it('разные времена цифрами подряд', () => {
    expect(typeDigits('150')).toBe('1:50');
    expect(typeDigits('1234')).toBe('12:34');
    expect(typeDigits('940')).toBe('9:40');
    expect(typeDigits('1055')).toBe('10:55');
    expect(typeDigits('2000')).toBe('20:00');
  });
  it('ручное двоеточие по-прежнему работает', () => {
    expect(typeDigits('15')).toBe('15');
    expect(maskTime('15:0')).toBe('15:0');
    expect(maskTime('15:00')).toBe('15:00');
    expect(maskTime('9:40')).toBe('9:40');
  });
  it('стирание с конца', () => {
    expect(maskTime('15:0')).toBe('15:0');
    expect(maskTime('15:')).toBe('15:');
    expect(maskTime('15')).toBe('15');
  });
  it('время из набранных цифр проходит проверку и уходит на сервер', () => {
    expect(normalizeTime(typeDigits('1500'))).toBe('15:00');
    expect(buildFieldValue('time', typeDigits('1500'))).toEqual({ value: '15:00' });
  });
});
