import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ResultAdd } from '../src/screens/comps/ResultAdd';
import { StageAdd } from '../src/screens/comps/StageAdd';
import { renderApp } from './helpers';

afterEach(() => vi.unstubAllGlobals());

function mockApi(routes: Record<string, () => { status?: number; json: unknown }>) {
  const calls: { key: string; body: any }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${(init?.method ?? 'GET').toUpperCase()} ${String(input).split('?')[0]}`;
    const raw = init?.body;
    calls.push({ key, body: raw instanceof FormData ? '[multipart]' : raw ? JSON.parse(String(raw)) : undefined });
    const h = routes[key];
    if (!h) return new Response('{}', { status: 404 });
    const r = h();
    return new Response(JSON.stringify(r.json), { status: r.status ?? 200, headers: { 'Content-Type': 'application/json' } });
  }));
  return calls;
}

async function shoot() {
  (URL as any).createObjectURL = () => 'blob:x';
  const cam = await screen.findByTestId('photo-cam');
  fireEvent.change(cam, { target: { files: [new File([new Uint8Array([1, 2, 3])], 'a.jpg', { type: 'image/jpeg' })] } });
}

describe('соревнования: фото -> пояснение -> «Отправить»', () => {
  it('этапы: разбор стартует только по кнопке и несёт пояснение', async () => {
    const calls = mockApi({
      'POST /api/uploads': () => ({ status: 201, json: { id: 'u1', url: '/api/uploads/u1', kind: 'other' } }),
      'POST /api/comp/events/5/stages/parse': () => ({ json: { job_id: 'j1' } }),
      'GET /api/jobs/j1': () => ({ json: { status: 'done', result: { recognized: false, reason: 'not_recognized', stages: [] } } }),
    });
    renderApp(<StageAdd eventId={5} divisionId={null} onDone={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Фото' }));
    await shoot();
    const send = screen.getByRole('button', { name: 'Отправить' });
    await waitFor(() => expect(send).not.toBeDisabled());
    expect(calls.some((c) => c.key.endsWith('/stages/parse'))).toBe(false);
    fireEvent.change(screen.getByLabelText(/Пояснение к фото/), { target: { value: 'второй день' } });
    fireEvent.click(send);
    await waitFor(() => expect(calls.find((c) => c.key.endsWith('/stages/parse'))?.body).toEqual({ upload_id: 'u1', division_id: null, note: 'второй день' }));
  });

  it('результаты: то же самое, пояснение уходит в note', async () => {
    const calls = mockApi({
      'POST /api/uploads': () => ({ status: 201, json: { id: 'u2', url: '/api/uploads/u2', kind: 'other' } }),
      'POST /api/comp/events/5/results/parse': () => ({ json: { job_id: 'j2' } }),
      'GET /api/jobs/j2': () => ({ json: { status: 'done', result: { recognized: false, reason: 'not_recognized', rows: [] } } }),
    });
    renderApp(<ResultAdd eventId={5} divisionId={null} stages={[]} onDone={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Фото' }));
    await shoot();
    const send = screen.getByRole('button', { name: 'Отправить' });
    await waitFor(() => expect(send).not.toBeDisabled());
    expect(calls.some((c) => c.key.endsWith('/results/parse'))).toBe(false);
    fireEvent.change(screen.getByLabelText(/Пояснение к фото/), { target: { value: 'я в синей майке' } });
    fireEvent.click(send);
    await waitFor(() => expect(calls.find((c) => c.key.endsWith('/results/parse'))?.body).toMatchObject({ upload_id: 'u2', note: 'я в синей майке' }));
  });
});
