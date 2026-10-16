import { useEffect, useRef, useState } from 'react';

// Таймер отдыха считает от момента окончания (epoch ms), а не тикает счётчиком:
// при блокировке экрана setInterval замирает, а Date.now() продолжает идти.

export function restEndAt(now: number, restSec: number): number {
  return now + Math.max(0, Math.round(restSec)) * 1000;
}

/** Остаток в целых секундах (округляем вверх, чтобы «0:00» показывался только в момент конца). */
export function restRemaining(endAt: number, now: number): number {
  return Math.max(0, Math.ceil((endAt - now) / 1000));
}

/**
 * Обратный отсчёт до `endAt`. `onDone` вызывается один раз, когда остаток стал 0
 * (в т.ч. если приложение вернулось из фона уже после конца).
 */
export function useCountdown(endAt: number | null, onDone?: () => void, tickMs = 250): number {
  const [left, setLeft] = useState(() => (endAt == null ? 0 : restRemaining(endAt, Date.now())));
  const doneRef = useRef(onDone);
  doneRef.current = onDone;
  useEffect(() => {
    if (endAt == null) {
      setLeft(0);
      return;
    }
    let fired = false;
    const tick = () => {
      const r = restRemaining(endAt, Date.now());
      setLeft(r);
      if (r === 0 && !fired) {
        fired = true;
        clearInterval(id);
        doneRef.current?.();
      }
    };
    const id = setInterval(tick, tickMs);
    const vis = () => {
      if (document.visibilityState === 'visible') tick();
    };
    document.addEventListener('visibilitychange', vis);
    tick();
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', vis);
    };
  }, [endAt, tickMs]);
  return left;
}

/** Вибрация и звук по окончании отдыха, если платформа разрешает (iOS Safari вибрацию не даёт). */
export function alertRestOver(): void {
  try {
    navigator.vibrate?.([250, 120, 250]);
  } catch {
    /* запрещено */
  }
  beep();
}

let audio: AudioContext | null = null;

/** Вызывать из обработчика тапа: без жеста браузер не даст запустить звук позже. */
export function primeAudio(): void {
  try {
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    audio ??= new AC();
    if (audio.state === 'suspended') void audio.resume();
  } catch {
    /* нет звука */
  }
}

function beep(): void {
  try {
    if (!audio) return;
    const now = audio.currentTime;
    for (const [i, f] of [880, 880, 1175].entries()) {
      const o = audio.createOscillator();
      const g = audio.createGain();
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, now + i * 0.22);
      g.gain.exponentialRampToValueAtTime(0.3, now + i * 0.22 + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.22 + 0.18);
      o.connect(g).connect(audio.destination);
      o.start(now + i * 0.22);
      o.stop(now + i * 0.22 + 0.2);
    }
  } catch {
    /* нет звука */
  }
}

/** Screen Wake Lock: не гасим экран, пока идёт сессия. Возвращает true, если API доступен. */
export function useWakeLock(active: boolean): boolean {
  const supported = typeof navigator !== 'undefined' && 'wakeLock' in navigator;
  useEffect(() => {
    if (!active || !supported) return;
    let lock: WakeLockSentinel | null = null;
    let alive = true;
    const acquire = async () => {
      try {
        lock = await navigator.wakeLock.request('screen');
        if (!alive) void lock.release();
      } catch {
        /* отказ (экономия заряда) — экран может погаснуть */
      }
    };
    const vis = () => {
      if (document.visibilityState === 'visible') void acquire(); // lock снимается при сворачивании
    };
    void acquire();
    document.addEventListener('visibilitychange', vis);
    return () => {
      alive = false;
      document.removeEventListener('visibilitychange', vis);
      void lock?.release().catch(() => {});
    };
  }, [active, supported]);
  return supported;
}
