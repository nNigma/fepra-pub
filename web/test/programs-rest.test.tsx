import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { restEndAt, restRemaining, useCountdown } from '../src/screens/programs/rest';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('таймер отдыха по timestamp окончания', () => {
  it('чистые функции', () => {
    expect(restEndAt(1000, 90)).toBe(91_000);
    expect(restRemaining(91_000, 1000)).toBe(90);
    expect(restRemaining(91_000, 90_500)).toBe(1); // округление вверх
    expect(restRemaining(91_000, 200_000)).toBe(0);
  });

  it('отсчёт идёт от Date.now(), а не от числа тиков', () => {
    vi.setSystemTime(new Date('2026-09-29T10:00:00Z'));
    const end = restEndAt(Date.now(), 60);
    const done = vi.fn();
    const { result } = renderHook(() => useCountdown(end, done));
    expect(result.current).toBe(60);
    act(() => { vi.advanceTimersByTime(10_000); });
    expect(result.current).toBe(50);
  });

  it('экран был заблокирован: таймеры не тикали, но время ушло — после возврата остаток верный и onDone сработал один раз', () => {
    vi.setSystemTime(new Date('2026-09-29T10:00:00Z'));
    const end = restEndAt(Date.now(), 60);
    const done = vi.fn();
    const { result } = renderHook(() => useCountdown(end, done));
    // «блокировка»: часы уходят на 45 с вперёд без единого тика
    act(() => { vi.setSystemTime(new Date('2026-09-29T10:00:45Z')); vi.advanceTimersByTime(250); });
    expect(result.current).toBe(15);
    expect(done).not.toHaveBeenCalled();
    act(() => { vi.setSystemTime(new Date('2026-09-29T10:02:00Z')); document.dispatchEvent(new Event('visibilitychange')); });
    expect(result.current).toBe(0);
    expect(done).toHaveBeenCalledTimes(1);
    act(() => { vi.advanceTimersByTime(5000); });
    expect(done).toHaveBeenCalledTimes(1);
  });

  it('endAt=null: ноль и без таймеров', () => {
    const { result } = renderHook(() => useCountdown(null));
    expect(result.current).toBe(0);
  });
});
