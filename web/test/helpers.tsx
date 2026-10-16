import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { vi } from 'vitest';
import { I18nProvider } from '../src/i18n';
import { SessionProvider } from '../src/lib/session';
import type { Me } from '../src/api/types';

export const ME: Me = {
  id: 1, nick: 'Тест', lang: 'ru', roles: { admin: false, pro: true, coach: false },
  gym: 'Universe', has_passkey: false, garmin: { connected: false, status: 'disconnected' }, public_url: null,
};

type Handler = (body: any, url: string) => { status?: number; json?: unknown } | Promise<{ status?: number; json?: unknown }>;

/** Подмена fetch: ключ "METHOD /path" (без query) -> обработчик. Возвращает список вызовов. */
export function mockFetch(routes: Record<string, Handler>) {
  const calls: { key: string; body: any; url: string }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    const key = `${method} ${url.split('?')[0]}`;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ key, body, url });
    const h = routes[key];
    if (!h) return new Response(JSON.stringify({ detail: 'no route ' + key }), { status: 404 });
    const r = await h(body, url);
    return new Response(JSON.stringify(r.json ?? {}), { status: r.status ?? 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fn);
  return { calls, fn };
}

export function renderApp(ui: ReactElement, path = '/') {
  return render(
    <I18nProvider initial="ru">
      <SessionProvider>
        <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
      </SessionProvider>
    </I18nProvider>,
  );
}
