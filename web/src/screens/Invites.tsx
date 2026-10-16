import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { endpoints } from '../api/endpoints';
import type { Invite, InviteIn } from '../api/types';
import { useT } from '../i18n';
import { inviteUrl } from '../lib/jobs';
import { useSession } from '../lib/session';
import { useFetch } from '../lib/useFetch';

export function InvitesScreen() {
  const t = useT();
  const { me } = useSession();
  const list = useFetch(() => endpoints.invites(), 'invites');
  const [role, setRole] = useState<InviteIn['role']>('athlete');
  const [gymInput, setGym] = useState<string | null>(null); // null — не трогали, берём зал админа
  const gym = gymInput ?? me?.gym ?? '';
  const [existing, setExisting] = useState('');
  const [ttl, setTtl] = useState(72);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    setCopied(false);
    try {
      const body: InviteIn = {
        role, gym: gym.trim() || null,
        existing_user_id: existing.trim() ? Number(existing.trim()) : null,
        ttl_hours: ttl, note: note.trim(),
      };
      const inv = await endpoints.createInvite(body);
      setCreated(inviteUrl(inv, me?.public_url));
      list.reload();
    } catch (ex) {
      setErr(t('err.generic', { msg: (ex as Error).message }));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created);
      setCopied(true);
    } catch {
      /* буфер недоступен: ссылку можно выделить вручную */
    }
  }

  const items: Invite[] = Array.isArray(list.data) ? list.data : list.data?.invites ?? [];
  return (
    <>
      <Link className="back" to="/profile" style={{ color: 'var(--mut)' }}>← {t('profile.title')}</Link>
      <h1>{t('admin.invites_title')}</h1>
      <form onSubmit={(e) => void submit(e)}>
        <label className="field">
          <span>{t('admin.role')}</span>
          <select value={role} onChange={(e) => setRole(e.target.value as InviteIn['role'])}>
            {(['athlete', 'pro', 'coach', 'admin'] as const).map((r) => <option key={r} value={r}>{t(`admin.role.${r}`)}</option>)}
          </select>
        </label>
        <label className="field"><span>{t('admin.gym')}</span><input value={gym} onChange={(e) => setGym(e.target.value)} /></label>
        <label className="field"><span>{t('admin.existing')}</span><input value={existing} onChange={(e) => setExisting(e.target.value.replace(/\D/g, ''))} inputMode="numeric" /></label>
        <label className="field"><span>{t('admin.ttl')}</span><input type="number" min={1} max={720} value={ttl} onChange={(e) => setTtl(Math.max(1, +e.target.value || 1))} /></label>
        <label className="field"><span>{t('admin.note')}</span><input value={note} onChange={(e) => setNote(e.target.value)} maxLength={120} /></label>
        <button type="submit" className="btn primary block" disabled={busy}>{t('admin.create')}</button>
      </form>
      {err && <div className="msg err" role="alert">{err}</div>}
      {created && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="mut" style={{ fontSize: 12, marginBottom: 4 }}>{t('admin.link')}</div>
          <div data-testid="invite-url" style={{ wordBreak: 'break-all', fontSize: 14, marginBottom: 8 }}>{created}</div>
          <button type="button" className="btn block" onClick={() => void copy()}>{copied ? t('admin.copied') : t('admin.copy')}</button>
        </div>
      )}
      <h2>{t('admin.list')}</h2>
      {items.length === 0 && !list.loading && <div className="mut">{t('admin.list_empty')}</div>}
      {items.map((i, n) => (
        <div key={i.token ?? n} className="wrow" style={{ cursor: 'default' }}>
          <div className="wmain">
            <div className="wt">{t(`admin.role.${i.role ?? 'athlete'}`)}{i.note ? ` · ${i.note}` : ''}</div>
            <div className="wsub">{i.gym ?? '—'} · {i.used_at ? t('admin.used') : t('admin.active')}{i.expires_at ? ` · ${i.expires_at.slice(0, 16).replace('T', ' ')}` : ''}</div>
          </div>
        </div>
      ))}
    </>
  );
}
