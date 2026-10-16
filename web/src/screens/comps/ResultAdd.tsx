import { useState } from 'react';
import { compsApi, type CompStage, type ParsedRow, type ResultsParseResult } from '../../api/comps';
import { useT } from '../../i18n';
import { runJob, useCancelFlag } from '../../lib/runJob';
import { PhotoPicker, apiMessage } from '../ui5';
import { parseResultInput, serializeConfirmResults, serializeResultText } from './serialize';

const inp = { minHeight: 44, borderRadius: 10, border: '1px solid var(--bd)', padding: '0 10px', background: 'var(--bg)', width: '100%' } as const;

/** Результат текстом «значение, место[, размер поля]» или фото таблицы (сопоставление этапов + подтверждение). */
export function ResultAdd({
  eventId, divisionId, stages, onDone,
}: { eventId: number; divisionId: number | null; stages: CompStage[]; onDone: () => void }) {
  const t = useT();
  const cancel = useCancelFlag();
  const [mode, setMode] = useState<'text' | 'photo'>('text');
  const [text, setText] = useState('');
  const [stageIdx, setStageIdx] = useState<string>('');
  const [athlete, setAthlete] = useState('');
  const [rows, setRows] = useState<ParsedRow[] | null>(null);
  const [parsed, setParsed] = useState<ResultsParseResult | null>(null);
  const [photo, setPhoto] = useState<{ id: string; url: string } | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const textOk = parseResultInput(text) != null;

  async function saveText() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await compsApi.addResultText(eventId, serializeResultText({
        text, athlete, stageIdx: stageIdx === '' ? null : Number(stageIdx), divisionId,
      }));
      setText('');
      setMsg({ ok: true, text: t('comp5.result_saved', { idx: r.stage_idx, value: r.value, place: r.place ?? '—' }) });
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
      const r = await runJob<ResultsParseResult>(() => compsApi.parseResults(eventId, { upload_id: uploadId, athlete: athlete.trim() || undefined, division_id: divisionId, note: note.trim() || undefined }), { signal: cancel });
      setParsed(r);
      if (!r.recognized || !r.rows?.length) setMsg({ ok: false, text: t(`meal.reason.${r.reason ?? 'not_recognized'}`) });
      else setRows(r.rows);
    } catch (e) {
      setMsg({ ok: false, text: apiMessage(e, t) });
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!rows) return;
    setBusy(true);
    try {
      const r = await compsApi.confirmResults(serializeConfirmResults(eventId, rows, { athlete: parsed?.athlete ?? athlete, divisionId: parsed?.division_id ?? divisionId }));
      setMsg({ ok: true, text: t('comp5.results_saved', { saved: r.saved, skipped: r.skipped }) });
      setRows(null);
      onDone();
    } catch (e) {
      setMsg({ ok: false, text: apiMessage(e, t) });
    } finally {
      setBusy(false);
    }
  }
  const patchRow = (i: number, p: Partial<ParsedRow>) => setRows((rs) => (rs ?? []).map((r, j) => (j === i ? { ...r, ...p } : r)));

  if (rows) {
    return (
      <div>
        <div className="sub">{t('comp5.results_preview')}</div>
        {rows.map((r, i) => (
          <div key={i} className="card" style={{ marginBottom: 8 }}>
            <label className="field"><span>{t('comp5.stage')}</span>
              <select value={r.stage_id ?? ''} onChange={(e) => {
                const st = stages.find((s) => s.id === Number(e.target.value));
                patchRow(i, { stage_id: st ? st.id : null, stage_idx: st?.idx ?? null, stage_name: st?.name ?? null });
              }}>
                <option value="">{t('comp5.skip_row')}</option>
                {stages.map((s) => <option key={s.id} value={s.id}>{s.idx}. {s.name}</option>)}
              </select>
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input aria-label={t('comp5.value')} style={inp} value={r.value ?? ''} onChange={(e) => patchRow(i, { value: e.target.value })} />
              <input aria-label={t('comp5.place')} style={inp} inputMode="numeric" value={r.place ?? ''} onChange={(e) => patchRow(i, { place: e.target.value === '' ? null : Number(e.target.value) })} />
              <button type="button" className="btn" aria-label={t('meal.remove_food')} onClick={() => setRows(rows.filter((_, j) => j !== i))}>✕</button>
            </div>
          </div>
        ))}
        <button type="button" className="btn primary block" disabled={busy} onClick={() => void confirm()}>{t('comp5.confirm')}</button>
        <button type="button" className="btn block" style={{ marginTop: 8 }} onClick={() => setRows(null)}>{t('common.cancel')}</button>
        {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role="status">{msg.text}</div>}
      </div>
    );
  }
  return (
    <div>
      <div className="langsw" style={{ marginBottom: 10 }}>
        {(['text', 'photo'] as const).map((m) => <button key={m} type="button" className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{t(`meal.mode.${m}`)}</button>)}
      </div>
      <label className="field"><span>{t('comp5.athlete')}</span>
        <input value={athlete} placeholder={t('comp5.athlete_me')} onChange={(e) => setAthlete(e.target.value)} /></label>
      {mode === 'text' ? (
        <form onSubmit={(e) => { e.preventDefault(); if (textOk) void saveText(); }}>
          <label className="field"><span>{t('comp5.stage')}</span>
            <select value={stageIdx} onChange={(e) => setStageIdx(e.target.value)}>
              <option value="">{t('comp5.stage_auto')}</option>
              {stages.map((s) => <option key={s.id} value={s.idx}>{s.idx}. {s.name}</option>)}
            </select></label>
          <label className="field"><span>{t('comp5.result_text')}</span>
            <input value={text} placeholder="5:30, 12, 40" onChange={(e) => setText(e.target.value)} />
            <small className="mut" style={{ display: 'block', marginTop: 3 }}>{t('comp5.result_hint')}</small></label>
          <button type="submit" className="btn primary block" disabled={busy || !textOk}>{t('comp5.result_add')}</button>
        </form>
      ) : (
        <>
          <PhotoPicker kind="other" label={t('comp5.photo_results')} disabled={busy} onUploaded={(u, url) => setPhoto({ id: u.id, url })} />
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
