import { useEffect, useState } from 'react';
import { Card } from '../../components/ui';
import { disablePush, enablePush, currentPushState, PushError, type PushState } from '../../api/pushClient';
import { useT } from '../../i18n';

/** Переключатель push-уведомлений для Профиля. */
export function PushToggle() {
  const t = useT();
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    void currentPushState().then((s) => alive && setState(s));
    return () => { alive = false; };
  }, []);
  if (state == null) return null;
  async function toggle() {
    setBusy(true);
    setMsg(null);
    try {
      if (state === 'on') await disablePush();
      else await enablePush();
      setState(await currentPushState());
    } catch (e) {
      const reason = e instanceof PushError ? e.reason : 'failed';
      setMsg(t(`push.err.${reason}`));
      setState(await currentPushState());
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <div className="kv">
        <span>🔔 {t('push.title')}</span>
        {state === 'unsupported' ? (
          <span className="mut">{t('push.unsupported')}</span>
        ) : state === 'denied' ? (
          <span className="mut">{t('push.denied')}</span>
        ) : (
          <button type="button" role="switch" aria-checked={state === 'on'} className={`btn${state === 'on' ? ' primary' : ''}`} disabled={busy} onClick={() => void toggle()}>
            {state === 'on' ? t('push.on') : t('push.off')}
          </button>
        )}
      </div>
      <div className="mut" style={{ fontSize: 12.5 }}>{t('push.hint')}</div>
      {msg && <div className="msg err" role="alert">{msg}</div>}
    </Card>
  );
}
