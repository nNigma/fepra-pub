import { describe, expect, it, vi } from 'vitest';
import { watchForUpdates } from '../src/sw-update';

function fakeSw(controller: unknown) {
  const listeners: Record<string, () => void> = {};
  const update = vi.fn().mockResolvedValue(undefined);
  const sw = {
    controller,
    addEventListener: (t: string, cb: () => void) => { listeners[t] = cb; },
    getRegistration: vi.fn().mockResolvedValue({ update }),
  };
  Object.defineProperty(globalThis.navigator, 'serviceWorker', { value: sw, configurable: true });
  return { listeners, update, sw };
}

describe('автообновление PWA', () => {
  it('смена контроллера при уже работавшем SW перезагружает страницу один раз', () => {
    const reload = vi.fn();
    Object.defineProperty(window, 'location', { value: { reload }, configurable: true });
    const { listeners } = fakeSw({});
    watchForUpdates();
    listeners.controllerchange();
    listeners.controllerchange();
    expect(reload).toHaveBeenCalledTimes(1);
  });
  it('первая установка (контроллера не было) страницу не перезагружает', () => {
    const reload = vi.fn();
    Object.defineProperty(window, 'location', { value: { reload }, configurable: true });
    const { listeners } = fakeSw(null);
    watchForUpdates();
    listeners.controllerchange();
    expect(reload).not.toHaveBeenCalled();
  });
  it('при возврате в приложение проверяет наличие новой версии', async () => {
    const { update } = fakeSw({});
    watchForUpdates();
    document.dispatchEvent(new Event('visibilitychange'));
    await Promise.resolve();
    await Promise.resolve();
    expect(update).toHaveBeenCalled();
  });
});
