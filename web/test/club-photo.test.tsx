import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { ClubEditScreen } from '../src/screens/club/ClubEdit';
import { ME, renderApp } from './helpers';

const COACH = { ...ME, roles: { admin: false, pro: false, coach: true } };
const BOARD = 'Фронтальный присед 5×5\nWod#1\n21-15-9';

// свой перехват fetch: общий mockFetch разбирает тело как JSON и не понимает multipart-загрузку
type H = () => { status?: number; json?: unknown };
function mockFetch(rs: Record<string, H>) {
  const calls: { key: string; body: unknown }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${(init?.method ?? 'GET').toUpperCase()} ${String(input).split('?')[0]}`;
    const raw = init?.body;
    const body = raw instanceof FormData ? '[multipart]' : raw ? JSON.parse(String(raw)) : undefined;
    calls.push({ key, body });
    const h = rs[key];
    if (!h) return new Response(JSON.stringify({ detail: 'no route ' + key }), { status: 404 });
    const r = h();
    return new Response(JSON.stringify(r.json ?? {}), { status: r.status ?? 200, headers: { 'Content-Type': 'application/json' } });
  }));
  return { calls };
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

function routes(parsed: object) {
  return {
    'GET /api/me': () => ({ json: COACH }),
    'GET /api/club/program': () => ({ json: { gym: 'Universe', day: '2026-09-29', program: null, last_day: null, can_manage: true } }),
    'GET /api/club/dictionary': () => ({ json: [] }),
    'POST /api/uploads': () => ({ json: { id: 'up1', url: '/api/uploads/up1', mime: 'image/jpeg', size: 10, kind: 'board' } }),
    'POST /api/club/program/parse': () => ({ json: { job_id: 'j1' } }),
    'GET /api/jobs/j1': () => ({ json: { status: 'done', result: parsed } }),
    'POST /api/club/program/preview': () => ({ json: { raw_text: BOARD, format: 'other', canon: ['front_squat'], unknown: [], annotated: BOARD } }),
  };
}

function renderEdit() {
  return renderApp(<Routes><Route path="/club/edit" element={<ClubEditScreen />} /></Routes>, '/club/edit?day=2026-09-29');
}

function pickFile(testId: string) {
  const input = screen.getByTestId(testId) as HTMLInputElement;
  const file = new File([new Uint8Array(20)], 'board.jpg', { type: 'image/jpeg' });
  fireEvent.change(input, { target: { files: [file] } });
}

describe('тренер загружает фото доски', () => {
  it('фото распознаётся, текст попадает в редактор и открывается предпросмотр', async () => {
    const { calls } = mockFetch(routes({ recognized: true, reason: null, board_text: BOARD }));
    renderEdit();
    await screen.findByText(/Программа по фото доски/);
    pickFile('club-file');
    await waitFor(() => expect((document.querySelector('textarea') as HTMLTextAreaElement).value).toBe(BOARD));
    expect(calls.map((c) => c.key)).toEqual(expect.arrayContaining([
      'POST /api/uploads', 'POST /api/club/program/parse', 'POST /api/club/program/preview']));
    expect(calls.find((c) => c.key === 'POST /api/club/program/parse')?.body).toEqual({ upload_id: 'up1', engine: 'fast' });
    expect(await screen.findByText(/Доска распознана/)).toBeTruthy();
  });

  it('не распознано: понятное сообщение, текст не затирается', async () => {
    mockFetch(routes({ recognized: false, reason: 'not_recognized', board_text: null }));
    renderEdit();
    await screen.findByText(/Программа по фото доски/);
    pickFile('club-cam');
    expect(await screen.findByText(/Не удалось распознать доску/)).toBeTruthy();
    expect((document.querySelector('textarea') as HTMLTextAreaElement).value).toBe('');
  });

  it('слишком большой файл не отправляется', async () => {
    const { calls } = mockFetch(routes({ recognized: true, board_text: BOARD }));
    renderEdit();
    await screen.findByText(/Программа по фото доски/);
    const input = screen.getByTestId('club-file') as HTMLInputElement;
    const big = new File([new Uint8Array(1)], 'big.jpg', { type: 'image/jpeg' });
    Object.defineProperty(big, 'size', { value: 11 * 1024 * 1024 });
    fireEvent.change(input, { target: { files: [big] } });
    expect(await screen.findByText(/Фото больше 10 МБ/)).toBeTruthy();
    expect(calls.some((c) => c.key === 'POST /api/uploads')).toBe(false);
  });
});
