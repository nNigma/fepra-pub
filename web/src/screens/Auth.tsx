import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError } from '../api/client';
import { endpoints, loginWithPasskey, registerPasskey } from '../api/endpoints';
import { passkeysSupported } from '../api/webauthn';
import { A2hsBanner } from '../components/Shell';
import { useT } from '../i18n';
import { useSession } from '../lib/session';

export function LoginScreen() {
  const t = useT();
  const { refresh } = useSession();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const supported = passkeysSupported();

  async function go() {
    setBusy(true);
    setErr(null);
    try {
      await loginWithPasskey();
      await refresh();
    } catch (e) {
      const name = (e as Error).name;
      setErr(name === 'NotAllowedError' || (e as Error).message === 'cancelled' ? t('login.cancelled') : t('login.failed'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="wrap">
      <div className="center">
        <div style={{ fontSize: 48 }}>🏋️</div>
        <h1>{t('login.title')}</h1>
        <A2hsBanner />
        {supported ? (
          <button type="button" className="btn primary block" style={{ maxWidth: 340 }} disabled={busy} onClick={() => void go()}>
            {busy ? t('login.busy') : `🔐 ${t('login.passkey')}`}
          </button>
        ) : (
          <div className="msg info">{t('login.no_support')}</div>
        )}
        {err && <div className="msg err" role="alert">{err}</div>}
        <div className="mut" style={{ fontSize: 13, maxWidth: 320 }}>{t('login.no_access')}</div>
      </div>
    </div>
  );
}

type Step = 'nick' | 'passkey' | 'done';

export function InviteScreen() {
  const t = useT();
  const nav = useNavigate();
  const { token = '' } = useParams();
  const { refresh } = useSession();
  const [nick, setNick] = useState('');
  const [step, setStep] = useState<Step>('nick');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [info, setInfo] = useState<{ valid: boolean; existing: boolean; nick: string | null } | null>(null);
  useEffect(() => { endpoints.inviteInfo(token).then(setInfo, () => setInfo(null)); }, [token]);
  const existing = !!info?.existing;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const n = existing ? (info?.nick ?? '') : nick.trim();
    if (!n && !existing) return setErr(t('invite.nick_required'));
    setBusy(true);
    setErr(null);
    try {
      await endpoints.redeem(token, n);
      await refresh();
      if (passkeysSupported()) setStep('passkey');
      else nav('/', { replace: true });
    } catch (ex) {
      const s = ex instanceof ApiError ? ex.status : 0;
      setErr(s >= 400 && s < 500 ? t('invite.bad_token') : t('err.generic', { msg: (ex as Error).message }));
    } finally {
      setBusy(false);
    }
  }

  async function addPasskey() {
    setBusy(true);
    setErr(null);
    try {
      await registerPasskey();
      await refresh();
      setOkMsg(t('passkey.ok'));
      setStep('done');
      setTimeout(() => nav('/', { replace: true }), 900);
    } catch (ex) {
      setErr(t('passkey.fail', { msg: (ex as Error).message || (ex as Error).name }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="wrap">
      <div className="center">
        <div style={{ fontSize: 48 }}>🏋️</div>
        {step === 'nick' && (
          <form onSubmit={(e) => void submit(e)} style={{ width: '100%', maxWidth: 340, textAlign: 'left' }}>
            <h1 style={{ textAlign: 'center' }}>{t('invite.title')}</h1>
            <p className="mut" style={{ textAlign: 'center' }}>{t('invite.lead')}</p>
            {existing ? (
              <div className="msg info" role="note" data-testid="invite-existing">{t('invite.existing', { nick: info?.nick ?? '' })}</div>
            ) : (
              <label className="field">
                <span>{t('invite.nick')}</span>
                <input value={nick} onChange={(e) => setNick(e.target.value)} placeholder={t('invite.nick_ph')}
                  autoComplete="nickname" maxLength={32} autoFocus />
              </label>
            )}
            <button type="submit" className="btn primary block" disabled={busy}>{existing ? t('invite.submit_existing') : t('invite.submit')}</button>
          </form>
        )}
        {step === 'passkey' && (
          <div style={{ maxWidth: 340 }}>
            <h1>{t('passkey.title')}</h1>
            <p className="mut">{t('passkey.text')}</p>
            <button type="button" className="btn primary block" disabled={busy} onClick={() => void addPasskey()}>
              🔐 {t('passkey.add')}
            </button>
            <div style={{ height: 8 }} />
            <button type="button" className="btn block" onClick={() => nav('/', { replace: true })}>{t('passkey.skip')}</button>
          </div>
        )}
        {step === 'done' && <div className="msg ok">{okMsg ?? t('invite.done')}</div>}
        {err && <div className="msg err" role="alert">{err}</div>}
      </div>
    </div>
  );
}
