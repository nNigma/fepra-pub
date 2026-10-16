// Тонкие помощники поверх request(): PUT/PATCH/DELETE и загрузка файла (фаза 5).
import { request } from './client';

export const rest = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body ?? {} }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body: body ?? {} }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

export interface UploadResult {
  id: string;
  url: string;
  mime: string;
  size: number;
  kind: string;
}

/** POST /api/uploads (multipart: file + kind). */
export function uploadFile(file: Blob, kind: 'meal' | 'board' | 'other', name = 'photo.jpg'): Promise<UploadResult> {
  const fd = new FormData();
  fd.append('file', file, name);
  fd.append('kind', kind);
  return request<UploadResult>('/api/uploads', { method: 'POST', body: fd });
}

export const q = encodeURIComponent;
