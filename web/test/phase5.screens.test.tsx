import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminScreen } from '../src/screens/admin/Admin';
import { ClubScreen } from '../src/screens/club/Club';
import { CompCreateScreen } from '../src/screens/comps/CompCreate';
import { MealAddScreen } from '../src/screens/meals/MealAdd';
import { OnboardingGate } from '../src/screens/onboarding/Onboarding';
import { MoreScreen } from '../src/screens/Profile';
import { Route, Routes } from 'react-router-dom';
import { ME, mockFetch, renderApp } from './helpers';

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

const meWith = (roles: Partial<typeof ME.roles>) => () => ({ json: { ...ME, roles: { ...ME.roles, ...roles } } });

describe('онбординг: мастер', () => {
  const base = {
    'GET /api/me': () => ({ json: ME }),
    'GET /api/onboarding': () => ({ json: { complete: false, missing: ['height_cm', 'weight_kg', 'sex', 'age'], optional_missing: [], ranges: { height_cm: [100, 250], age: [10, 100], weight_kg: [20, 400] } } }),
    'GET /api/profile': () => ({ json: { id: 1, nick: 'Тест', height_cm: null, weight_kg: null, sex: null, age: null, gym: 'Universe', lang: 'ru', goal: 'maintain', city: 'Москва', astro: false, watch: {}, available_watch_actions: [] } }),
    'GET /api/gyms': () => ({ json: { gyms: [{ name: 'Universe', is_default: true, members: 3 }], special: ['solo', 'other'] } }),
  };

  it('клиентская ошибка -> 422 с fields -> успех -> необязательный шаг -> приложение', async () => {
    let patches = 0;
    const m = mockFetch({
      ...base,
      'PATCH /api/profile': (body) => {
        patches++;
        if (patches === 1) return { status: 422, json: { detail: 'age: ...', fields: { age: 'возраст: сервер не принял' } } };
        return { json: { ...body } };
      },
    });
    renderApp(<OnboardingGate><div>ПРИЛОЖЕНИЕ</div></OnboardingGate>);
    await screen.findByText(/Параметры тела/);
    fireEvent.click(screen.getByRole('button', { name: 'Дальше' }));
    expect(await screen.findByText(/Рост: целое число 100–250 см/)).toBeInTheDocument();
    expect(m.calls.some((c) => c.key === 'PATCH /api/profile')).toBe(false); // на сервер невалидное не ушло

    fireEvent.change(screen.getByLabelText(/Рост, см/), { target: { value: '180' } });
    fireEvent.change(screen.getByLabelText(/Вес, кг/), { target: { value: '80,5' } });
    fireEvent.change(screen.getByLabelText(/Пол/), { target: { value: 'm' } });
    fireEvent.change(screen.getByLabelText(/Возраст/), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Дальше' }));
    expect(await screen.findByText('возраст: сервер не принял')).toBeInTheDocument();
    expect(m.calls.find((c) => c.key === 'PATCH /api/profile')!.body).toEqual({ height_cm: 180, weight_kg: 80.5, sex: 'm', age: 30 });

    fireEvent.click(screen.getByRole('button', { name: 'Дальше' }));
    await screen.findByText(/Питание, город, язык/);
    fireEvent.click(screen.getByRole('button', { name: 'Готово' }));
    expect(await screen.findByText('ПРИЛОЖЕНИЕ')).toBeInTheDocument();
  });

  it('профиль полный — сразу приложение; ошибка проверки не блокирует', async () => {
    mockFetch({ 'GET /api/me': () => ({ json: ME }), 'GET /api/onboarding': () => ({ json: { complete: true, missing: [], optional_missing: [], ranges: {} } }) });
    renderApp(<OnboardingGate><div>ПРИЛОЖЕНИЕ</div></OnboardingGate>);
    expect(await screen.findByText('ПРИЛОЖЕНИЕ')).toBeInTheDocument();
    vi.unstubAllGlobals();
    mockFetch({ 'GET /api/me': () => ({ json: ME }), 'GET /api/onboarding': () => ({ status: 500, json: { detail: 'boom' } }) });
    renderApp(<OnboardingGate><div>ПРИЛОЖЕНИЕ-2</div></OnboardingGate>);
    expect(await screen.findByText('ПРИЛОЖЕНИЕ-2')).toBeInTheDocument();
  });
});

describe('питание: запись по тексту с уточнениями', () => {
  it('разбор -> уточнение копит notes -> сохранение с одним uuid', async () => {
    let n = 0;
    const draft = { foods: [{ name: 'суп', grams: 300, kcal: 150, protein_g: 5, fat_g: 5, carb_g: 20 }], totals: { kcal: 150, protein_g: 5, fat_g: 5, carb_g: 20 }, question: 'на бульоне или со сливками?', quality: 2, quality_note: 'лёгкий' };
    const m = mockFetch({
      'GET /api/me': meWith({ pro: true }),
      'POST /api/meals/parse': () => { n++; return { json: { job_id: `j${n}` } }; },
      'GET /api/jobs/j1': () => ({ json: { status: 'done', result: { recognized: true, reason: null, draft, notes: [], source: { kind: 'text', text: 'суп' } } } }),
      'GET /api/jobs/j2': () => ({ json: { status: 'done', result: { recognized: true, reason: null, draft, notes: ['без сливок'], source: { kind: 'text', text: 'суп' } } } }),
      'POST /api/meals': () => ({ json: { created: true, meal: { id: 1 } } }),
    });
    renderApp(<Routes><Route path="/meals/new" element={<MealAddScreen />} /><Route path="/meals" element={<div>СПИСОК</div>} /></Routes>, '/meals/new?day=2026-01-15');
    fireEvent.click(await screen.findByRole('button', { name: 'Текст' }));
    fireEvent.change(screen.getByLabelText('Что ты съел'), { target: { value: 'суп' } });
    fireEvent.click(screen.getByRole('button', { name: 'Разобрать' }));
    expect(await screen.findByLabelText('Блюдо')).toHaveValue('суп');
    expect(screen.getByText(/на бульоне или со сливками/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Поправить'), { target: { value: 'без сливок' } });
    fireEvent.click(screen.getByRole('button', { name: /Уточнить у ИИ/ }));
    await waitFor(() => expect(screen.getByTestId('notes')).toHaveTextContent('без сливок'));
    const parses = m.calls.filter((c) => c.key === 'POST /api/meals/parse');
    expect(parses[0].body).toEqual({ text: 'суп' });
    expect(parses[1].body).toEqual({ text: 'суп', correction: 'без сливок', notes: [] });

    fireEvent.click(screen.getByRole('button', { name: 'Сохранить приём' }));
    await screen.findByText('СПИСОК');
    const save = m.calls.find((c) => c.key === 'POST /api/meals')!;
    expect(save.body.uuid).toMatch(/[0-9a-f-]{20,}/);
    expect(save.body).toMatchObject({ day: '2026-01-15', text: 'суп' });
  });

  it('не Pro: объяснение и «попроси админа», запросов нет', async () => {
    const m = mockFetch({ 'GET /api/me': meWith({ pro: false }) });
    renderApp(<MealAddScreen />, '/meals/new');
    expect(await screen.findByText(/попроси админа/)).toBeInTheDocument();
    expect(m.calls.some((c) => c.key.includes('/api/meals'))).toBe(false);
  });
});

describe('старт: дедуп', () => {
  it('duplicate -> кандидаты -> «создать новый» шлёт force_new', async () => {
    const m = mockFetch({
      'GET /api/me': () => ({ json: ME }),
      'POST /api/comp/events': (b) => b.force_new
        ? { json: { created: true, duplicate: false, event_id: 9, division_id: 3, participant_id: 4 } }
        : { json: { created: false, duplicate: true, candidates: [{ id: 7, name: 'Кубок Тулы', city: 'Тула', date_start: '2026-04-12', divisions: [{ id: 12, name: 'RX', field_size: 40, participant_id: null }] }] } },
      'POST /api/comp/events/7/join': () => ({ json: { event_id: 7, division_id: 12, participant_id: 32, created: true } }),
    });
    renderApp(<Routes><Route path="/comps/new" element={<CompCreateScreen />} /><Route path="/comps/:id" element={<div>СТАРТ</div>} /></Routes>, '/comps/new');
    fireEvent.change(await screen.findByLabelText('Название'), { target: { value: 'Кубок Тулы' } });
    fireEvent.change(screen.getByLabelText(/Дата/), { target: { value: '12.04.2026' } });
    fireEvent.change(screen.getByLabelText('Город'), { target: { value: 'тула' } });
    fireEvent.click(screen.getByRole('button', { name: 'Создать' }));
    expect(await screen.findByText('Такой старт уже есть')).toBeInTheDocument();
    expect(screen.getByText(/Кубок Тулы/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Создать новый всё равно' }));
    await screen.findByText('СТАРТ');
    expect(m.calls.filter((c) => c.key === 'POST /api/comp/events').map((c) => !!c.body.force_new)).toEqual([false, true]);
    expect(m.calls.some((c) => c.key.endsWith('/join'))).toBe(false);
  });
});

describe('роли на экранах', () => {
  const day = { gym: 'Universe', day: '2026-09-29', program: { id: 1, uuid: 'u', day: '2026-09-29', gym: 'Universe', raw_text: 'WOD: Fran', format: 'for_time', movements: ['thruster'], blocks: null, blocks_verified: false, source: 'manual', confirmed: true, updated_at: null, created_by: 1 }, last_day: null, can_manage: true };

  it('зал: обычный атлет не видит управления', async () => {
    mockFetch({ 'GET /api/me': meWith({}), 'GET /api/club/program': () => ({ json: { ...day, can_manage: false } }) });
    renderApp(<ClubScreen />);
    expect(await screen.findByText(/WOD: Fran/)).toBeInTheDocument();
    expect(screen.queryByText(/Ожидающие/)).toBeNull();
    expect(screen.queryByText(/Редактировать программу/)).toBeNull();
  });
  it('зал: тренер видит очередь, статистику и редактор', async () => {
    mockFetch({ 'GET /api/me': meWith({ coach: true }), 'GET /api/club/program': () => ({ json: day }) });
    renderApp(<ClubScreen />);
    expect(await screen.findByText(/Редактировать программу/)).toBeInTheDocument();
    expect(screen.getByText(/Ожидающие/)).toBeInTheDocument();
    expect(screen.getByText(/Статистика и атлеты/)).toBeInTheDocument();
  });
  it('админка закрыта не-админу, «Ещё» показывает плитки по ролям', async () => {
    mockFetch({ 'GET /api/me': meWith({ pro: true }) });
    const { unmount } = renderApp(<AdminScreen />);
    expect(await screen.findByText('Нет доступа к этому разделу.')).toBeInTheDocument();
    unmount();
    vi.unstubAllGlobals();
    mockFetch({ 'GET /api/me': meWith({ pro: true }) });
    renderApp(<MoreScreen />);
    expect(await screen.findByText('ИИ-тренер')).toBeInTheDocument();
    expect(screen.queryByText('Админка')).toBeNull();
    vi.unstubAllGlobals();
    mockFetch({ 'GET /api/me': meWith({ admin: true }) });
    renderApp(<MoreScreen />);
    expect(await screen.findByText('Админка')).toBeInTheDocument();
  });
});
