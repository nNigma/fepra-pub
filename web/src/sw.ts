// Service worker (injectManifest): предкэш оболочки + Web Push.
// Типы WebWorker не подключаем (конфликт с DOM в общем tsconfig), описываем минимум сами.
import { clientsClaim } from 'workbox-core';
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';
import { parsePushPayload, targetUrl } from './push-utils';

interface WaitEvent { waitUntil(p: Promise<unknown>): void }
interface PushEv extends WaitEvent { data: { json(): unknown; text(): string } | null }
interface ClickEv extends WaitEvent { notification: { close(): void; data?: { url?: string } } }
interface WinClient { url: string; focus(): Promise<unknown>; navigate?(url: string): Promise<unknown> }
declare global {
  interface Window { __WB_MANIFEST: { url: string; revision: string | null }[] }
}

interface SW {
  location: { origin: string };
  registration: { showNotification(title: string, o: Record<string, unknown>): Promise<void> };
  clients: {
    matchAll(o: { type: 'window'; includeUncontrolled: boolean }): Promise<WinClient[]>;
    openWindow(url: string): Promise<unknown>;
  };
  skipWaiting(): Promise<void>;
  addEventListener(type: string, cb: (e: never) => void): void;
}
const sw = self as unknown as SW;

sw.skipWaiting();
clientsClaim();
cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST); // workbox подставляет манифест вместо этого литерала
// кэшируем только оболочку; API и всё вне /app/ не трогаем
registerRoute(new NavigationRoute(createHandlerBoundToURL('/app/index.html'), { denylist: [/^\/api\//] }));

sw.addEventListener('push', ((event: PushEv) => {
  const p = parsePushPayload(event.data);
  const url = targetUrl(p.url, sw.location.origin);
  event.waitUntil(
    sw.registration.showNotification(p.title || 'FePra', {
      body: p.body ?? '',
      tag: p.tag || undefined,
      icon: '/app/icon-192.png',
      badge: '/app/icon-192.png',
      data: { url },
    }),
  );
}) as (e: never) => void);

sw.addEventListener('notificationclick', ((event: ClickEv) => {
  event.notification.close();
  const url = targetUrl(event.notification.data?.url, sw.location.origin);
  event.waitUntil(
    sw.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async (list) => {
      const app = list.find((c) => c.url.startsWith(`${sw.location.origin}/app/`));
      if (app) {
        try {
          if (app.navigate) await app.navigate(url);
        } catch {
          /* навигация не разрешена — просто фокус */
        }
        await app.focus();
        return;
      }
      await sw.clients.openWindow(url);
    }),
  );
}) as (e: never) => void);

export {};
