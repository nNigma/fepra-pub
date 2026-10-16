import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { ProgramsRoutes } from '../src/screens/programs';
import { NoticeBanners } from '../src/screens/programs/Notices';
import { ReferenceRow } from '../src/screens/programs/parts';
import { ME, mockFetch, renderApp } from './helpers';
import { session, setRow, TREE } from './programs-fixtures';
import { loadLocal } from '../src/screens/programs/benchState';

const meOk = () => ({ json: ME });
beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

const app = (path: string) => renderApp(<Routes><Route path="/programs/*" element={<ProgramsRoutes />} /></Routes>, path);

describe('каталог', () => {
  it('корень: planned приглушены с меткой «скоро»; planned-программа не ссылка; ТА ведёт вглубь', async () => {
    mockFetch({
      'GET /api/me': meOk,
      'GET /api/programs/tree': () => ({ json: { tree: TREE } }),
      'GET /api/enrollments': () => ({ json: { enrollments: [] } }),
    });
    app('/programs');
    const cf = await screen.findByText('Кроссфит');
    const row = cf.closest('.pg-row')!;
    expect(row).toHaveClass('soon');
    expect(within(row as HTMLElement).getByText('скоро')).toBeInTheDocument();
    expect(screen.getByText('ТА').closest('a')).toHaveAttribute('href', '/programs/node/weightlifting');
  });

  it('уровень «Кроссфит» — заглушка «наполняется», дочерняя planned-программа не кликабельна', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/programs/tree': () => ({ json: { tree: TREE } }) });
    app('/programs/node/crossfit');
    expect(await screen.findByText('Раздел наполняется')).toBeInTheDocument();
    const child = screen.getByText('Силовой цикл').closest('.pg-row')!;
    expect(child.tagName).not.toBe('A');
    expect(child).toHaveAttribute('aria-disabled', 'true');
  });

  it('система показывает активные программы ссылками на карточку, скрытые нет', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/programs/tree': () => ({ json: { tree: TREE } }) });
    app('/programs/node/bulgarian');
    const a = await screen.findByText('Цикл до теста');
    expect(a.closest('a')).toHaveAttribute('href', '/programs/p/bulgarian-peak-8w');
    expect(screen.queryByText('Скрытая')).toBeNull();
  });
});

describe('источник опорного веса в интерфейсе', () => {
  const show = (ref: any) => renderApp(<ReferenceRow ref_={ref} name="Рывок" names={{ clean_and_jerk: { ru: 'Толчок', en: 'C&J' } }} />);
  it('best + устарел', () => {
    show({ lift: 'x', kg: 80, source: 'best', stale: true, day: '2026-06-29' });
    expect(screen.getByText('Ваш максимум, 29.06')).toBeInTheDocument();
    expect(screen.getByText('устарел')).toBeInTheDocument();
    expect(screen.getByText('80')).toBeInTheDocument();
  });
  it('derived: от какого лифта, оценка', () => {
    show({ lift: 'x', kg: 64, source: 'derived', from: ['clean_and_jerk'] });
    expect(screen.getByText('Оценка от: Толчок')).toBeInTheDocument();
    expect(screen.getByText(/уточнится тест-сессией/)).toBeInTheDocument();
  });
  it('starter и needs_input', () => {
    show({ lift: 'x', kg: 48, source: 'starter', level: 'normal' });
    expect(screen.getByText('Стартовый уровень «Обычный»')).toBeInTheDocument();
  });
  it('needs_input без веса', () => {
    show({ lift: 'x', kg: null, source: 'needs_input' });
    expect(screen.getByText('Нужен ввод')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});

describe('карточка программы: запись', () => {
  const card = (needs: string[]) => ({
    slug: 'bulgarian-peak-8w', kind: 'program', title_ru: 'Цикл', title_en: 'Cycle', status: 'active', soon: false, enrollment_id: null,
    template: { version: 1, title: { ru: 'Цикл до теста', en: 'Cycle' }, summary: { ru: 'Кратко', en: 'Short' }, params: { weeks: 8 },
      required_lifts: ['squat_snatch'], optional_lifts: [], weeks: [{ week: 1, type: 'volume', title: { ru: 'Неделя 1', en: 'W1' }, sessions: 4 }] },
    requirements: {
      lifts: [{ lift: 'squat_snatch', name: { ru: 'Рывок в сед', en: 'Squat snatch' }, required: true,
        reference: needs.length ? { lift: 'squat_snatch', kg: null, source: 'needs_input', options: { careful: 34, normal: 48, experienced: 66 }, question: { ru: 'Твой максимум: рывок?', en: 'max?' } }
          : { lift: 'squat_snatch', kg: 55, source: 'best', day: '2026-09-13' } }],
      needs_input: needs, needs_test: needs,
    },
  });

  it('needs_input: три уровня с килограммами, выбор уровня -> POST с level, затем переход к записи', async () => {
    const m = mockFetch({
      'GET /api/me': meOk,
      'GET /api/programs/tree': () => ({ json: { tree: TREE } }),
      'GET /api/programs/bulgarian-peak-8w': () => ({ json: card(['squat_snatch']) }),
      'POST /api/programs/bulgarian-peak-8w/enroll': () => ({ json: { id: 'enr1' } }),
      'GET /api/enrollments/enr1': () => ({ status: 404, json: { detail: 'x' } }),
      'GET /api/enrollments/enr1/today': () => ({ status: 404, json: { detail: 'x' } }),
    });
    app('/programs/p/bulgarian-peak-8w');
    const start = await screen.findByRole('button', { name: 'Начать программу' });
    expect(start).toBeDisabled();
    expect(screen.getByText(/Рывок в сед: 48 кг/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: /Обычный/ }));
    expect(start).toBeEnabled();
    fireEvent.click(start);
    await waitFor(() => expect(m.calls.some((c) => c.key === 'POST /api/programs/bulgarian-peak-8w/enroll')).toBe(true));
    const body = m.calls.find((c) => c.key.startsWith('POST /api/programs'))!.body;
    expect(body.level).toBe('normal');
    expect(body.start_day).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(body.id).toBeTruthy();
  });

  it('ручной ввод максимума уходит в base_maxes', async () => {
    const m = mockFetch({
      'GET /api/me': meOk,
      'GET /api/programs/tree': () => ({ json: { tree: TREE } }),
      'GET /api/programs/bulgarian-peak-8w': () => ({ json: card(['squat_snatch']) }),
      'POST /api/programs/bulgarian-peak-8w/enroll': () => ({ json: { id: 'enr1' } }),
    });
    app('/programs/p/bulgarian-peak-8w');
    const input = await screen.findByLabelText(/Твой максимум: рывок/);
    fireEvent.change(input, { target: { value: '62,5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Начать программу' }));
    await waitFor(() => expect(m.calls.some((c) => c.key.includes('/enroll'))).toBe(true));
    expect(m.calls.find((c) => c.key.includes('/enroll'))!.body.base_maxes).toEqual({ squat_snatch: 62.5 });
  });

  it('422 needs_input: показываем вопросы из items', async () => {
    mockFetch({
      'GET /api/me': meOk,
      'GET /api/programs/tree': () => ({ json: { tree: TREE } }),
      'GET /api/programs/bulgarian-peak-8w': () => ({ json: card([]) }),
      'POST /api/programs/bulgarian-peak-8w/enroll': () => ({
        status: 422,
        json: { detail: 'нужны опорные веса', code: 'needs_input', items: { squat_snatch: { lift: 'squat_snatch', kg: null, source: 'needs_input', question: { ru: 'Сколько ты рвёшь?', en: '?' } } } },
      }),
    });
    app('/programs/p/bulgarian-peak-8w');
    fireEvent.click(await screen.findByRole('button', { name: 'Начать программу' }));
    expect(await screen.findByLabelText('Сколько ты рвёшь?')).toBeInTheDocument();
    expect(screen.getByText(/Сервер просит указать/)).toBeInTheDocument();
  });
});

describe('экран у помоста', () => {
  const putOk = (extra: object = {}) => ({ json: { set: { id: 's1' }, changed: [], why: null, session_status: 'in_progress', ...extra } });

  it('«Сделал» отправляет PUT и запускает таймер отдыха (rest_sec); отметка пишется в localStorage', async () => {
    const m = mockFetch({ 'GET /api/me': meOk, 'GET /api/sessions/sess1': () => ({ json: session() }), 'PUT /api/sessions/sess1/sets/s1': () => putOk() });
    app('/programs/session/sess1');
    const cur = await screen.findByTestId('current-set');
    expect(within(cur).getByText(/40 кг × 1/)).toBeInTheDocument();
    fireEvent.click(within(cur).getByRole('button', { name: /Сделал/ }));
    await waitFor(() => expect(m.calls.find((c) => c.key.startsWith('PUT'))).toBeTruthy());
    const put = m.calls.find((c) => c.key.startsWith('PUT'))!;
    expect(put.body).toMatchObject({ done_kg: 40, ok: true, reps: 1 });
    expect(screen.getByTestId('rest-left')).toHaveTextContent('1:30');
    expect(loadLocal('sess1')!.sets.s1).toMatchObject({ ok: true, done_kg: 40 });
    await waitFor(() => expect(loadLocal('sess1')!.sets.s1.pending).toBe(false));
    // следующий подход стал текущим
    expect(within(screen.getByTestId('current-set')).getByText(/50 кг × 1/)).toBeInTheDocument();
  });

  it('«сделал другой вес» шлёт введённый вес', async () => {
    const m = mockFetch({ 'GET /api/me': meOk, 'GET /api/sessions/sess1': () => ({ json: session() }), 'PUT /api/sessions/sess1/sets/s1': () => putOk() });
    app('/programs/session/sess1');
    const cur = await screen.findByTestId('current-set');
    fireEvent.change(within(cur).getByLabelText(/другой вес/), { target: { value: '37,5' } });
    fireEvent.click(within(cur).getByRole('button', { name: /Сделал/ }));
    await waitFor(() => expect(m.calls.find((c) => c.key.startsWith('PUT'))).toBeTruthy());
    expect(m.calls.find((c) => c.key.startsWith('PUT'))!.body.done_kg).toBe(37.5);
  });

  it('«Не вышло»: по changed перечитывается план и показывается «было → стало» с причиной', async () => {
    let served = 0;
    const before = session({}, [setRow('s1', 0, 60), setRow('s2', 1, 65), setRow('s3', 2, 70)]);
    const after = session({}, [setRow('s1', 0, 60, { ok: false, done_kg: 60 }), setRow('s2', 1, 60), setRow('s3', 2, 65)]);
    const m = mockFetch({
      'GET /api/me': meOk,
      'GET /api/sessions/sess1': () => ({ json: served++ === 0 ? before : after }),
      'PUT /api/sessions/sess1/sets/s1': () => putOk({ changed: ['s2', 's3'], why: { ru: 'Не вышло: остальные подходы на 5 кг легче.', en: 'Missed' } }),
    });
    app('/programs/session/sess1');
    fireEvent.click(await screen.findByRole('button', { name: /Не вышло/ }));
    const toast = await screen.findByTestId('miss-toast');
    expect(toast).toHaveTextContent('остальные подходы на 5 кг легче');
    expect(toast).toHaveTextContent('65 → 60');
    expect(toast).toHaveTextContent('70 → 65');
    expect(m.calls.find((c) => c.key.startsWith('PUT'))!.body.ok).toBe(false);
    // новый план виден в текущем подходе
    expect(within(screen.getByTestId('current-set')).getByText(/60 кг × 1/)).toBeInTheDocument();
  });

  it('перезагрузка страницы не теряет отметки: неподтверждённая отметка доотправляется, сервер — источник правды', async () => {
    // первая «жизнь»: сети нет, PUT падает, отметка остаётся pending в localStorage
    let online = false;
    const puts: any[] = [];
    mockFetch({
      'GET /api/me': meOk,
      'GET /api/sessions/sess1': () => ({ json: session() }),
      'PUT /api/sessions/sess1/sets/s1': (b) => { if (!online) throw new TypeError('offline'); puts.push(b); return putOk(); },
    });
    const first = app('/programs/session/sess1');
    fireEvent.click(await within(await screen.findByTestId('current-set')).findByRole('button', { name: /Сделал/ }));
    await screen.findByText(/неотправленных отметок 1/);
    expect(loadLocal('sess1')!.sets.s1.pending).toBe(true);
    first.unmount();

    // вторая «жизнь» (перезагрузка): сервер про подход не знает, локально помним -> доотправка
    online = true;
    app('/programs/session/sess1');
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toMatchObject({ done_kg: 40, ok: true });
    // и подход показан как выполненный, текущим стал второй
    expect(within(await screen.findByTestId('current-set')).getByText(/50 кг × 1/)).toBeInTheDocument();
    await waitFor(() => expect(loadLocal('sess1')!.sets.s1.pending).toBe(false));
  });

  it('чек-ин: POST и плашка why', async () => {
    const fresh = session({ checkin: null });
    const m = mockFetch({
      'GET /api/me': meOk,
      'GET /api/sessions/sess1': () => ({ json: fresh }),
      'POST /api/sessions/sess1/checkin': () => ({ json: { ...fresh, checkin: { tired: true }, why: 'Чек-ин: устал. Легче на 5 пунктов.' } }),
    });
    app('/programs/session/sess1');
    fireEvent.click(await screen.findByRole('button', { name: 'Устал' }));
    fireEvent.click(screen.getByRole('button', { name: 'Применить' }));
    expect(await screen.findByText(/Чек-ин: устал\. Легче на 5 пунктов/)).toBeInTheDocument();
    expect(m.calls.find((c) => c.key.endsWith('/checkin'))!.body).toEqual({ tired: true });
    expect(screen.queryByText('Как самочувствие?')).toBeNull();
  });

  it('тест-сессия: пояснение и попытки', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/sessions/sess1': () => ({ json: session({ kind: 'test', adjust: { level: 'none', delta_pct: 0, cap_pct: null, signals: [], postpone_advised: true } }, [setRow('s1', 0, 40, { kind: 'attempt', pct: 100 })]) }) });
    app('/programs/session/sess1');
    expect(await screen.findByText('Тест максимума', { selector: 'b' })).toBeInTheDocument();
    expect(screen.getByText(/лучше|советует перенести/i)).toBeInTheDocument();
    expect(screen.getByText(/попытка/)).toBeInTheDocument();
  });

  it('завершение: RPE -> finish, итог с новыми максами и «обновить опорные?»', async () => {
    const done = [setRow('s1', 0, 40, { ok: true, done_kg: 40 }), setRow('s2', 1, 50, { ok: true, done_kg: 50 })];
    const m = mockFetch({
      'GET /api/me': meOk,
      'GET /api/sessions/sess1': () => ({ json: session({}, done) }),
      'POST /api/sessions/sess1/finish': () => ({ json: { session_id: 'sess1', status: 'done', already: false, activity_id: 'a1', maxes: [{ lift: 'squat_snatch', kg: 65, reps: 1 }],
        refresh: [{ lift: 'squat_snatch', base_kg: 60, new_kg: 65, delta_kg: 5, ru: 'Новый максимум: 65 кг. Обновить опорные?', en: '' }], base_updated: [], enrollment_done: false } }),
      'POST /api/enrollments/enr1/refresh-base': () => ({ json: { id: 'enr1', refreshed: ['squat_snatch'] } }),
    });
    app('/programs/session/sess1');
    fireEvent.click(await screen.findByRole('button', { name: 'Завершить тренировку' }));
    fireEvent.click(screen.getByRole('button', { name: '7' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить итог' }));
    expect(await screen.findByText(/Тренировка сохранена/)).toBeInTheDocument();
    const fin = m.calls.find((c) => c.key.endsWith('/finish'))!;
    expect(fin.body.rpe).toBe(7);
    expect(fin.body.activity_id).toBeTruthy();
    expect(screen.getByText('65 кг')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Да, обновить' }));
    expect(await screen.findByText(/Обновлено: squat snatch|Обновлено: Рывок в сед/)).toBeInTheDocument();
    expect(m.calls.find((c) => c.key.endsWith('/refresh-base'))!.body).toEqual({ lifts: ['squat_snatch'] });
  });

  it('Wake Lock запрашивается, пока идёт тренировка', async () => {
    const release = vi.fn(async () => {});
    const request = vi.fn(async () => ({ release }));
    Object.defineProperty(navigator, 'wakeLock', { value: { request }, configurable: true });
    mockFetch({ 'GET /api/me': meOk, 'GET /api/sessions/sess1': () => ({ json: session() }) });
    const r = app('/programs/session/sess1');
    await screen.findByTestId('current-set');
    await waitFor(() => expect(request).toHaveBeenCalledWith('screen'));
    r.unmount();
    await act(async () => {});
    expect(release).toHaveBeenCalled();
    // @ts-expect-error чистим подмену
    delete navigator.wakeLock;
  });
});

describe('баннеры уведомлений', () => {
  it('Garmin просит войти: кнопка ведёт на экран Garmin и помечает прочитанным', async () => {
    const m = mockFetch({
      'GET /api/me': meOk,
      'GET /api/notices': () => ({ json: [{ id: 'n1', kind: 'garmin_expired', text: 'Garmin просит войти заново', created_at: 'x', read_at: null }] }),
      'POST /api/notices/n1/read': () => ({ json: { ok: true } }),
    });
    renderApp(<NoticeBanners />);
    expect(await screen.findByText('Garmin просит войти заново')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'Войти в Garmin' });
    expect(link).toHaveAttribute('href', '/profile/garmin');
    fireEvent.click(link);
    await waitFor(() => expect(m.calls.some((c) => c.key === 'POST /api/notices/n1/read')).toBe(true));
    expect(screen.queryByText('Garmin просит войти заново')).toBeNull();
  });
});

describe('карточка программы: описание и дни', () => {
  const described = () => ({
    slug: 'bulgarian-peak-8w', kind: 'program', title_ru: 'Цикл', title_en: 'Cycle', status: 'active', soon: false, enrollment_id: null,
    template: {
      version: 1, title: { ru: 'Цикл до теста', en: 'Cycle' }, summary: { ru: 'Кратко', en: 'Short' }, params: { weeks: 8 },
      required_lifts: ['squat_snatch'], optional_lifts: [],
      about: [
        { id: 'intro', title: { ru: 'Об этой программе', en: 'About' }, text: { ru: 'Восьминедельный цикл к тесту.', en: 'Eight weeks.' } },
        { id: 'what', title: { ru: 'Что такое болгарская система', en: 'What' }, text: { ru: 'Школа тяжёлой атлетики.', en: 'School.' } },
      ],
      week_types: { volume: { title: { ru: 'Объёмная неделя', en: 'Volume week' }, text: { ru: 'Самая лёгкая по весам.', en: 'Lightest.' } } },
      weeks: [{
        week: 1, type: 'volume', title: { ru: 'Неделя 1', en: 'W1' }, sessions: 1,
        days: [{ idx: 1, dow: 0, kind: 'normal', minutes: 30, title: { ru: 'Рывок + присед', en: 'Snatch + squat' },
          purpose: { ru: 'Рывок учит скорости под штангой.', en: 'Speed.' }, focus: { ru: ['рывок', 'присед'], en: ['snatch', 'squat'] }, intensity: 'base' }],
      }],
    },
    requirements: { lifts: [], needs_input: [], needs_test: [] },
  });

  it('есть блоки «О программе», а неделя раскрывается описанием каждого дня', async () => {
    mockFetch({ 'GET /api/me': meOk, 'GET /api/programs/tree': () => ({ json: { tree: TREE } }), 'GET /api/programs/bulgarian-peak-8w': () => ({ json: described() }) });
    app('/programs/p/bulgarian-peak-8w');
    expect(await screen.findByText('О программе')).toBeInTheDocument();
    expect(screen.getByText('Что такое болгарская система')).toBeInTheDocument();
    expect(screen.getByText('Восьминедельный цикл к тесту.')).toBeInTheDocument();
    expect(screen.getByText(/Пн · Рывок \+ присед/)).toBeInTheDocument();
    expect(screen.getByText('Рывок учит скорости под штангой.')).toBeInTheDocument();
    expect(screen.getByText('рывок')).toBeInTheDocument();
    expect(screen.getByText(/Самая лёгкая по весам/)).toBeInTheDocument();
  });
});
