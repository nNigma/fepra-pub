import { useState } from 'react';
import { compsApi, type ParsedStage, type StagesParseResult } from '../../api/comps';
import { useT } from '../../i18n';
import { runJob, useCancelFlag } from '../../lib/runJob';
import { PhotoPicker, apiMessage } from '../ui5';
import { serializeConfirmStages } from './serialize';

/** Этап текстом или фото: фото -> превью (можно править) -> подтверждение. */
export function StageAdd({ eventId, divisionId, onDone }: { eventId: number; divisionId: number | null; onDone: () => void }) {
  const t = useT();
  const cancel = useCancelFlag();
  const [mode, setMode] = useState<'text' | 'photo'>('text');
  const [text, setText] = useState('');
  const [stages, setStages] = useState<ParsedStage[] | null>(null);
  const [parsed, setParsed] = useState<StagesParseResult | null>(null);
  const [photo, setPhoto] = useState<{ id: string; url: string } | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function saveText() {
    setBusy(true);
    setMsg(null);
    try {
      await compsApi.addStageText(eventId, text.trim(), divisionId);
      setText('');
      setMsg({ ok: true, text: t('comp5.stage_saved') });
      onDone();
    } catch (e) {
      setMsg({ ok: false, text: apiMessage(e, t) });
    } finally {
      setBusy(false);
    }
  }
  async function parse(uploadId: string) {
    setBusy(true);
    setMsg(null);
    try {
      const r = await runJob<StagesParseResult>(() => compsApi.parseStages(eventId, uploadId, divisionId, note.trim() || undefined), { signal: cancel });
      setParsed(r);
      if (!r.recognized || !r.stages?.length) setMsg({ ok: false, text: t(`meal.reason.${r.reason ?? 'not_recognized'}`) });
      else setStages(r.stages);
    } catch (e) {
      setMsg({ ok: false, text: apiMessage(e, t) });
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!stages) return;
    setBusy(true);
    try {
      const r = await compsApi.confirmStages(serializeConfirmStages(eventId, stages, parsed?.division_id ?? divisionId));
      setMsg({ ok: true, text: t('comp5.stages_saved', { saved: r.saved, skipped: r.skipped }) });
      setStages(null);
      onDone();
    } catch (e) {
      setMsg({ ok: false, text: apiMessage(e, t) });
    } finally {
      setBusy(false);
    }
  }

  if (stages) {
    return (
      <div>
        <div className="sub">{t('comp5.stages_preview')}</div>
        {stages.map((s, i) => (
          <div key={i} className="card" style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <input aria-label={t('comp5.stage_name')} value={s.name} style={{ flex: 1, minHeight: 44, borderRadius: 10, border: '1px solid var(--bd)', padding: '0 10px', background: 'var(--bg)' }}
                onChange={(e) => setStages(stages.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
              <button type="button" className="btn" aria-label={t('meal.remove_food')} onClick={() => setStages(stages.filter((_, j) => j !== i))}>✕</button>
            </div>
            <textarea aria-label={t('comp5.stage_desc')} rows={2} value={s.prescription} style={{ width: '100%', marginTop: 6, borderRadius: 10, border: '1px solid var(--bd)', padding: 8, background: 'var(--bg)' }}
              onChange={(e) => setStages(stages.map((x, j) => (j === i ? { ...x, prescription: e.target.value } : x)))} />
          </div>
        ))}
        <button type="button" className="btn primary block" disabled={busy || stages.length === 0} onClick={() => void confirm()}>{t('comp5.confirm')}</button>
        <button type="button" className="btn block" style={{ marginTop: 8 }} onClick={() => setStages(null)}>{t('common.cancel')}</button>
        {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role="status">{msg.text}</div>}
      </div>
    );
  }
  return (
    <div>
      <div className="langsw" style={{ marginBottom: 10 }}>
        {(['text', 'photo'] as const).map((m) => <button key={m} type="button" className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{t(`meal.mode.${m}`)}</button>)}
      </div>
      {mode === 'text' ? (
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) void saveText(); }}>
          <label className="field"><span>{t('comp5.stage_text')}</span>
            <textarea rows={3} value={text} placeholder={t('comp5.stage_text_ph')} onChange={(e) => setText(e.target.value)} /></label>
          <button type="submit" className="btn primary block" disabled={busy || !text.trim()}>{t('comp5.stage_add')}</button>
        </form>
      ) : (
        <>
          <PhotoPicker kind="other" label={t('comp5.photo_stages')} disabled={busy} onUploaded={(u, url) => setPhoto({ id: u.id, url })} />
          {photo && <img src={photo.url} alt="" style={{ width: '100%', maxHeight: 220, objectFit: 'cover', borderRadius: 12, margin: '12px 0' }} />}
          <label className="field"><span>{t('comp5.photo_note')}</span>
            <textarea rows={2} value={note} disabled={busy} onChange={(e) => setNote(e.target.value)} /></label>
          <button type="button" className="btn primary block" disabled={busy || !photo} onClick={() => photo && void parse(photo.id)}>{t('meal.send')}</button>
        </>
      )}
      {busy && mode === 'photo' && <div className="loading" role="status">{t('meal.parsing')}</div>}
      {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role="status">{msg.text}</div>}
    </div>
  );
}
