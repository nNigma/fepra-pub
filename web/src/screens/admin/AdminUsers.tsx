import { useEffect, useState } from 'react';
import { endpoints } from '../../api/endpoints';
import { inviteUrl } from '../../lib/jobs';
import { adminApi, type AdminGym, type AdminUser, type RolesPatch } from '../../api/admin';
import { Card, ErrorBox, Loading } from '../../components/ui';
import { ApiError } from '../../api/client';
import { useT } from '../../i18n';
import { isAdmin } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { BackLink, Guard, apiMessage } from '../ui5';
import { applyRoles, isBlocking, removeWarning, roleWarning, type RoleWarning } from './logic';

function UserCard({ u, all, gyms, selfId, onChange, onRemoved }: {
  u: AdminUser; all: AdminUser[]; gyms: AdminGym[]; selfId?: number;
  onChange: (u: AdminUser) => void; onRemoved: (id: number) => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const warn = (w: RoleWarning) => (w ? t(`adm.warn.${w}`) : null);

  async function put(patch: RolesPatch) {
    const w = roleWarning(all, u, patch, selfId);
    if (isBlocking(w)) { setErr(warn(w)); return; } // сервер ответил бы 409, не шлём
    if (w && !window.confirm(warn(w) ?? '')) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await adminApi.setRoles(u.id, patch);
      onChange({ ...u, roles: r.roles });
    } catch (e) {
      setErr(apiMessage(e, t));
    } finally {
      setBusy(false);
    }
  }
  async function makeLink() {
    setBusy(true);
    setErr(null);
    setCopied(false);
    try {
      const inv = await endpoints.createInvite({ role: 'athlete', gym: null, existing_user_id: u.id, ttl_hours: 72, note: `вход ${u.nick ?? u.id}` });
      const url = inviteUrl(inv, undefined);
      setLink(url);
      try { await navigator.clipboard.writeText(url); setCopied(true); } catch { /* буфер недоступен: ссылку видно на экране */ }
    } catch (e) {
      setErr(apiMessage(e, t));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    const w = removeWarning(all, u);
    if (isBlocking(w)) { setErr(warn(w)); return; }
    if (!window.confirm(t('adm.remove_confirm', { nick: u.nick ?? u.id }))) return;
    setBusy(true);
    try {
      await adminApi.removeUser(u.id);
      onRemoved(u.id);
    } catch (e) {
      setErr(apiMessage(e, t));
      setBusy(false);
    }
  }
  const sw = (k: 'allowlist' | 'pro' | 'admin') => (
    <label className="kv" style={{ alignItems: 'center', minHeight: 44 }}>
      <span style={{ color: 'var(--tx)' }}>{t(`adm.role.${k}`)}</span>
      <input type="checkbox" style={{ width: 24, height: 24 }} checked={u.roles[k]} disabled={busy} onChange={(e) => void put({ [k]: e.target.checked })} />
    </label>
  );
  return (
    <Card>
      <div style={{ fontWeight: 600 }}>{u.nick ?? '—'} <span className="mut" style={{ fontWeight: 400, fontSize: 12 }}>#{u.id}{u.gym ? ` · ${u.gym}` : ''}</span></div>
      {sw('allowlist')}
      {sw('pro')}
      {sw('admin')}
      <div style={{ marginTop: 6 }}>
        <div style={{ color: 'var(--tx)', minHeight: 32, display: 'flex', alignItems: 'center' }}>{t('adm.role.coach')}: {t('adm.coach_gyms_hint')}</div>
        {gyms.map((g) => {
          const has = (u.roles.coach_gyms ?? []).includes(g.name);
          return (
            <label key={g.name} className="kv" style={{ alignItems: 'center', minHeight: 44 }}>
              <span style={{ color: 'var(--tx)' }}>{g.name}</span>
              <input type="checkbox" style={{ width: 24, height: 24 }} checked={has} disabled={busy}
                aria-label={`${t('adm.role.coach')}: ${g.name}`}
                onChange={(e) => {
                  const cur = u.roles.coach_gyms ?? [];
                  const next = e.target.checked ? [...cur, g.name] : cur.filter((x) => x !== g.name);
                  void put({ coach: next.length ? next : null });
                }} />
            </label>
          );
        })}
      </div>
      {err && <div className="msg err" role="alert">{err}</div>}
      <button type="button" className="btn block" style={{ marginTop: 8 }} disabled={busy} onClick={() => void makeLink()}>🔗 {t('adm.login_link')}</button>
      <div className="mut" style={{ fontSize: 12.5, marginTop: 4 }}>{t('adm.login_link_hint')}</div>
      {link && (
        <div style={{ marginTop: 6 }}>
          <div data-testid="login-link" style={{ wordBreak: 'break-all', fontSize: 13 }}>{link}</div>
          {copied && <div className="mut" style={{ fontSize: 12.5 }}>{t('adm.copied')}</div>}
        </div>
      )}
      <button type="button" className="btn danger block" style={{ marginTop: 8 }} disabled={busy} onClick={() => void remove()}>{t('adm.remove')}</button>
    </Card>
  );
}

function Body() {
  const t = useT();
  const { me } = useSession();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [gyms, setGyms] = useState<AdminGym[]>([]);
  const [q, setQ] = useState('');
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    let alive = true;
    const h = setTimeout(() => {
      adminApi.users(q.trim() || undefined).then((u) => alive && setUsers(u), (e) => alive && setError(e instanceof ApiError ? e : new ApiError(-1, String(e))));
    }, q ? 250 : 0);
    return () => { alive = false; clearTimeout(h); };
  }, [q]);
  useEffect(() => { adminApi.gyms().then(setGyms, () => {}); }, []);
  if (error) return <ErrorBox error={error} />;
  return (
    <>
      <input aria-label={t('adm.search')} placeholder={t('adm.search')} value={q} onChange={(e) => setQ(e.target.value)}
        style={{ width: '100%', minHeight: 44, borderRadius: 10, border: '1px solid var(--bd)', padding: '0 12px', background: 'var(--card)', marginBottom: 10 }} />
      {!users ? <Loading /> : users.length === 0 ? <div className="sub">{t('adm.no_users')}</div> : users.map((u) => (
        <UserCard key={u.id} u={u} all={users} gyms={gyms} selfId={me?.id}
          onChange={(nu) => setUsers((us) => applyRoles(us ?? [], nu.id, nu.roles))}
          onRemoved={(id) => setUsers((us) => (us ?? []).filter((x) => x.id !== id))} />
      ))}
    </>
  );
}

export function AdminUsersScreen() {
  const t = useT();
  const { me } = useSession();
  return (
    <>
      <BackLink to="/admin" />
      <h1>{t('adm.users')}</h1>
      <Guard ok={isAdmin(me)}><Body /></Guard>
    </>
  );
}
