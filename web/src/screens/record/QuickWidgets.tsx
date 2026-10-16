// Компактный виджет на Сводке: самочувствие 1–10, вес тела, кнопка «Записать тренировку».
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { recordApi } from '../../api/record';
import { Card } from '../../components/ui';
import { useT } from '../../i18n';
import { errText } from './errors';
import { parseDecimal } from './logic';
import './record.css';

export function QuickWidgets() {
  const t = useT();
  const [feel, setFeel] = useState<number | null>(null);
  const [kg, setKg] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const sendFeel = async (n: number) => {
    setBusy(true);
    setMsg(null);
    try {
      await recordApi.feel(n);
      setFeel(n);
      setMsg({ ok: true, text: t('rec.feel_saved', { n }) });
    } catch (e) {
      setMsg({ ok: false, text: errText(e, t) });
    } finally {
      setBusy(false);
    }
  };
  const sendKg = async () => {
    const v = parseDecimal(kg);
    if (v == null || v < 20 || v > 500) { setMsg({ ok: false, text: t('rec.err.bodyweight') }); return; }
    setBusy(true);
    setMsg(null);
    try {
      const r = await recordApi.bodyweight(v);
      setKg('');
      setMsg({ ok: true, text: t('rec.bw_saved', { kg: r.kg }) });
    } catch (e) {
      setMsg({ ok: false, text: errText(e, t) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <div className="rec-inline" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <b>{t('rec.quick_title')}</b>
        <Link className="btn primary" to="/record">＋ {t('rec.title')}</Link>
      </div>
      <div className="mut" style={{ fontSize: 13, marginBottom: 4 }}>{t('rec.feel_q')}</div>
      <div className="rec-grid5" role="group" aria-label={t('rec.feel_q')}>
        {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
          <button key={n} type="button" disabled={busy} className={feel === n ? 'on' : ''} aria-pressed={feel === n} onClick={() => sendFeel(n)}>{n}</button>
        ))}
      </div>
      <div className="rec-inline">
        <input className="rec-in" inputMode="decimal" placeholder={t('rec.bw_ph')} aria-label={t('rec.bodyweight')} value={kg}
          onChange={(e) => setKg(e.target.value.replace(/[^\d.,]/g, ''))} />
        <button type="button" className="btn" disabled={busy || !kg} onClick={sendKg}>{t('rec.bw_save')}</button>
      </div>
      {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role={msg.ok ? 'status' : 'alert'}>{msg.text}</div>}
    </Card>
  );
}
