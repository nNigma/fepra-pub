import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { GymTodayCard, previewLines, shortDay } from '../src/screens/record/GymTodayCard';
import { RecordScreen } from '../src/screens/record/RecordScreen';
import { todayIso } from '../src/screens/record/draft';
import { ME, mockFetch, renderApp } from './helpers';

const FORM = {
  version: 1,
  blocks: [{ index: 0, title: 'Фронтальный присед', format: 'strength', kind: 'strength', fields: [
    { key: '0.0', label: 'раунд 1 (вес×повторы)', type: 'weight_reps', unit: 'кг×повт', section: 'Фронтальный присед', group: null, movement: 'Фронтальный присед', reps_default: 5 },
  ] }],
};
const PROGRAM = {
  found: true, day: todayIso(), gym: 'Universe', board_text: 'Фронтальный присед 5×5\nWod#1\n21-15-9',
  blocks: [{ header: 'Фронтальный присед' }], blocks_verified: true, form: FORM, template_text: '',
};
const meOk = () => ({ json: ME });

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe('хелперы программы зала', () => {
  it('превью: первые строки и многоточие', () => {
    expect(previewLines('a\n\n b \nc', 2)).toBe('a\nb\n…');
    expect(previewLines('a\nb', 5)).toBe('a\nb');
    expect(previewLines(undefined)).toBe('');
  });
  it('короткая дата', () => {
    expect(shortDay('2026-09-29')).toBe('29.09');
    expect(shortDay('мусор')).toBe('мусор');
  });
});

describe('карточка программы зала на сегодня', () => {
  it('есть программа: карточка со ссылкой в форму зала', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/gym-program': () => ({ json: PROGRAM }) });
    renderApp(<GymTodayCard />);
    const link = await screen.findByRole('link', { name: 'Записать по программе зала' });
    expect(link.getAttribute('href')).toBe(`/record?gym=Universe&day=${todayIso()}`);
    expect(screen.getByText(/Фронтальный присед 5×5/)).toBeTruthy();
  });
  it('нет программы: карточки нет', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/gym-program': () => ({ json: { found: false, day: todayIso() } }) });
    renderApp(<GymTodayCard />);
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Записать по программе зала' })).toBeNull());
  });
});

describe('мастер записи: программа зала', () => {
  const renderRecord = (path = '/record') =>
    renderApp(<Routes><Route path="/record" element={<RecordScreen />} /></Routes>, path);

  it('при выборе дня программа зала предлагается сразу', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/gym-program': () => ({ json: PROGRAM }) });
    renderRecord();
    expect(await screen.findByText(/Программа зала на/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Записать по программе зала' })).toBeTruthy();
  });

  it('кнопка открывает форму по программе зала без загрузки своей доски', async () => {
    const { calls } = mockFetch({ 'GET /api/me': meOk, 'GET /api/gym-program': () => ({ json: PROGRAM }) });
    renderRecord();
    fireEvent.click(await screen.findByRole('button', { name: 'Записать по программе зала' }));
    // на шаге проверки показана доска зала только для чтения и есть кнопка «Принять»
    await screen.findByText(/Программа зала/);
    expect(calls.some((c) => c.key === 'POST /api/board/parse')).toBe(false);
    expect(calls.some((c) => c.key === 'POST /api/uploads')).toBe(false);
  });

  it('ссылка ?gym=1 сразу открывает форму по программе зала', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/gym-program': () => ({ json: PROGRAM }) });
    renderRecord(`/record?gym=1&day=${todayIso()}`);
    expect(await screen.findByText(/раунд 1 \(вес×повторы\)/)).toBeTruthy();       // сразу форма результата
    expect(document.querySelector('.gym-prog')?.textContent).toContain('Фронтальный присед 5×5');   // программа под рукой
  });

  it('нет программы на день: карточки нет, мастер работает как обычно', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/gym-program': () => ({ json: { found: false, day: todayIso() } }) });
    renderRecord();
    await screen.findByRole('button', { name: 'ТА' });
    expect(screen.queryByText(/Программа зала на/)).toBeNull();
  });
});

describe('админ и тренер управляют программой зала прямо из тренировок', () => {
  const ADMIN = { ...ME, roles: { admin: true, pro: true, coach: false } };
  const COACH = { ...ME, roles: { admin: false, pro: false, coach: true } };

  it('админ: программы нет — карточка с кнопкой загрузки доски', async () => {
    mockFetch({ 'GET /api/me': () => ({ json: ADMIN }), 'GET /api/gym-program': () => ({ json: { found: false, day: todayIso() } }) });
    renderApp(<GymTodayCard />);
    const add = await screen.findByRole('link', { name: /Загрузить программу зала/ });
    expect(add.getAttribute('href')).toBe(`/club/edit?day=${todayIso()}`);
    expect(screen.queryByRole('link', { name: 'Записать по программе зала' })).toBeNull();
  });

  it('тренер: программа есть — записать и изменить', async () => {
    mockFetch({ 'GET /api/me': () => ({ json: COACH }), 'GET /api/gym-program': () => ({ json: PROGRAM }) });
    renderApp(<GymTodayCard />);
    expect(await screen.findByRole('link', { name: 'Записать по программе зала' })).toBeTruthy();
    expect((await screen.findByRole('link', { name: /Изменить программу зала/ })).getAttribute('href')).toBe(`/club/edit?day=${todayIso()}`);
  });

  it('обычному атлету без программы карточки нет', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/gym-program': () => ({ json: { found: false, day: todayIso() } }) });
    renderApp(<GymTodayCard />);
    await waitFor(() => expect(screen.queryByText(/Программа зала на сегодня/)).toBeNull());
  });

  it('в мастере записи админ видит ссылку на добавление программы на выбранный день', async () => {
    mockFetch({ 'GET /api/me': () => ({ json: ADMIN }), 'GET /api/gym-program': () => ({ json: { found: false, day: todayIso() } }) });
    renderApp(<Routes><Route path="/record" element={<RecordScreen />} /></Routes>, '/record');
    const l = await screen.findByRole('link', { name: /Добавить программу зала на/ });
    expect(l.getAttribute('href')).toBe(`/club/edit?day=${todayIso()}`);
  });

  it('в мастере записи обычный атлет такой ссылки не видит', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/gym-program': () => ({ json: { found: false, day: todayIso() } }) });
    renderApp(<Routes><Route path="/record" element={<RecordScreen />} /></Routes>, '/record');
    await screen.findByRole('button', { name: 'ТА' });
    expect(screen.queryByRole('link', { name: /программу зала на/ })).toBeNull();
  });
});

describe('мастер записи: «Дальше» при готовой программе зала', () => {
  it('сразу открывает форму результата по программе зала, доску не просит', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/gym-program': () => ({ json: PROGRAM }) });
    renderApp(<Routes><Route path="/record" element={<RecordScreen />} /></Routes>, '/record');
    fireEvent.click(await screen.findByRole('button', { name: 'Дальше: по программе зала' }));
    expect(await screen.findByText(/раунд 1 \(вес×повторы\)/)).toBeTruthy();      // сразу форма результата
    expect(screen.queryByRole('button', { name: 'Принять' })).toBeNull();
  });
});

describe('мастер записи: выбор зала (несколько залов)', () => {
  it('админ выбирает зал, и программа запрашивается именно для него', async () => {
    const urls: string[] = [];
    mockFetch({
      'GET /api/me': meOk,
      'GET /api/club/gyms': () => ({ json: { current: 'Universe', can_add: true, gyms: [
        { name: 'Universe', is_default: true, is_mine: true, can_manage: true },
        { name: 'INVICTUS GO OXY', is_default: false, is_mine: false, can_manage: true }] } }),
      'GET /api/gym-program': (_b: any, url: string) => {
        urls.push(url);
        return { json: url.includes('INVICTUS') || url.includes('%D') ? { ...PROGRAM, gym: 'INVICTUS GO OXY' } : { found: false, day: todayIso() } };
      },
    });
    renderApp(<Routes><Route path="/record" element={<RecordScreen />} /></Routes>, '/record');
    fireEvent.click(await screen.findByRole('button', { name: 'INVICTUS GO OXY' }));
    expect(await screen.findByRole('button', { name: 'Записать по программе зала' })).toBeTruthy();
    expect(urls.some((u) => u.includes('gym=INVICTUS'))).toBe(true);
  });
});


describe('программа зала: переход к записи', () => {
  it('на просмотре программы есть кнопка «Записать тренировку по этой программе» с названием зала', async () => {
    const { ClubScreen } = await import('../src/screens/club/Club');
    mockFetch({
      'GET /api/me': meOk,
      'GET /api/club/gyms': () => ({ json: { current: 'INVICTUS GO OXY', gyms: [{ name: 'INVICTUS GO OXY', is_default: false, is_mine: true, can_manage: false }] } }),
      'GET /api/club/program': () => ({ json: { gym: 'INVICTUS GO OXY', day: '2026-10-03', program: { raw_text: 'Wod ×2', format: 'x', movements: [] }, last_day: null, can_manage: false } }),
    });
    renderApp(<ClubScreen />, '/club');
    const link = await screen.findByRole('link', { name: /Записать тренировку по этой программе/ });
    expect(link.getAttribute('href')).toBe('/record?gym=INVICTUS%20GO%20OXY&day=2026-10-03');
  });

  it('ссылка с названием зала открывает форму результата именно этого зала', async () => {
    const urls: string[] = [];
    mockFetch({
      'GET /api/me': meOk,
      'GET /api/club/gyms': () => ({ json: { current: 'Universe', gyms: [
        { name: 'Universe', is_default: true, is_mine: true, can_manage: true }, { name: 'INVICTUS GO OXY', is_default: false, is_mine: false, can_manage: true }] } }),
      'GET /api/gym-program': (_b: any, url: string) => { urls.push(url); return { json: { ...PROGRAM, gym: 'INVICTUS GO OXY' } }; },
    });
    renderApp(<Routes><Route path="/record" element={<RecordScreen />} /></Routes>, `/record?gym=${encodeURIComponent('INVICTUS GO OXY')}&day=${todayIso()}`);
    expect(await screen.findByText(/раунд 1 \(вес×повторы\)/)).toBeTruthy();
    expect(urls.some((u) => u.includes('gym=INVICTUS%20GO%20OXY'))).toBe(true);
  });
});

describe('запись по программе другого зала', () => {
  it('в PUT уходит название выбранного зала (иначе сервер искал бы программу только в зале из профиля)', async () => {
    const { buildPutBody } = await import('../src/screens/record/logic');
    const { newDraft } = await import('../src/screens/record/draft');
    const d = { ...newDraft(), source: 'gym' as const, gymName: 'INVICTUS GO OXY', parse: { recognized: true, reason: null, board_text: 'x', blocks: [], form: FORM } as never };
    expect(buildPutBody(d).body.board).toEqual({ source: 'gym', gym: 'INVICTUS GO OXY' });
    expect(buildPutBody({ ...d, gymName: null }).body.board).toEqual({ source: 'gym' });
  });
});
