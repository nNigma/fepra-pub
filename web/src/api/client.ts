// Единый API-клиент: fetch + cookie-сессия (same-origin), типизированные ошибки.

export class ApiError extends Error {
  status: number;
  detail: string;
  /** машинный код ошибки бэкенда (`needs_input`, `closed`, …), если пришёл */
  code?: string;
  /** разобранное тело ошибки (например `items` у 422 needs_input) */
  body?: Record<string, unknown>;
  /** 422 профиля и др.: {поле: сообщение} */
  fields?: Record<string, string>;
  constructor(status: number, detail: string, fields?: Record<string, string>) {
    super(detail || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.fields = fields;
  }
  get isNetwork(): boolean {
    return this.status === 0;
  }
}

type Handler = (e: ApiError) => void;

let unauthorizedHandler: Handler | null = null;
let networkHandler: Handler | null = null;
let asUser: string | null = null;

/** 401 на любой запрос -> экран входа. Регистрирует SessionProvider. */
export function onUnauthorized(h: Handler | null): void {
  unauthorizedHandler = h;
}
/** Потеря сети -> экран «нет соединения». */
export function onNetworkError(h: Handler | null): void {
  networkHandler = h;
}

/** Админ-режим `?as=`: кого смотрим. Подставляется только в GET отчётов. */
export function setAsUser(id: string | null): void {
  asUser = id;
}
export function getAsUser(): string | null {
  return asUser;
}

export function withAs(path: string, as: string | null = asUser): string {
  if (!as) return path;
  return path + (path.includes('?') ? '&' : '?') + 'as=' + encodeURIComponent(as);
}

interface Opts {
  method?: string;
  body?: unknown;
  /** не дёргать глобальный обработчик 401 (для /api/me и форм входа) */
  quiet401?: boolean;
  signal?: AbortSignal;
}

async function parseError(
  res: Response,
): Promise<{ detail: string; body?: Record<string, unknown>; fields?: Record<string, string> }> {
  try {
    const j = (await res.json()) as Record<string, unknown>;
    const f =
      j.fields && typeof j.fields === 'object' && !Array.isArray(j.fields)
        ? (j.fields as Record<string, string>)
        : undefined;
    const d = j.detail;
    if (typeof d === 'string') return { detail: d, body: j, fields: f };
    if (Array.isArray(d)) {
      return { detail: d.map((x) => (x as { msg?: string }).msg ?? '').join('; '), body: j, fields: f };
    }
    return { detail: res.statusText, body: j, fields: f };
  } catch {
    /* не JSON */
  }
  return { detail: res.statusText };
}

export async function request<T>(path: string, opts: Opts = {}): Promise<T> {
  const init: RequestInit = {
    method: opts.method ?? 'GET',
    credentials: 'same-origin',
    headers: {},
    signal: opts.signal,
  };
  if (typeof FormData !== 'undefined' && opts.body instanceof FormData) {
    init.body = opts.body; // multipart: границу и Content-Type ставит браузер
  } else if (opts.body !== undefined) {
    (init.headers as Record<string, string>)['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    const err = new ApiError(0, 'network');
    networkHandler?.(err);
    throw err;
  }
  if (!res.ok) {
    const parsed = await parseError(res);
    const err = new ApiError(res.status, parsed.detail, parsed.fields);
    err.body = parsed.body;
    if (typeof parsed.body?.code === 'string') err.code = parsed.body.code;
    if (res.status === 401 && !opts.quiet401) unauthorizedHandler?.(err);
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, o: Opts = {}) => request<T>(withAs(path), o),
  /** GET без подстановки ?as= (служебные эндпоинты, не отчёты) */
  getPlain: <T>(path: string, o: Opts = {}) => request<T>(path, o),
  post: <T>(path: string, body?: unknown, o: Opts = {}) =>
    request<T>(path, { ...o, method: 'POST', body: body ?? {} }),
};
