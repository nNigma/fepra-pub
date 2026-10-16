// Обновление PWA без ручного «закрой и открой дважды».
// Новый service worker активируется сразу (skipWaiting + clientsClaim), но открытая страница
// остаётся на старом коде. Перезагружаем её один раз, когда сменился контроллер, и проверяем
// наличие новой версии при каждом возврате в приложение.

export function watchForUpdates(): void {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
  const sw = navigator.serviceWorker;
  // если контроллера ещё не было, это первая установка, а не обновление: перезагрузка не нужна
  let hadController = !!sw.controller;
  let reloading = false;
  sw.addEventListener('controllerchange', () => {
    if (!hadController) {
      hadController = true;
      return;
    }
    if (reloading) return;
    reloading = true;
    window.location.reload();
  });
  const check = () => {
    sw.getRegistration().then((r) => r?.update()).catch(() => undefined);
  };
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') check();
  });
  window.addEventListener('online', check);
}
