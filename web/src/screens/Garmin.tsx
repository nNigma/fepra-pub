import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { endpoints } from '../api/endpoints';
import type { GarminLoginResult } from '../api/types';
import { Async } from '../components/ui';
import { useT } from '../i18n';
import { pollJob } from '../lib/jobs';
import { useSession } from '../lib/session';
import { useFetch } from '../lib/useFetch';

type Msg = { ok: boolean; text: string } | null;

export function GarminScreen() {
  const t = useT();
  const { refresh } = useSession();
  const state = useFetch(() => endpoints.garminStatus(), 'garmin-status');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [needMfa, setNeedMfa] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  const [histDays, setHistDays] = useState(90);
  const cancel = useRef({ cancelled: false });
  useEffect(() => {
    cancel.current.cancelled = false;
    const c = cancel.current;
    return () => { c.cancelled = true; };
  }, []);

  async function afterLogin(res: GarminLoginResult) {
    if (res.status === 'need_mfa') {
      setNeedMfa(true);
      return;
    }
    if (res.status === 'ok') {
      setNeedMfa(false);
      setMsg({ ok: true, text: t('garmin.connected_ok') });
      state.reload();
      await refresh();
      return;
    }
    setNeedMfa(false);
    setMsg({ ok: false, text: t('garmin.error', { msg: res.message || t('garmin.error_default') }) });
  }

  async function login(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const pw = password;
    setPassword(''); // пароль в state не задерживается ни на секунду после отправки
    try {
      await afterLogin(await endpoints.garminLogin(email.trim(), pw));
    } catch (ex) {
      setMsg({ ok: false, text: t('garmin.error', { msg: (ex as Error).message }) });
    } finally {
      setBusy(false);
    }
  }

  async function sendMfa(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const c = code.trim();
    setCode('');
    try {
      await afterLogin(await endpoints.garminMfa(c));
    } catch (ex) {
      setMsg({ ok: false, text: t('garmin.error', { msg: (ex as Error).message }) });
    } finally {
      setBusy(false);
    }
  }

  async function runJob(start: () => Promise<{ job_id: string }>) {
    setBusy(true);
    setMsg({ ok: true, text: t('garmin.syncing') });
    try {
      const { job_id } = await start();
      await pollJob(job_id, { signal: cancel.current });
      setMsg({ ok: true, text: t('garmin.sync_done') });
      state.reload();
    } catch (ex) {
      if ((ex as Error).message !== 'cancelled') setMsg({ ok: false, text: t('garmin.sync_error', { msg: (ex as Error).message }) });
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!window.confirm(t('garmin.disconnect_confirm'))) return;
    setBusy(true);
    try {
      await endpoints.garminDisconnect();
      setMsg(null);
      state.reload();
      await refresh();
    } catch (ex) {
      setMsg({ ok: false, text: t('err.generic', { msg: (ex as Error).message }) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Link className="back" to="/profile" style={{ color: 'var(--mut)' }}>← {t('profile.title')}</Link>
      <h1>{t('garmin.title')}</h1>
      <div className="msg info" style={{ marginTop: 6 }}>🔒 {t('garmin.privacy')}</div>
      <Async state={state}>
        {(st) =>
          st.connected ? (
            <>
              <div className="card" style={{ marginBottom: 12 }}>
                <div className="kv"><span>{t('garmin.status_on')}</span><span style={{ color: 'var(--green)' }}>● {st.status}</span></div>
                {st.email && <div className="kv"><span>{t('garmin.account')}</span><span>{st.email}</span></div>}
                <div className="kv"><span>{t('garmin.last_sync')}</span><span>{st.last_sync ? st.last_sync.replace('T', ' ').slice(0, 16) : t('garmin.never')}</span></div>
              </div>
              <button type="button" className="btn primary block" disabled={busy} onClick={() => void runJob(() => endpoints.garminSync())}>{t('garmin.sync')}</button>
              <div style={{ display: 'flex', gap: 8, margin: '8px 0' }}>
                <select aria-label={t('garmin.history')} value={histDays} onChange={(e) => setHistDays(+e.target.value)} style={{ minHeight: 44, borderRadius: 10, padding: '0 10px', background: 'var(--card)', border: '1px solid var(--bd)' }}>
                  {[30, 90, 180, 365].map((n) => <option key={n} value={n}>{t('garmin.history_days', { n })}</option>)}
                </select>
                <button type="button" className="btn" style={{ flex: 1 }} disabled={busy} onClick={() => void runJob(() => endpoints.garminHistory(histDays))}>{t('garmin.history')}</button>
              </div>
              <button type="button" className="btn danger block" disabled={busy} onClick={() => void disconnect()}>{t('garmin.disconnect')}</button>
            </>
          ) : needMfa ? (
            <form onSubmit={(e) => void sendMfa(e)} style={{ marginTop: 12 }}>
              <h2 style={{ marginTop: 0 }}>{t('garmin.mfa_title')}</h2>
              <p className="mut">{t('garmin.mfa_text')}</p>
              <label className="field">
                <span>{t('garmin.mfa_code')}</span>
                <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={12} autoFocus />
              </label>
              <button type="submit" className="btn primary block" disabled={busy || !code.trim()}>{t('garmin.mfa_send')}</button>
            </form>
          ) : (
            <form onSubmit={(e) => void login(e)} style={{ marginTop: 12 }} autoComplete="off">
              <label className="field">
                <span>{t('garmin.email')}</span>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" autoCapitalize="none" spellCheck={false} required />
              </label>
              <label className="field">
                <span>{t('garmin.password')}</span>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" autoCapitalize="none" spellCheck={false} required />
              </label>
              <button type="submit" className="btn primary block" disabled={busy || !email || !password}>{busy ? t('garmin.busy') : t('garmin.login')}</button>
            </form>
          )
        }
      </Async>
      {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role="status">{msg.text}</div>}
    </>
  );
}
