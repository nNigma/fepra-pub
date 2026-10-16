// Общие мелочи экранов фазы 5.
import { useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/client';
import { uploadFile, type UploadResult } from '../api/rest';
import { useT } from '../i18n';
import { shrinkImage } from '../lib/image';
import { isPro } from '../lib/roles';
import { useSession } from '../lib/session';

export function BackLink({ to, label }: { to: string; label?: string }) {
  const t = useT();
  return <Link className="back" style={{ color: 'var(--mut)' }} to={to}>‹ {label ?? t('common.back')}</Link>;
}

export function Field({ label, error, hint, children }: { label: string; error?: string | null; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && !error && <small className="mut" style={{ display: 'block', marginTop: 3 }}>{hint}</small>}
      {error && <small role="alert" style={{ display: 'block', marginTop: 3, color: 'var(--red)' }}>{error}</small>}
    </label>
  );
}

/** Текст ошибки API для пользователя (403/429 и т.д.) */
export function apiMessage(e: unknown, t: (k: string, p?: Record<string, string | number>) => string): string {
  if (e instanceof ApiError) {
    if (e.isNetwork) return t('net.offline_title');
    if (e.status === 403) return e.detail && /pro/i.test(e.detail) ? t('err.pro') : t('err.forbidden');
    return e.detail || t('err.generic', { msg: e.status });
  }
  const m = (e as Error)?.message;
  return m === 'timeout' ? t('f5.timeout') : m || t('err.generic', { msg: '?' });
}

/** Раздел только для Pro: не Pro — объяснение и «попроси админа». */
export function ProGate({ children }: { children: ReactNode }) {
  const t = useT();
  const { me } = useSession();
  if (!me) return null;
  if (isPro(me)) return <>{children}</>;
  return (
    <div className="card" role="note">
      <h2 style={{ marginTop: 0 }}>{t('pro.title')}</h2>
      <p>{t('pro.text')}</p>
      <p className="mut">{t('pro.ask_admin')}</p>
    </div>
  );
}

/** Доступ по условию; иначе сообщение «нет доступа». */
export function Guard({ ok, children }: { ok: boolean; children: ReactNode }) {
  const t = useT();
  if (!ok) return <div className="msg err" role="alert">{t('err.forbidden')}</div>;
  return <>{children}</>;
}

/** Выбор фото (камера/галерея) -> загрузка -> onUploaded. */
export function PhotoPicker({
  kind, label, onUploaded, disabled,
}: { kind: 'meal' | 'board' | 'other'; label: string; onUploaded: (u: UploadResult, preview: string) => void; disabled?: boolean }) {
  const t = useT();
  const ref = useRef<HTMLInputElement>(null);
  const cam = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function pick(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const blob = await shrinkImage(file);
      const up = await uploadFile(blob, kind, file.name || 'photo.jpg');
      onUploaded(up, URL.createObjectURL(blob));
    } catch (e) {
      setErr(apiMessage(e, t));
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = '';
      if (cam.current) cam.current.value = '';
    }
  }
  return (
    <>
      <input ref={cam} type="file" accept="image/*" capture="environment" className="hidden-file" data-testid="photo-cam" onChange={(e) => void pick(e.target.files?.[0])} />
      <input ref={ref} type="file" accept="image/*" className="hidden-file" data-testid="photo-file" onChange={(e) => void pick(e.target.files?.[0])} />
      <div role="group" aria-label={label} style={{ display: 'flex', gap: 8 }}>
        <button type="button" className="btn primary" style={{ flex: 1 }} disabled={busy || disabled} onClick={() => cam.current?.click()}>
          📷 {busy ? t('f5.uploading') : t('f5.photo_camera')}
        </button>
        <button type="button" className="btn" style={{ flex: 1 }} disabled={busy || disabled} onClick={() => ref.current?.click()}>
          🖼 {t('f5.photo_gallery')}
        </button>
      </div>
      {err && <div className="msg err" role="alert">{err}</div>}
    </>
  );
}

export function todayIso(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function shiftDay(iso: string, delta: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  return todayIso(new Date(y, m - 1, d + delta));
}
