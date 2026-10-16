import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LlmBlock } from '../src/components/LlmBlock';
import { A2hsBanner, Offline, isIosSafariBrowser } from '../src/components/Shell';
import { GarminScreen } from '../src/screens/Garmin';
import { InviteScreen, LoginScreen } from '../src/screens/Auth';
import { InvitesScreen } from '../src/screens/Invites';
import { Route, Routes } from 'react-router-dom';
import { ME, mockFetch, renderApp } from './helpers';

const meOk = () => ({ json: ME });

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe('LlmBlock', () => {
  it('запуск -> pending -> поллинг -> готовый текст', async () => {
    let polls = 0;
    const m = mockFetch({
      'GET /api/me': meOk,
      'GET /api/llm/workout/2026-09-01': () => {
        polls++;
        // 1-й GET — статус при загрузке (нет кэша); дальше — поллинг, кэш появляется на 3-м
        return { json: polls >= 3 ? { available: true, cached: { text: '## Итог\nХорошая работа', engine: 'claude' } } : { available: true, cached: null } };
      },
      'POST /api/llm/workout/2026-09-01': () => ({ json: { pending: true } }),
    });
    renderApp(<LlmBlock kind="workout" refKey="2026-09-01" pro pollMs={5} />);
    fireEvent.click(await screen.findByRole('button', { name: /Разобрать ИИ/ }));
    expect(await screen.findByText(/Хорошая работа/)).toBeInTheDocument();
    expect(screen.getByText('Итог')).toBeInTheDocument();
    expect(m.calls.filter((c) => c.key.startsWith('POST')).length).toBe(1);
    expect(screen.getByText(/Месье Клод/)).toBeInTheDocument();
  });

  it('429 показывает лимит, 403 — нужен Pro', async () => {
    mockFetch({
      'GET /api/me': meOk,
      'GET /api/llm/summary/30d': () => ({ json: { available: true, cached: null } }),
      'POST /api/llm/summary/30d': () => ({ status: 429, json: { detail: 'Лимит ИИ на сегодня исчерпан (7/день)' } }),
    });
    renderApp(<LlmBlock kind="summary" refKey="30d" pro />);
    fireEvent.click(await screen.findByRole('button', { name: /Разобрать ИИ/ }));
    expect(await screen.findByText(/Лимит ИИ на сегодня исчерпан \(7/)).toBeInTheDocument();
  });

  it('не Pro: только подсказка, запросов нет', async () => {
    const m = mockFetch({ 'GET /api/me': meOk });
    renderApp(<LlmBlock kind="summary" refKey="30d" pro={false} />);
    expect(await screen.findByText(/в Pro/)).toBeInTheDocument();
    expect(m.calls.some((c) => c.key.includes('/api/llm'))).toBe(false);
  });
});

describe('Garmin', () => {
  const base = {
    'GET /api/me': meOk,
    'GET /api/garmin/status': () => ({ json: { connected: false, status: 'disconnected' } }),
  };

  it('текст про пароль и токены на экране, поле пароля без автозаполнения', async () => {
    mockFetch(base);
    renderApp(<GarminScreen />);
    expect(await screen.findByText(/Пароль не сохраняется/)).toBeInTheDocument();
    const pw = document.querySelector('input[type=password]') as HTMLInputElement;
    expect(pw.autocomplete).toBe('off');
  });

  it('логин: пароль очищается из поля сразу после отправки; need_mfa -> код -> ok', async () => {
    let connected = false;
    const m = mockFetch({
      ...base,
      'GET /api/garmin/status': () => ({ json: connected ? { connected: true, status: 'ok', email: 'a@b.c', last_sync: null } : { connected: false, status: 'disconnected' } }),
      'POST /api/garmin/login': () => ({ json: { status: 'need_mfa' } }),
      'POST /api/garmin/mfa': () => { connected = true; return { json: { status: 'ok' } }; },
    });
    renderApp(<GarminScreen />);
    await screen.findByText(/Пароль не сохраняется/);
    fireEvent.change(document.querySelector('input[type=email]')!, { target: { value: 'a@b.c' } });
    const pw = document.querySelector('input[type=password]') as HTMLInputElement;
    fireEvent.change(pw, { target: { value: 's3cret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Подключить' }));
    await screen.findByText('Код подтверждения');
    // пароль ушёл в запрос и нигде в DOM не остался
    expect(m.calls.find((c) => c.key === 'POST /api/garmin/login')!.body).toEqual({ email: 'a@b.c', password: 's3cret' });
    expect(document.body.innerHTML).not.toContain('s3cret');
    fireEvent.change(document.querySelector('input[autocomplete=one-time-code]')!, { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить код' }));
    expect(await screen.findByText(/Garmin подключён/)).toBeInTheDocument();
    expect(m.calls.find((c) => c.key === 'POST /api/garmin/mfa')!.body).toEqual({ code: '123456' });
  });

  it('ошибка логина показывает сообщение и возвращает форму с пустым паролем', async () => {
    mockFetch({ ...base, 'POST /api/garmin/login': () => ({ json: { status: 'error', message: 'неверный пароль' } }) });
    renderApp(<GarminScreen />);
    await screen.findByText(/Пароль не сохраняется/);
    fireEvent.change(document.querySelector('input[type=email]')!, { target: { value: 'a@b.c' } });
    fireEvent.change(document.querySelector('input[type=password]')!, { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Подключить' }));
    expect(await screen.findByText(/неверный пароль/)).toBeInTheDocument();
    expect((document.querySelector('input[type=password]') as HTMLInputElement).value).toBe('');
  });

  it('синк: POST -> job -> поллинг -> «Готово»', async () => {
    let n = 0;
    mockFetch({
      'GET /api/me': meOk,
      'GET /api/garmin/status': () => ({ json: { connected: true, status: 'ok', email: 'a@b.c', last_sync: '2026-09-28T10:00:00Z' } }),
      'POST /api/garmin/sync': () => ({ json: { job_id: 'j1' } }),
      'GET /api/jobs/j1': () => ({ json: ++n < 2 ? { status: 'running' } : { status: 'done', result: {} } }),
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderApp(<GarminScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Синхронизировать сейчас' }));
    await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
    expect(await screen.findByText('Готово.')).toBeInTheDocument();
    vi.useRealTimers();
  });
});

describe('вход и оболочка', () => {
  it('LoginScreen: кнопка Face ID и подсказка про админа', async () => {
    vi.stubGlobal('PublicKeyCredential', class {});
    Object.defineProperty(navigator, 'credentials', { value: {}, configurable: true });
    mockFetch({ 'GET /api/me': () => ({ status: 401, json: { detail: 'x' } }) });
    renderApp(<LoginScreen />);
    expect(await screen.findByRole('button', { name: /Face ID/ })).toBeInTheDocument();
    expect(screen.getByText(/Попроси у админа новую ссылку/)).toBeInTheDocument();
  });

  it('Invite: пустой ник -> ошибка; ник -> POST redeem {token,nick}', async () => {
    const m = mockFetch({
      'GET /api/me': meOk,
      'POST /api/auth/redeem': () => ({ json: { ok: true } }),
    });
    // без WebAuthn после redeem сразу редирект на /
    renderApp(
      <Routes>
        <Route path="/invite/:token" element={<InviteScreen />} />
        <Route path="/" element={<div>HOME</div>} />
      </Routes>,
      '/invite/tok123',
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Продолжить' }));
    expect(await screen.findByText('Введи ник.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Ник'), { target: { value: '  Роман ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
    await waitFor(() => expect(m.calls.some((c) => c.key === 'POST /api/auth/redeem')).toBe(true));
    expect(m.calls.find((c) => c.key === 'POST /api/auth/redeem')!.body).toEqual({ token: 'tok123', nick: 'Роман' });
  });

  it('Invite для существующего пользователя Telegram: ника не просит, показывает чей аккаунт', async () => {
    const m = mockFetch({
      'GET /api/me': () => ({ status: 401, json: {} }),
      'POST /api/auth/invite-info': () => ({ json: { valid: true, existing: true, nick: 'Роман' } }),
      'POST /api/auth/redeem': () => ({ json: ME }),
    });
    renderApp(<Routes><Route path="/invite/:token" element={<InviteScreen />} /><Route path="/" element={<div>HOME</div>} /></Routes>, '/invite/tokX');
    expect(await screen.findByTestId('invite-existing')).toHaveTextContent('Роман');
    expect(screen.queryByLabelText('Ник')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Войти в свой аккаунт' }));
    await waitFor(() => expect(m.calls.some((c) => c.key === 'POST /api/auth/redeem')).toBe(true));
  });

  it('Invite: невалидный токен -> понятное сообщение', async () => {
    mockFetch({
      'GET /api/me': () => ({ status: 401, json: {} }),
      'POST /api/auth/redeem': () => ({ status: 400, json: { detail: 'bad' } }),
    });
    renderApp(<Routes><Route path="/invite/:token" element={<InviteScreen />} /></Routes>, '/invite/bad');
    fireEvent.change(await screen.findByLabelText('Ник'), { target: { value: 'X' } });
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(await screen.findByText(/недействительна или уже использована/)).toBeInTheDocument();
  });

  it('Offline: экран «Нет соединения» с кнопкой', async () => {
    mockFetch({ 'GET /api/me': meOk });
    renderApp(<Offline />);
    expect(await screen.findByText('Нет соединения')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
  });

  it('A2HS: показывается на iPhone один раз и запоминается', async () => {
    mockFetch({ 'GET /api/me': meOk });
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari');
    const { unmount } = renderApp(<A2hsBanner />);
    fireEvent.click(await screen.findByRole('button', { name: 'Понятно' }));
    expect(localStorage.getItem('fepra.a2hs.seen')).toBe('1');
    unmount();
    renderApp(<A2hsBanner />);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(/Добавь на экран/)).toBeNull();
  });

  it('isIosSafariBrowser: не показываем в standalone и не на Android', () => {
    const ios = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)';
    expect(isIosSafariBrowser(ios, false)).toBe(true);
    expect(isIosSafariBrowser(ios, true)).toBe(false);
    expect(isIosSafariBrowser('Mozilla/5.0 (Linux; Android 14)', false)).toBe(false);
  });

  it('Приглашение админа: создание отправляет тело по контракту и показывает ссылку', async () => {
    const m = mockFetch({
      'GET /api/me': () => ({ json: { ...ME, roles: { ...ME.roles, admin: true } } }),
      'GET /api/admin/invites': () => ({ json: [] }),
      'POST /api/admin/invites': () => ({ json: { token: 'abc', url: 'https://x.test/app/#/invite/abc' } }),
    });
    renderApp(<InvitesScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Создать ссылку' }));
    expect(await screen.findByTestId('invite-url')).toHaveTextContent('https://x.test/app/#/invite/abc');
    expect(m.calls.find((c) => c.key === 'POST /api/admin/invites')!.body).toEqual({
      role: 'athlete', gym: 'Universe', existing_user_id: null, ttl_hours: 72, note: '',
    });
  });
});
