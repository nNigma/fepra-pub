import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Node 25 подсовывает свой (неполный) глобальный localStorage поверх jsdom: заменяем на простую реализацию.
function memoryStorage(): Storage {
  let m = new Map<string, string>();
  return {
    get length() { return m.size; },
    clear: () => { m = new Map(); },
    getItem: (k) => (m.has(k) ? m.get(k)! : null),
    key: (i) => [...m.keys()][i] ?? null,
    removeItem: (k) => { m.delete(k); },
    setItem: (k, v) => { m.set(k, String(v)); },
  };
}
Object.defineProperty(globalThis, 'localStorage', { value: memoryStorage(), configurable: true, writable: true });
Object.defineProperty(window, 'localStorage', { value: globalThis.localStorage, configurable: true, writable: true });

afterEach(() => cleanup());
