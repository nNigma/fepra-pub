import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { endpoints, registerPasskey } from '../api/endpoints';
import { passkeysSupported } from '../api/webauthn';
import { useI18n, useT } from '../i18n';
import { useSession } from '../lib/session';
import { PushToggle } from './programs/PushToggle';
import type { Lang } from '../api/types';
import { visibleTiles } from './more/tiles';

export function MoreScreen() {
  const t = useT();
  const { me } = useSession();
  return (
    <>
      <h1>{t('tab.more')}</h1>
      <div className="more-grid">
        {visibleTiles(me).map((x) => (
          <Link key={x.to} className="more-tile" to={x.to}><span className="mi" aria-hidden="true">{x.icon}</span><span>{t(x.key)}</span></Link>
        ))}
      </div>
    </>
  );
}

export function ProfileScreen() {
  const t = useT();
  const nav = useNavigate();
  const { lang, setLang } = useI18n();
  const { me, refresh, signedOut } = useSession();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  if (!me) return null;

  async function changeLang(l: Lang) {
    setLang(l);
    try {
      await endpoints.setLang(l);
    } catch {
      /* язык уже переключён локально */
    }
  }
  async function logout() {
    try {
      await endpoints.logout();
    } finally {
      signedOut();
      nav('/');
    }
  }
  async function addPasskey() {
    setBusy(true);
    setMsg(null);
    try {
      await registerPasskey();
      await refresh();
      setMsg({ ok: true, text: t('passkey.ok') });
    } catch (e) {
      setMsg({ ok: false, text: t('passkey.fail', { msg: (e as Error).message || (e as Error).name }) });
    } finally {
      setBusy(false);
    }
  }

  const roles = [me.roles.admin && t('profile.role.admin'), me.roles.pro && t('profile.role.pro'), me.roles.coach && t('profile.role.coach')].filter(Boolean);
  return (
    <>
      <h1>{t('profile.title')}</h1>
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="kv"><span>{t('profile.nick')}</span><b>{me.nick ?? `#${me.id}`}</b></div>
        <div className="kv"><span>{t('profile.roles')}</span><span>{roles.length ? roles.join(', ') : t('profile.role.athlete')}</span></div>
        {me.gym && <div className="kv"><span>{t('profile.gym')}</span><span>{me.gym}</span></div>}
        <div className="kv">
          <span>{t('profile.lang')}</span>
          <div className="langsw">
            {(['ru', 'en'] as Lang[]).map((l) => (
              <button key={l} type="button" className={lang === l ? 'on' : ''} onClick={() => void changeLang(l)}>{t(`lang.${l}`)}</button>
            ))}
          </div>
        </div>
      </div>

      <Link className="menu-link" to="/profile/settings"><span>✏️ {t('set.title')}</span><span className="mut">›</span></Link>
      <Link className="menu-link" to="/profile/garmin">
        <span>⌚ {t('profile.garmin')}</span>
        <span className="mut">{me.garmin?.connected ? t('profile.garmin_connected') : t('profile.garmin_off')} ›</span>
      </Link>
      {me.roles.admin && (
        <Link className="menu-link" to="/profile/invites"><span>✉️ {t('profile.admin_invites')}</span><span className="mut">›</span></Link>
      )}

      <PushToggle />

      {passkeysSupported() && (
        me.has_passkey ? (
          <div className="msg info">🔐 {t('passkey.have')}</div>
        ) : (
          <button type="button" className="btn block" style={{ marginBottom: 8 }} disabled={busy} onClick={() => void addPasskey()}>🔐 {t('passkey.add')}</button>
        )
      )}
      {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role="status">{msg.text}</div>}
      <button type="button" className="btn danger block" style={{ marginTop: 12 }} onClick={() => void logout()}>{t('profile.logout')}</button>
      <div className="foot">{t('profile.version')}: {__APP_VERSION__}</div>
    </>
  );
}
