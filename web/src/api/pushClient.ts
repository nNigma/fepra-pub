// Браузерная сторона Web Push: разрешение, подписка, отписка.
import { pushApi, type PushSubJSON } from './programs';

/** base64url (VAPID public key) -> Uint8Array для applicationServerKey. */
export function urlBase64ToUint8Array(b64url: string): Uint8Array<ArrayBuffer> {
  const pad = '='.repeat((4 - (b64url.length % 4)) % 4);
  const b64 = (b64url + pad).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export function pushSupported(): boolean {
  return typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

export type PushState = 'unsupported' | 'denied' | 'on' | 'off';

async function registration(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.ready;
}

export async function currentPushState(): Promise<PushState> {
  if (!pushSupported()) return 'unsupported';
  if (Notification.permission === 'denied') return 'denied';
  try {
    const sub = await (await registration()).pushManager.getSubscription();
    return sub && Notification.permission === 'granted' ? 'on' : 'off';
  } catch {
    return 'off';
  }
}

export class PushError extends Error {
  reason: 'unsupported' | 'denied' | 'no_key' | 'failed';
  constructor(reason: PushError['reason'], msg?: string) {
    super(msg ?? reason);
    this.reason = reason;
  }
}

export async function enablePush(): Promise<void> {
  if (!pushSupported()) throw new PushError('unsupported');
  let key: string;
  try {
    key = (await pushApi.key()).public_key;
  } catch {
    throw new PushError('no_key');
  }
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') throw new PushError('denied');
  const reg = await registration();
  let sub = await reg.pushManager.getSubscription();
  sub ??= await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) });
  const j = sub.toJSON() as Partial<PushSubJSON>;
  if (!j.endpoint || !j.keys?.p256dh || !j.keys.auth) throw new PushError('failed', 'bad subscription');
  await pushApi.subscribe({ endpoint: j.endpoint, keys: { p256dh: j.keys.p256dh, auth: j.keys.auth } });
}

export async function disablePush(): Promise<void> {
  if (!pushSupported()) return;
  const sub = await (await registration()).pushManager.getSubscription();
  if (!sub) return;
  try {
    await pushApi.unsubscribe(sub.endpoint);
  } finally {
    await sub.unsubscribe();
  }
}
