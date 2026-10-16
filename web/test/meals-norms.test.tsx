import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MealsScreen } from '../src/screens/meals/Meals';
import { buildParseRequest, buildSaveRequest, initialDraft } from '../src/screens/meals/draft';
import { MealAddScreen } from '../src/screens/meals/MealAdd';
import { ME, mockFetch, renderApp } from './helpers';

afterEach(() => vi.unstubAllGlobals());
const PRO = () => ({ json: { ...ME, roles: { ...ME.roles, pro: true } } });

const day = (extra: object = {}) => ({
  day: '2026-09-29', meals: [], water_l: 0.5, water_ml: 500,
  totals: { kcal: 951, protein_g: 59, fat_g: 41, carb_g: 87, fiber_g: 12, sodium_mg: 1800, iron_mg: 5, calcium_mg: 400, magnesium_mg: 120, potassium_mg: 1500, sugar_g: 20 },
  targets: { kcal: 2400, protein_g: 140, fat_g: 70, carb_g: 280 }, burned: 300, water_target_l: 2.7,
  micro_targets: { fiber_g: 30, sugar_g: 50, sodium_mg: 2300, iron_mg: 8, calcium_mg: 1000, magnesium_mg: 400, potassium_mg: 3500 },
  micro_limit: ['sugar_g', 'sodium_mg'], protein_per_kg: 0.75, ...extra,
});

describe('питание: нормы и микроэлементы на экране дня', () => {
  it('показывает норму ккал, БЖУ против нормы, микроэлементы и норму воды', async () => {
    mockFetch({ 'GET /api/me': PRO, 'GET /api/meals': () => ({ json: day() }) });
    renderApp(<MealsScreen />, '/meals');
    expect(await screen.findByText('/ 2700')).toBeInTheDocument();     // 2400 + 300 сожжено
    expect(screen.getByText('59/140 г')).toBeInTheDocument();
    expect(screen.getByText('12/30')).toBeInTheDocument();             // клетчатка
    expect(screen.getByText('≤1800/2300')).toBeInTheDocument();        // натрий — лимит
    expect(screen.getByTestId('water-ml')).toHaveTextContent('500 / 2700');
  });

  it('нет норм (профиль пуст): факт БЖУ и ссылка на профиль', async () => {
    mockFetch({ 'GET /api/me': PRO, 'GET /api/meals': () => ({ json: day({ targets: null }) }) });
    renderApp(<MealsScreen />, '/meals');
    expect(await screen.findByText(/Нормы КБЖУ не заданы/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Заполнить профиль' })).toHaveAttribute('href', '/profile');
  });
});

describe('питание: фото с текстовым описанием', () => {
  it('описание уходит вместе с фото при разборе и сохранении', () => {
    const s = { ...initialDraft(), source: { kind: 'photo' as const, upload_id: 'u1', text: 'борщ' } };
    expect(buildParseRequest(s)).toEqual({ upload_id: 'u1', text: 'борщ' });
    expect(buildSaveRequest({ ...s, draft: { foods: [] } })).toMatchObject({ upload_id: 'u1', text: 'борщ' });
  });

  it('есть отдельные кнопки «Снять» (камера) и «Из галереи»', async () => {
    mockFetch({ 'GET /api/me': PRO });
    renderApp(<MealAddScreen />, '/meals/new');
    expect(await screen.findByRole('button', { name: /Снять/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Из галереи/ })).toBeInTheDocument();
    expect(screen.getByTestId('photo-cam')).toHaveAttribute('capture', 'environment');
    expect(screen.getByTestId('photo-file')).not.toHaveAttribute('capture');
  });

  it('поле описания есть на вкладке «Фото»', async () => {
    mockFetch({ 'GET /api/me': PRO });
    renderApp(<MealAddScreen />, '/meals/new');
    const box = await screen.findByLabelText(/Описание к фото/);
    fireEvent.change(box, { target: { value: 'борщ' } });
    await waitFor(() => expect(box).toHaveValue('борщ'));
  });
});

describe('отчёт по дню: добавление приёма', () => {
  it('есть кнопка записать приём на этот день и правка приёма по клику', async () => {
    const { NutritionDayScreen } = await import('../src/screens/Nutrition');
    const { Route, Routes } = await import('react-router-dom');
    mockFetch({
      'GET /api/me': PRO,
      'GET /api/nutrition': () => ({ json: { day: '2026-09-27', meals: [{ id: 7, ts: '2026-09-27T13:00:00', kcal: 500, foods: [{ name: 'рис' }] }], totals: {}, pro: true } }),
    });
    renderApp(<Routes><Route path="/nutrition/:day" element={<NutritionDayScreen />} /></Routes>, '/nutrition/2026-09-27');
    expect(await screen.findByRole('link', { name: /Записать приём/ })).toHaveAttribute('href', '/meals/new?day=2026-09-27');
    expect(await screen.findByText(/рис/)).toBeInTheDocument();
    expect(document.querySelector('a[href="/meals/7?day=2026-09-27"]')).not.toBeNull();
  });
});

describe('питание: фото -> текст -> «Отправить»', () => {
  it('после съёмки разбор не стартует, пока не нажата «Отправить»; описание уходит вместе с фото', async () => {
    const draft = { foods: [{ name: 'борщ', grams: 300, kcal: 200, protein_g: 8, fat_g: 8, carb_g: 20 }], totals: { kcal: 200, protein_g: 8, fat_g: 8, carb_g: 20 } };
    const routes: Record<string, () => { status?: number; json: unknown }> = {
      'GET /api/me': () => PRO(),
      'POST /api/uploads': () => ({ status: 201, json: { id: 'u1', url: '/api/uploads/u1', kind: 'meal' } }),
      'POST /api/meals/parse': () => ({ json: { job_id: 'j1' } }),
      'GET /api/jobs/j1': () => ({ json: { status: 'done', result: { recognized: true, reason: null, draft, notes: [], source: { kind: 'photo', upload_id: 'u1', text: 'борщ' } } } }),
    };
    const m = { calls: [] as { key: string; body: any }[] };
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const key = `${(init?.method ?? 'GET').toUpperCase()} ${String(input).split('?')[0]}`;
      const raw = init?.body;
      m.calls.push({ key, body: raw instanceof FormData ? '[multipart]' : raw ? JSON.parse(String(raw)) : undefined });
      const h = routes[key];
      if (!h) return new Response('{}', { status: 404 });
      const r = h();
      return new Response(JSON.stringify(r.json), { status: r.status ?? 200, headers: { 'Content-Type': 'application/json' } });
    }));
    (URL as any).createObjectURL = () => 'blob:x';
    renderApp(<MealAddScreen />, '/meals/new');
    const cam = await screen.findByTestId('photo-cam');
    fireEvent.change(cam, { target: { files: [new File([new Uint8Array([1, 2, 3])], 'a.jpg', { type: 'image/jpeg' })] } });
    const btn = screen.getByRole('button', { name: 'Отправить' });
    await waitFor(() => expect(m.calls.some((c) => c.key === 'POST /api/uploads')).toBe(true));
    await waitFor(() => expect(btn).not.toBeDisabled());
    expect(m.calls.some((c) => c.key === 'POST /api/meals/parse')).toBe(false);
    fireEvent.change(screen.getByLabelText(/Описание к фото/), { target: { value: 'борщ' } });
    fireEvent.click(btn);
    expect(await screen.findByLabelText('Блюдо')).toHaveValue('борщ');
    expect(m.calls.find((c) => c.key === 'POST /api/meals/parse')!.body).toEqual({ upload_id: 'u1', text: 'борщ' });
  });
});
