import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { RecordScreen } from '../src/screens/record/RecordScreen';
import { WorkoutManageScreen } from '../src/screens/record/WorkoutManage';
import { GoalsScreen } from '../src/screens/Goals';
import { QuickWidgets } from '../src/screens/record/QuickWidgets';
import { DRAFT_KEY, loadDraft } from '../src/screens/record/draft';
import { ME, mockFetch, renderApp } from './helpers';

const meOk = () => ({ json: ME });

const FORM = {
  version: 1,
  blocks: [
    { index: 0, title: 'рывок', format: 'emom_strength', kind: 'strength', fields: [
      { key: '0.0', label: 'раунд 1 (вес×повторы)', type: 'weight_reps', unit: 'кг×повт', section: 'рывок', group: null, movement: 'рывок' },
    ] },
    { index: 1, title: 'WOD 1', format: 'for_time', kind: 'metcon', fields: [
      { key: '1.0', label: 'время (мм:сс)', type: 'time', unit: 'мм:сс', section: 'WOD 1', group: null, movement: null },
    ] },
  ],
};
const PARSED = {
  recognized: true, reason: null, board_text: '2 ТА: рывок 3x3\n3 WOD 20 бёрпи', format: 'other', engine_used: null,
  sport: 'weightlifting', blocks: [{ header: 'ТА' }, { header: 'WOD 1' }], blocks_verified: false, form: FORM,
  template_text: '', annotated: 'аннотация раундов',
};

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

function renderRecord() {
  return renderApp(<Routes><Route path="/record" element={<RecordScreen />} /></Routes>, '/record');
}

async function toBoardStep() {
  fireEvent.click(await screen.findByRole('button', { name: 'ТА' }));
  fireEvent.click(screen.getByRole('button', { name: 'Дальше' }));
}

describe('запись тренировки: сценарий целиком', () => {
  it('текст доски -> разбор (job) -> проверка -> форма -> PUT -> ambiguous -> resolve', async () => {
    let putBody: any = null;
    let putPath = '';
    const m = mockFetch({
      'GET /api/me': meOk,
      'POST /api/board/parse': () => ({ json: { job_id: 'j1' } }),
      'GET /api/jobs/j1': () => ({ json: { id: 'j1', status: 'done', error: null, result: PARSED } }),
      'PUT /api/workouts/UUID': () => ({ json: {} }),
    });
    // uuid известен только после рендера — подменяем обработчик PUT динамически
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? 'GET').toUpperCase();
      if (method === 'PUT' && url.startsWith('/api/workouts/')) {
        putPath = url;
        putBody = JSON.parse(String(init!.body));
        return new Response(JSON.stringify({
          activity_id: url.split('/').pop(), created: true, day: putBody.day, sport: 'weightlifting', score: '6:00', rpe: 8, scaling: 'rx',
          board_source: 'own', metcon_lines: ['WOD 1 — время: 6:00'], credited: [],
          ambiguous: [{ movement: 'рывок', family: 'snatch', weight: 80, reps: 3, variants: [{ id: 'squat_snatch', label: 'В сед' }, { id: 'power_snatch', label: 'В стойку' }] }],
          proposed_maxes: null, lifts_skipped_quota: false, bodyweight: 80,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return (m.fn as any)(input, init);
    }));
    renderRecord();
    await toBoardStep();
    fireEvent.click(screen.getByRole('button', { name: /Текстом/ }));
    fireEvent.change(screen.getByLabelText('Текстом'), { target: { value: '2 ТА: рывок 3x3\n3 WOD 20 бёрпи' } });
    fireEvent.click(screen.getByRole('button', { name: 'Распознать' }));

    // проверка доски
    expect(await screen.findByText('Проверь доску')).toBeInTheDocument();
    const parseCall = m.calls.find((c) => c.key === 'POST /api/board/parse')!;
    expect(parseCall.body).toMatchObject({ sport: 'weightlifting', engine: 'fast', text: expect.stringContaining('рывок') });
    fireEvent.click(screen.getByRole('button', { name: 'Принять' }));

    // форма результата
    fireEvent.change(screen.getByLabelText('раунд 1 (вес×повторы): кг'), { target: { value: '80' } });
    fireEvent.change(screen.getByLabelText('раунд 1 (вес×повторы): повт'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText(/время \(мм:сс\)/), { target: { value: '600' } });
    expect(screen.getByLabelText(/время \(мм:сс\)/)).toHaveValue('6:00');
    fireEvent.click(screen.getByRole('button', { name: '8' }));
    fireEvent.click(screen.getByRole('button', { name: 'RX' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    // после сохранения: вопрос про рывок
    expect(await screen.findByText(/какой вариант/)).toBeInTheDocument();
    expect(putPath).toMatch(/^\/api\/workouts\/[0-9a-f-]{36}$/);
    expect(putBody).toMatchObject({
      sport: 'weightlifting', rpe: 8, scaling: 'rx',
      board: { source: 'own', text: PARSED.board_text, blocks: PARSED.blocks },
      form_result: { '0.0': '80x3', '1.0': '6:00' },
    });

    const uuid = putPath.split('/').pop()!;
    (m.fn as any).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === `/api/workouts/${uuid}/lifts/resolve`) {
        expect(JSON.parse(String(init!.body))).toEqual({ movement: 'рывок', variant: 'power_snatch', weight: 80, reps: 3 });
        return new Response(JSON.stringify({ discipline: 'power_snatch', name: 'Рывок в стойку', weight: 80, reps: 3, est_1rm: 88 }), { status: 200 });
      }
      return new Response('{}', { status: 404 });
    });
    fireEvent.click(screen.getByRole('button', { name: 'В стойку' }));
    expect(await screen.findByText(/Рывок в стойку/)).toBeInTheDocument();
    expect(screen.queryByText(/какой вариант/)).toBeNull();
    expect(screen.getByText(/1ПМ ≈ 88 кг/)).toBeInTheDocument();
  });

  it('квота ИИ на фото: предлагаем ввести текст', async () => {
    mockFetch({
      'GET /api/me': meOk,
      'POST /api/board/parse': () => ({ json: { job_id: 'j2' } }),
      'GET /api/jobs/j2': () => ({ json: { status: 'done', result: { ...PARSED, recognized: false, reason: 'quota', form: { blocks: [] } } } }),
    });
    localStorage.setItem(DRAFT_KEY, JSON.stringify({
      v: 1, uuid: 'a6e0c0ee-9e6c-4c83-8d7e-000000000001', step: 'board', day: '2026-09-01', sport: 'crossfit', startTime: '09:00',
      source: 'photo', engine: 'fast', uploadId: 'up1', uploadName: 'b.jpg', boardText: '', parse: null, gymDay: null, values: {},
      rpe: null, scaling: null, bodyweight: '', freeText: '', duration: '', distance: '', saved: null, savedAt: Date.now(),
    }));
    renderRecord();
    fireEvent.click(await screen.findByRole('button', { name: 'Распознать' }));
    expect(await screen.findByText(/Лимит ИИ на сегодня исчерпан/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ввести текст доски' }));
    expect(screen.getByLabelText('Текстом')).toBeInTheDocument();
  });

  it('фото больше 10 МБ отклоняется на клиенте, без запросов', async () => {
    const m = mockFetch({ 'GET /api/me': meOk });
    renderRecord();
    await toBoardStep();
    fireEvent.click(screen.getByRole('button', { name: /Фото/ }));
    const file = new File(['x'], 'big.jpg', { type: 'image/jpeg' });
    Object.defineProperty(file, 'size', { value: 11 * 1024 * 1024 });
    fireEvent.change(screen.getByTestId('file-any'), { target: { files: [file] } });
    expect(await screen.findByText(/Файл больше 10 МБ/)).toBeInTheDocument();
    expect(m.calls.some((c) => c.key === 'POST /api/uploads')).toBe(false);
  });

  it('черновик: введённое переживает перезагрузку экрана', async () => {
    mockFetch({ 'GET /api/me': meOk });
    const first = renderApp(<RecordScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Бег' }));
    fireEvent.click(screen.getByRole('button', { name: 'Дальше' }));
    fireEvent.change(screen.getByLabelText('Длительность, мин'), { target: { value: '42' } });
    fireEvent.click(screen.getByRole('button', { name: '6' }));
    const uuid = loadDraft()!.uuid;
    first.unmount();

    renderApp(<RecordScreen />);
    expect(await screen.findByText(/Восстановил черновик/)).toBeInTheDocument();
    expect(screen.getByLabelText('Длительность, мин')).toHaveValue('42');
    expect(screen.getByRole('button', { name: '6' })).toHaveAttribute('aria-pressed', 'true');
    expect(loadDraft()!.uuid).toBe(uuid); // тот же UUID — повторный PUT идемпотентен
    fireEvent.click(screen.getByRole('button', { name: 'Начать заново' }));
    expect(await screen.findByText('Когда')).toBeInTheDocument();
    expect(loadDraft()!.uuid).not.toBe(uuid);
  });

  it('ошибка сети при сохранении: понятное сообщение, черновик остаётся', async () => {
    mockFetch({ 'GET /api/me': meOk });
    renderApp(<RecordScreen />);
    fireEvent.click(await screen.findByRole('button', { name: 'Бег' }));
    fireEvent.click(screen.getByRole('button', { name: 'Дальше' }));
    fireEvent.change(screen.getByLabelText('Длительность, мин'), { target: { value: '30' } });
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'PUT') throw new TypeError('network');
      return new Response(JSON.stringify(ME), { status: 200 });
    }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByText(/Введённое сохранено на телефоне/)).toBeInTheDocument();
    expect(loadDraft()?.duration).toBe('30');
  });
});

describe('proposed_maxes', () => {
  it('подтверждение исправленных максов -> POST /maxes', async () => {
    let sent: any = null;
    const id = '11111111-2222-4333-8444-555555555555';
    mockFetch({
      'GET /api/me': meOk,
      [`POST /api/workouts/${id}/maxes`]: (b) => {
        sent = b;
        return { json: { credited: [{ discipline: 'deadlift', name: 'Становая', weight: 150, reps: 3, est_1rm: 165 }], ambiguous: [], skipped_quota: false } };
      },
    });
    localStorage.setItem(DRAFT_KEY, JSON.stringify({
      v: 1, uuid: id, step: 'done', day: '2026-09-01', sport: 'crossfit', startTime: '', source: 'free', engine: 'fast', uploadId: null, uploadName: '',
      boardText: '', parse: null, gymDay: null, values: {}, rpe: null, scaling: null, bodyweight: '', freeText: 'x', duration: '', distance: '',
      saved: { activity_id: id, day: '2026-09-01', sport: 'crossfit', proposed_maxes: { maxes: [{ movement: 'становая тяга', weight_kg: 140, reps: 3 }] }, credited: [], ambiguous: [] },
      savedAt: Date.now(),
    }));
    renderRecord();
    const w = await screen.findByLabelText('становая тяга: кг');
    fireEvent.change(w, { target: { value: '150' } });
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
    expect(await screen.findByText(/165 кг/)).toBeInTheDocument();
    expect(sent).toEqual({ maxes: [{ movement: 'становая тяга', weight_kg: 150, reps: 3 }] });
  });
});

describe('правка и удаление', () => {
  const id = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
  const W = {
    id, day: '2026-09-01', sport: 'weightlifting', source: 'manual', score: '6:00', scaling: 'rx', rpe: 7, board_source: 'gym',
    updated_at: 't1', board_text: 'программа зала', form: FORM, form_values: { '1.0': '6:00' }, bodyweight: 80, editable: true, board_editable: false,
  };
  const path = `/workouts/x`;

  it('зальная доска недоступна с пояснением; PATCH шлёт только изменённое', async () => {
    let patched: any = null;
    mockFetch({
      'GET /api/me': meOk,
      [`GET /api/workouts/${id}`]: () => ({ json: W }),
      [`PATCH /api/workouts/${id}`]: (b) => { patched = b; return { json: { workout: W, credited: [], ambiguous: [], metcon_lines: [] } }; },
    });
    renderApp(<Routes><Route path="/w/:id" element={<WorkoutManageScreen />} /></Routes>, `/w/${id}`);
    const ta = await screen.findByLabelText('Текст доски');
    expect(ta).toBeDisabled();
    expect(screen.getByText(/нельзя править/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '9' }));
    fireEvent.change(screen.getByLabelText(/время \(мм:сс\)/), { target: { value: '530' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ rpe: 9, form_result: { '0.0': undefined, '1.0': '5:30' } });
    void path;
  });

  it('своя доска редактируется', async () => {
    mockFetch({ 'GET /api/me': meOk, [`GET /api/workouts/${id}`]: () => ({ json: { ...W, board_source: 'own', board_editable: true } }) });
    renderApp(<Routes><Route path="/w/:id" element={<WorkoutManageScreen />} /></Routes>, `/w/${id}`);
    expect(await screen.findByLabelText('Текст доски')).toBeEnabled();
  });

  it('удаление с подтверждением и «Отменить» (restore)', async () => {
    const calls: string[] = [];
    mockFetch({
      'GET /api/me': meOk,
      [`GET /api/workouts/${id}`]: () => { calls.push('GET'); return { json: W }; },
      [`DELETE /api/workouts/${id}`]: () => { calls.push('DELETE'); return { json: { id, deleted_at: 'x' } }; },
      [`POST /api/workouts/${id}/restore`]: () => { calls.push('RESTORE'); return { json: W }; },
    });
    renderApp(<Routes><Route path="/w/:id" element={<WorkoutManageScreen />} /></Routes>, `/w/${id}`);
    fireEvent.click(await screen.findByRole('button', { name: 'Удалить тренировку' }));
    expect(calls).not.toContain('DELETE'); // сначала спрашиваем
    const dlg = screen.getByRole('alertdialog');
    fireEvent.click(within(dlg).getByRole('button', { name: 'Да, удалить' }));
    expect(await screen.findByText('Тренировка удалена')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Отменить' }));
    await waitFor(() => expect(calls).toContain('RESTORE'));
    expect(await screen.findByLabelText('Текст доски')).toBeInTheDocument();
  });

  it('запись с часов не правится', async () => {
    mockFetch({ 'GET /api/me': meOk, [`GET /api/workouts/${id}`]: () => ({ json: { ...W, editable: false } }) });
    renderApp(<Routes><Route path="/w/:id" element={<WorkoutManageScreen />} /></Routes>, `/w/${id}`);
    expect(await screen.findByText(/пришла с часов/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Удалить тренировку' })).toBeNull();
  });
});

describe('цели, ПМ, вес тела, самочувствие', () => {
  const GOALS = {
    overall: { level: null, progress: 0, assessed: 0, total: 2 },
    goals: [{ id: 7, title: 'Присед -> 140', progress: { pct: 50, text: '100/140' } }],
    lifts: [{ id: 'back_squat', name: 'Присед', kind: 'lift', unit: 'kg', has_data: false }],
    benchmarks: [{ id: 'fran', name: 'Fran', kind: 'benchmark', unit: 'time', has_data: false }],
  };

  it('добавить числовую цель, завершить, архивировать', async () => {
    const sent: Record<string, any> = {};
    mockFetch({
      'GET /api/me': meOk,
      'GET /api/goals': () => ({ json: GOALS }),
      'POST /api/goals/items': (b) => { sent.add = b; return { json: { id: 8, status: 'active' } }; },
      'POST /api/goals/items/7/complete': () => { sent.complete = true; return { json: {} }; },
      'POST /api/goals/items/7/archive': () => { sent.archive = true; return { json: {} }; },
    });
    renderApp(<GoalsScreen />);
    await screen.findByText('Присед -> 140');
    fireEvent.click(screen.getByText('Добавить цель'));
    fireEvent.change(screen.getAllByLabelText('Дисциплина')[0], { target: { value: 'fran' } });
    fireEvent.change(screen.getByLabelText(/Цель \(/), { target: { value: '430' } });
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }));
    expect(await screen.findByText('Цель добавлена.')).toBeInTheDocument();
    expect(sent.add).toEqual({ kind: 'numeric', discipline: 'fran', target: '4:30' });
    fireEvent.click(screen.getByRole('button', { name: 'Завершить' }));
    await waitFor(() => expect(sent.complete).toBe(true));
    fireEvent.click(screen.getByRole('button', { name: 'В архив' }));
    await waitFor(() => expect(sent.archive).toBe(true));
  });

  it('цель по уровню и быстрый ввод ПМ (лифт) с уровнем в ответе', async () => {
    const sent: Record<string, any> = {};
    mockFetch({
      'GET /api/me': meOk,
      'GET /api/goals': () => ({ json: GOALS }),
      'POST /api/goals/items': (b) => { sent.goal = b; return { json: { id: 9 } }; },
      'POST /api/pm': (b) => { sent.pm = b; return { json: { discipline: 'back_squat', name: 'Присед', value: 100, reps: 3, est_1rm: 110, tier: { level: 'Средний', idx: 2 } } }; },
    });
    renderApp(<GoalsScreen />);
    await screen.findByText('Присед -> 140');
    fireEvent.click(screen.getByText('Добавить цель'));
    fireEvent.click(screen.getByRole('button', { name: 'Уровневая' }));
    fireEvent.change(screen.getAllByLabelText('Дисциплина')[0], { target: { value: 'back_squat' } });
    fireEvent.change(screen.getByLabelText('Уровень'), { target: { value: 'Элита' } });
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }));
    await screen.findByText('Цель добавлена.');
    expect(sent.goal).toEqual({ kind: 'level', discipline: 'back_squat', target: 'Элита' });

    fireEvent.click(screen.getByText('Быстрый ввод ПМ'));
    fireEvent.change(screen.getAllByLabelText('Дисциплина')[1], { target: { value: 'back_squat' } });
    fireEvent.change(screen.getByLabelText(/вес×повторы, например/), { target: { value: '100x3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Записать ПМ' }));
    expect(await screen.findByText(/1ПМ ≈ 110 кг/)).toBeInTheDocument();
    expect(screen.getByText(/уровень: Средний/)).toBeInTheDocument();
    expect(sent.pm).toEqual({ discipline: 'back_squat', value: 100, reps: 3 });
  });

  it('виджет на сводке: самочувствие и вес тела', async () => {
    const sent: Record<string, any> = {};
    mockFetch({
      'GET /api/me': meOk,
      'POST /api/feel': (b) => { sent.feel = b; return { json: { day: 'd', score: 8 } }; },
      'POST /api/bodyweight': (b) => { sent.bw = b; return { json: { day: 'd', kg: 79.5 } }; },
    });
    renderApp(<QuickWidgets />);
    fireEvent.click(await screen.findByRole('button', { name: '8' }));
    expect(await screen.findByText('Самочувствие 8 записано.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Вес тела, кг'), { target: { value: '79,5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Записать вес' }));
    expect(await screen.findByText(/79.5 кг записан/)).toBeInTheDocument();
    expect(sent.feel).toEqual({ score: 8 });
    expect(sent.bw.kg).toBe(79.5);
  });
});
