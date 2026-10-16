import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { ClubEditScreen } from '../src/screens/club/ClubEdit';
import { ClubScreen } from '../src/screens/club/Club';
import { AdminGymsScreen } from '../src/screens/admin/AdminGyms';
import { AdminUsersScreen } from '../src/screens/admin/AdminUsers';
import { pickGym } from '../src/screens/club/clubGym';
import { ME, renderApp } from './helpers';

const ADMIN = { ...ME, roles: { admin: true, pro: true, coach: false } };
const COACH = { ...ME, roles: { admin: false, pro: false, coach: true } };
const gymsOf = (names: string[], cur: string, manage = true) => ({
  current: cur, gyms: names.map((n) => ({ name: n, is_default: n === 'Universe', is_mine: n === cur, can_manage: manage })),
});

type H = (body: any, url: string) => { status?: number; json?: unknown };
function mockFetch(rs: Record<string, H>) {
  const calls: { key: string; body: any; url: string }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const key = `${(init?.method ?? 'GET').toUpperCase()} ${url.split('?')[0]}`;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ key, body, url });
    const h = rs[key];
    if (!h) return new Response(JSON.stringify({ detail: 'no route ' + key }), { status: 404 });
    const r = h(body, url);
    return new Response(JSON.stringify(r.json ?? {}), { status: r.status ?? 200, headers: { 'Content-Type': 'application/json' } });
  }));
  return { calls };
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe('выбор зала: чистая логика', () => {
  const gyms = gymsOf(['Universe', 'Атлант', 'Сигма'], 'Universe').gyms;
  it('приоритет: адрес, потом запомненный, потом зал по умолчанию', () => {
    expect(pickGym(gyms, 'Атлант', 'Сигма', 'Universe')).toBe('Атлант');
    expect(pickGym(gyms, null, 'Сигма', 'Universe')).toBe('Сигма');
    expect(pickGym(gyms, null, null, 'Universe')).toBe('Universe');
  });
  it('чужой или устаревший зал не выбирается', () => {
    expect(pickGym(gyms, 'Чужой', 'Тоже чужой', 'Universe')).toBe('Universe');
    expect(pickGym(gyms, null, null, undefined)).toBe('Universe');
    expect(pickGym([], null, null, 'Universe')).toBeUndefined();
  });
});

describe('редактор программы: выбор зала', () => {
  const renderEdit = (path = '/club/edit?day=2026-09-29') =>
    renderApp(<Routes><Route path="/club/edit" element={<ClubEditScreen />} /></Routes>, path);
  const routes = (me: object, gyms: object) => ({
    'GET /api/me': () => ({ json: me }),
    'GET /api/club/gyms': () => ({ json: gyms }),
    'GET /api/club/program': (_b: any, url: string) => {
      const g = new URL(url, 'http://x').searchParams.get('gym') ?? 'Universe';
      return { json: { gym: g, day: '2026-09-29', program: g === 'Атлант' ? { raw_text: 'доска Атланта' } : null, last_day: null, can_manage: true } };
    },
    'GET /api/club/dictionary': () => ({ json: [] }),
    'PUT /api/club/program': () => ({ json: { program: { id: 1 }, unknown: [], job_id: null } }),
    'POST /api/club/program/preview': () => ({ json: { raw_text: 'x', format: 'other', canon: [], unknown: [], annotated: 'x' } }),
  });

  it('админ видит все залы и выбирает, куда писать', async () => {
    const { calls } = mockFetch(routes(ADMIN, gymsOf(['Universe', 'Атлант', 'Сигма'], 'Universe')));
    renderEdit();
    for (const g of ['Universe', 'Атлант', 'Сигма']) expect(await screen.findByRole('button', { name: g })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Сигма' }));
    await waitFor(() => expect(calls.some((c) => c.key === 'GET /api/club/program' && c.url.includes('gym=%D0%A1%D0%B8%D0%B3%D0%BC%D0%B0'))).toBe(true));
    fireEvent.change(await screen.findByRole('textbox', { name: /Текст программы/ }), { target: { value: 'Фронтальный присед 5×5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() => expect(calls.find((c) => c.key === 'PUT /api/club/program')?.body).toEqual({ day: '2026-09-29', raw_text: 'Фронтальный присед 5×5', gym: 'Сигма' }));
  });

  it('админ с одним залом видит переключатель и создаёт новый зал', async () => {
    const one = { ...gymsOf(['Universe'], 'Universe'), can_add: true };
    const two = { ...gymsOf(['Universe', 'Атлант'], 'Universe'), can_add: true };
    let made = false;
    const { calls } = mockFetch({
      ...routes(ADMIN, one),
      'GET /api/club/gyms': () => ({ json: made ? two : one }),
      'POST /api/admin/gyms': () => { made = true; return { status: 201, json: { name: 'Атлант', is_default: false, members: 0, coaches: [] } }; },
    });
    vi.stubGlobal('prompt', vi.fn(() => 'Атлант'));
    window.prompt = vi.fn(() => 'Атлант');
    renderEdit();
    fireEvent.click(await screen.findByRole('button', { name: '+ Зал' }));
    await waitFor(() => expect(calls.find((c) => c.key === 'POST /api/admin/gyms')?.body).toEqual({ name: 'Атлант' }));
    expect(await screen.findByRole('button', { name: 'Атлант' })).toBeTruthy();
  });

  it('при смене зала подгружается программа именно этого зала', async () => {
    mockFetch(routes(ADMIN, gymsOf(['Universe', 'Атлант'], 'Universe')));
    renderEdit();
    fireEvent.click(await screen.findByRole('button', { name: 'Атлант' }));
    await waitFor(() => expect((document.querySelector('textarea') as HTMLTextAreaElement).value).toBe('доска Атланта'));
  });

  it('тренер одного зала переключателя не видит', async () => {
    mockFetch(routes(COACH, gymsOf(['Universe'], 'Universe')));
    renderEdit();
    await screen.findByText(/Программа по фото доски/);
    expect(screen.queryByRole('group', { name: 'Зал' })).toBeNull();
  });

  it('тренер нескольких залов выбирает из своих', async () => {
    mockFetch(routes(COACH, gymsOf(['Universe', 'Атлант'], 'Universe')));
    renderEdit();
    expect(await screen.findByRole('button', { name: 'Атлант' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Сигма' })).toBeNull();
  });

  it('залы без права управления в редакторе не предлагаются', async () => {
    mockFetch(routes(COACH, { current: 'Universe', gyms: [
      { name: 'Universe', is_default: true, is_mine: true, can_manage: true },
      { name: 'Чужой', is_default: false, is_mine: false, can_manage: false }] }));
    renderEdit();
    await screen.findByText(/Программа по фото доски/);
    expect(screen.queryByRole('button', { name: 'Чужой' })).toBeNull();
  });

  it('нет залов для управления: понятное сообщение', async () => {
    mockFetch(routes(COACH, gymsOf(['Universe'], 'Universe', false)));
    renderEdit();
    expect(await screen.findByText(/нет залов, где можно менять программу/)).toBeTruthy();
  });

  it('список залов не загрузился: редактор всё равно работает (зал подставит сервер)', async () => {
    const r = routes(ADMIN, gymsOf(['Universe'], 'Universe'));
    delete (r as any)['GET /api/club/gyms'];
    mockFetch(r);
    renderEdit();
    expect(await screen.findByText(/Программа по фото доски/)).toBeTruthy();
  });
});

describe('экран зала: выбор зала', () => {
  it('переключение зала перезапрашивает программу этого зала', async () => {
    const { calls } = mockFetch({
      'GET /api/me': () => ({ json: ADMIN }),
      'GET /api/club/gyms': () => ({ json: gymsOf(['Universe', 'Атлант'], 'Universe') }),
      'GET /api/club/program': (_b: any, url: string) => {
        const g = new URL(url, 'http://x').searchParams.get('gym') ?? 'Universe';
        return { json: { gym: g, day: '2026-09-29', program: { id: 1, raw_text: `доска ${g}`, format: 'other', movements: [] }, last_day: null, can_manage: true } };
      },
    });
    renderApp(<Routes><Route path="/club" element={<ClubScreen />} /></Routes>, '/club');
    expect(await screen.findByText('доска Universe')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Атлант' }));
    expect(await screen.findByText('доска Атлант')).toBeTruthy();
    expect(calls.filter((c) => c.key === 'GET /api/club/program').length).toBeGreaterThanOrEqual(2);
  });
});

describe('админка: несколько залов у тренера', () => {
  it('тренер с двумя залами: каждый зал снимается отдельно', async () => {
    const { calls } = mockFetch({
      'GET /api/me': () => ({ json: ADMIN }),
      'GET /api/admin/gyms': () => ({ json: [
        { name: 'Universe', is_default: true, members: 3, coaches: [{ id: 7, nick: 'Иван' }] },
        { name: 'Атлант', is_default: false, members: 1, coaches: [{ id: 7, nick: 'Иван' }] }] }),
      'GET /api/admin/coaches': () => ({ json: [{ id: 7, nick: 'Иван', gym: 'Universe', gyms: ['Universe', 'Атлант'] }] }),
      'DELETE /api/admin/coaches/7': () => ({ json: { ok: true } }),
    });
    vi.stubGlobal('confirm', () => true);
    renderApp(<AdminGymsScreen />);
    fireEvent.click(await screen.findByRole('button', { name: /Снять: Атлант/ }));
    await waitFor(() => expect(calls.some((c) => c.key === 'DELETE /api/admin/coaches/7' && c.url.includes('gym='))).toBe(true));
    expect(screen.getByRole('button', { name: /Снять из всех залов/ })).toBeTruthy();
  });
});

describe('админка: назначение тренеру залов', () => {
  const user = (coach_gyms: string[]) => ({
    id: 7, nick: 'Иван', gym: 'Universe', created_at: null,
    roles: { allowlist: true, pro: false, admin: false, coach: coach_gyms.length > 0, coach_gym: coach_gyms[0] ?? null, coach_gyms },
  });
  const setup = (cg: string[]) => mockFetch({
    'GET /api/me': () => ({ json: ADMIN }),
    'GET /api/admin/users': () => ({ json: [user(cg)] }),
    'GET /api/admin/gyms': () => ({ json: [
      { name: 'Universe', is_default: true, members: 3, coaches: [] }, { name: 'Атлант', is_default: false, members: 1, coaches: [] },
      { name: 'Сигма', is_default: false, members: 0, coaches: [] }] }),
    'PUT /api/admin/users/7/roles': (b) => ({ json: { id: 7, roles: { ...user(Array.isArray(b.coach) ? b.coach : []).roles } } }),
  });

  it('отметка второго зала отправляет полный набор залов', async () => {
    const { calls } = setup(['Universe']);
    renderApp(<AdminUsersScreen />);
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Тренер зала: Атлант' }));
    await waitFor(() => expect(calls.find((c) => c.key === 'PUT /api/admin/users/7/roles')?.body).toEqual({ coach: ['Universe', 'Атлант'] }));
  });

  it('«Ссылка для входа» создаёт приглашение на существующий аккаунт и показывает ссылку', async () => {
    const m = mockFetch({
      'GET /api/me': () => ({ json: ADMIN }),
      'GET /api/admin/users': () => ({ json: [user([])] }),
      'GET /api/admin/gyms': () => ({ json: [] }),
      'POST /api/admin/invites': () => ({ json: { token: 'abc', url: 'https://x.test/app/#/invite/abc' } }),
    });
    renderApp(<AdminUsersScreen />);
    fireEvent.click(await screen.findByRole('button', { name: /Ссылка для входа в приложение/ }));
    expect(await screen.findByTestId('login-link')).toHaveTextContent('https://x.test/app/#/invite/abc');
    expect(m.calls.find((c) => c.key === 'POST /api/admin/invites')?.body).toMatchObject({ existing_user_id: 7, role: 'athlete' });
  });

  it('снятие последнего зала снимает тренера (coach: null)', async () => {
    const { calls } = setup(['Universe']);
    renderApp(<AdminUsersScreen />);
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Тренер зала: Universe' }));
    await waitFor(() => expect(calls.find((c) => c.key === 'PUT /api/admin/users/7/roles')?.body).toEqual({ coach: null }));
  });

  it('текущие залы тренера отмечены', async () => {
    setup(['Universe', 'Сигма']);
    renderApp(<AdminUsersScreen />);
    expect(((await screen.findByRole('checkbox', { name: 'Тренер зала: Сигма' })) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole('checkbox', { name: 'Тренер зала: Атлант' }) as HTMLInputElement).checked).toBe(false);
  });
});

describe('профиль: дополнительные залы', () => {
  it('можно добавить себя ещё в один зал, основной зал в списке не показывается', async () => {
    const { ProfileSettingsScreen } = await import('../src/screens/settings/ProfileSettings');
    const profile = { id: 1, nick: 'Я', height_cm: 180, weight_kg: 80, sex: 'm', age: 30, gym: 'Universe', extra_gyms: [], lang: 'ru', goal: 'maintain', city: 'Москва', astro: false, watch: {}, available_watch_actions: [] };
    const { calls } = mockFetch({
      'GET /api/me': () => ({ json: ME }),
      'GET /api/profile': () => ({ json: profile }),
      'GET /api/gyms': () => ({ json: { gyms: [{ name: 'Universe', is_default: true, members: 3 }, { name: 'Атлант', is_default: false, members: 1 }], special: ['solo', 'other'] } }),
      'PATCH /api/profile': () => ({ json: { ...profile, extra_gyms: ['Атлант'] } }),
    });
    renderApp(<Routes><Route path="/s" element={<ProfileSettingsScreen />} /></Routes>, '/s');
    const chip = await screen.findByRole('button', { name: /Атлант/ });
    expect(screen.queryByRole('button', { name: /Universe/ })).toBeNull();
    fireEvent.click(chip);
    await waitFor(() => expect(calls.find((c) => c.key === 'PATCH /api/profile')?.body).toEqual({ extra_gyms: ['Атлант'] }));
  });
});
