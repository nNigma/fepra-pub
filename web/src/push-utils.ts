// Чистые функции service worker'а (вынесены ради тестов; в sw.ts импортируются).

export interface PushPayload {
  title?: string;
  body?: string;
  url?: string;
  tag?: string;
}

/** Разбор payload: JSON {title, body, url, tag}; не-JSON текст считаем телом. */
export function parsePushPayload(raw: { json(): unknown; text(): string } | null | undefined): PushPayload {
  if (!raw) return {};
  try {
    const j = raw.json();
    if (j && typeof j === 'object') return j as PushPayload;
  } catch {
    /* не JSON */
  }
  try {
    const t = raw.text();
    return t ? { body: t } : {};
  } catch {
    return {};
  }
}

/** Ссылка из уведомления: только наш origin и путь под /app/, иначе главная приложения. */
export function targetUrl(url: string | undefined, origin: string): string {
  const fallback = `${origin}/app/`;
  if (!url) return fallback;
  try {
    const u = new URL(url, origin);
    if (u.origin !== origin || !u.pathname.startsWith('/app/')) return fallback;
    return u.href;
  } catch {
    return fallback;
  }
}
