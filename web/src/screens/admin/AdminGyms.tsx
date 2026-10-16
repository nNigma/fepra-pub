import { useState } from 'react';
import { adminApi } from '../../api/admin';
import { Async, Card, SecTitle } from '../../components/ui';
import { useT } from '../../i18n';
import { isAdmin } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { useFetch } from '../../lib/useFetch';
import { BackLink, Guard, apiMessage } from '../ui5';

function Body() {
  const t = useT();
  const gyms = useFetch(() => adminApi.gyms(), 'admin-gyms');
  const coaches = useFetch(() => adminApi.coaches(), 'admin-coaches');
  const [name, setName] = useState('');
  const [uid, setUid] = useState('');
  const [gym, setGym] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const reloadAll = () => { gyms.reload(); coaches.reload(); };
  const fail = (e: unknown) => setMsg({ ok: false, text: apiMessage(e, t) });
  return (
    <>
      <SecTitle>{t('adm.gyms')}</SecTitle>
      <Async state={gyms}>
        {(list) => (
          <>
            {list.map((g) => (
              <Card key={g.name}>
                <div style={{ fontWeight: 600 }}>{g.name}{g.is_default ? ` · ${t('adm.default')}` : ''}</div>
                <div className="mut" style={{ fontSize: 13 }}>{t('adm.members', { n: g.members })}{g.coaches.length ? ` · ${t('adm.coaches')}: ${g.coaches.map((c) => c.nick ?? c.id).join(', ')}` : ''}</div>
              </Card>
            ))}
            <form style={{ display: 'flex', gap: 8 }} onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim()) return;
              setMsg(null);
              adminApi.addGym(name.trim()).then(() => { setName(''); reloadAll(); }, fail);
            }}>
              <input aria-label={t('adm.gym_name')} placeholder={t('adm.gym_name')} value={name} maxLength={60} onChange={(e) => setName(e.target.value)}
                style={{ flex: 1, minHeight: 44, borderRadius: 10, border: '1px solid var(--bd)', padding: '0 12px', background: 'var(--card)' }} />
              <button type="submit" className="btn primary" disabled={!name.trim()}>{t('adm.add')}</button>
            </form>
          </>
        )}
      </Async>

      <SecTitle>{t('adm.coaches')}</SecTitle>
      <Async state={coaches}>
        {(list) => (
          <>
            {list.length === 0 && <div className="sub">{t('adm.no_coaches')}</div>}
            {list.map((c) => (
              <Card key={c.id}>
                <div style={{ fontWeight: 600 }}>{c.nick ?? `#${c.id}`}</div>
                {c.gyms.map((g) => (
                  <div key={g} className="kv" style={{ alignItems: 'center' }}>
                    <span style={{ color: 'var(--tx)' }}>{g}</span>
                    <button type="button" className="btn danger" aria-label={`${t('adm.revoke')}: ${g}`}
                      onClick={() => { if (window.confirm(t('adm.revoke_gym_confirm', { gym: g }))) adminApi.revokeCoach(c.id, g).then(reloadAll, fail); }}>{t('adm.revoke')}</button>
                  </div>
                ))}
                {c.gyms.length > 1 && (
                  <button type="button" className="btn danger block" style={{ marginTop: 6 }}
                    onClick={() => { if (window.confirm(t('adm.revoke_confirm'))) adminApi.revokeCoach(c.id).then(reloadAll, fail); }}>{t('adm.revoke_all')}</button>
                )}
              </Card>
            ))}
            <form style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }} onSubmit={(e) => {
              e.preventDefault();
              if (!/^\d+$/.test(uid.trim()) || !gym) return;
              setMsg(null);
              adminApi.assignCoach(Number(uid), gym).then(() => { setUid(''); reloadAll(); }, fail);
            }}>
              <input aria-label={t('adm.user_id')} placeholder={t('adm.user_id')} inputMode="numeric" value={uid} onChange={(e) => setUid(e.target.value)}
                style={{ flex: 1, minWidth: 120, minHeight: 44, borderRadius: 10, border: '1px solid var(--bd)', padding: '0 12px', background: 'var(--card)' }} />
              <select aria-label={t('adm.gym')} value={gym} onChange={(e) => setGym(e.target.value)}
                style={{ flex: 1, minWidth: 120, minHeight: 44, borderRadius: 10, border: '1px solid var(--bd)', background: 'var(--card)', padding: '0 8px' }}>
                <option value="">{t('adm.gym')}</option>
                {(gyms.data ?? []).map((g) => <option key={g.name} value={g.name}>{g.name}</option>)}
              </select>
              <button type="submit" className="btn primary" disabled={!uid.trim() || !gym}>{t('adm.assign')}</button>
            </form>
          </>
        )}
      </Async>
      {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role="alert">{msg.text}</div>}
    </>
  );
}

export function AdminGymsScreen() {
  const t = useT();
  const { me } = useSession();
  return (
    <>
      <BackLink to="/admin" />
      <h1>{t('adm.gyms')}</h1>
      <Guard ok={isAdmin(me)}><Body /></Guard>
    </>
  );
}
