import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, onNetworkError, onUnauthorized, request, setAsUser, withAs } from '../src/api/client';
import { mockFetch } from './helpers';

afterEach(() => {
  vi.unstubAllGlobals();
  onUnauthorized(null);
  onNetworkError(null);
  setAsUser(null);
});

describe('api client', () => {
  it('withAs подставляет ?as= только когда задан', () => {
    expect(withAs('/api/summary')).toBe('/api/summary');
    expect(withAs('/api/summary', '42')).toBe('/api/summary?as=42');
    expect(withAs('/api/nutrition?day=2026-09-01', '42')).toBe('/api/nutrition?day=2026-09-01&as=42');
  });

  it('GET отчёта уходит с cookie same-origin и с as в админ-режиме', async () => {
    const m = mockFetch({ 'GET /api/summary': () => ({ json: { ok: 1 } }) });
    setAsUser('7');
    await api.get('/api/summary');
    expect(m.calls[0].url).toBe('/api/summary?as=7');
    expect((m.fn.mock.calls[0][1] as RequestInit).credentials).toBe('same-origin');
  });

  it('POST шлёт JSON', async () => {
    const m = mockFetch({ 'POST /api/lang': (b) => ({ json: b }) });
    const r = await api.post<{ lang: string }>('/api/lang', { lang: 'en' });
    expect(r.lang).toBe('en');
    expect(m.calls[0].body).toEqual({ lang: 'en' });
  });

  it('401 вызывает обработчик выхода, quiet401 — нет', async () => {
    mockFetch({ 'GET /api/x': () => ({ status: 401, json: { detail: 'nope' } }) });
    const h = vi.fn();
    onUnauthorized(h);
    await expect(request('/api/x')).rejects.toMatchObject({ status: 401, detail: 'nope' });
    expect(h).toHaveBeenCalledTimes(1);
    await expect(request('/api/x', { quiet401: true })).rejects.toBeInstanceOf(ApiError);
    expect(h).toHaveBeenCalledTimes(1);
  });

  it('потеря сети -> ApiError(0) и обработчик сети', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    const h = vi.fn();
    onNetworkError(h);
    const e = (await request('/api/x').catch((x) => x)) as ApiError;
    expect(e).toBeInstanceOf(ApiError);
    expect(e.isNetwork).toBe(true);
    expect(h).toHaveBeenCalledTimes(1);
  });

  it('разбирает detail из строки и из списка ошибок FastAPI', async () => {
    mockFetch({
      'GET /api/a': () => ({ status: 422, json: { detail: [{ msg: 'bad' }, { msg: 'worse' }] } }),
      'GET /api/b': () => ({ status: 403, json: { detail: 'нужен Pro' } }),
    });
    await expect(request('/api/a')).rejects.toMatchObject({ detail: 'bad; worse' });
    await expect(request('/api/b')).rejects.toMatchObject({ status: 403, detail: 'нужен Pro' });
  });
});
