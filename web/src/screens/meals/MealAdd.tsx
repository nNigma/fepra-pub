import { useReducer, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { mealsApi, type MealParseResult } from '../../api/meals';
import { useT } from '../../i18n';
import { runJob, useCancelFlag } from '../../lib/runJob';
import { BackLink, PhotoPicker, ProGate, apiMessage, todayIso } from '../ui5';
import { DraftEditor } from './DraftEditor';
import { buildParseRequest, buildSaveRequest, draftReducer, initialDraft, type DraftSource } from './draft';

const REASONS: Record<string, string> = { quota: 'meal.reason.quota', no_vision: 'meal.reason.no_vision', not_recognized: 'meal.reason.not_recognized' };

export function MealAddScreen() {
  const t = useT();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const day = sp.get('day') || todayIso();
  const cancel = useCancelFlag();
  const [s, dispatch] = useReducer(draftReducer, undefined, () => initialDraft());
  const [mode, setMode] = useState<'photo' | 'text'>('photo');
  const [text, setText] = useState('');
  const [photoNote, setPhotoNote] = useState('');
  const [photo, setPhoto] = useState<{ id: string; url?: string } | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const parsing = s.status === 'parsing';

  async function parse(source: DraftSource | null, correction?: string) {
    setErr(null);
    dispatch({ type: 'parsing' });
    try {
      const res = await runJob<MealParseResult>(() => mealsApi.parse(buildParseRequest(source ? { ...s, source } : s, correction)), { signal: cancel });
      dispatch({ type: 'parsed', result: res, correction });
    } catch (e) {
      dispatch({ type: 'failed' });
      setErr(apiMessage(e, t));
    }
  }

  async function save() {
    setSaving(true);
    setErr(null);
    try {
      await mealsApi.save(buildSaveRequest(s, day === todayIso() ? undefined : day));
      nav(`/meals${day === todayIso() ? '' : `?day=${day}`}`);
    } catch (e) {
      setErr(apiMessage(e, t)); // uuid не меняется: повтор безопасен
    } finally {
      setSaving(false);
    }
  }

  const sendPhoto = () => {
    if (!photo) return;
    const source: DraftSource = { kind: 'photo', upload_id: photo.id, url: photo.url, text: photoNote.trim() || null };
    dispatch({ type: 'start', source });
    void parse(source);
  };

  const startText = () => {
    const source: DraftSource = { kind: 'text', text: text.trim() };
    dispatch({ type: 'start', source });
    void parse(source);
  };

  return (
    <>
      <BackLink to="/meals" />
      <h1>{t('meal.add')}</h1>
      <ProGate>
        {!s.draft && (
          <>
            <div className="langsw" style={{ marginBottom: 12 }}>
              {(['photo', 'text'] as const).map((m) => (
                <button key={m} type="button" className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{t(`meal.mode.${m}`)}</button>
              ))}
            </div>
            {mode === 'photo' ? (
              <>
              <PhotoPicker
                kind="meal" label={t('meal.take_photo')} disabled={parsing}
                onUploaded={(u, url) => { setPhoto({ id: u.id, url: u.url }); setPreview(url); }}
              />
              {preview && <img src={preview} alt="" style={{ width: '100%', maxHeight: 220, objectFit: 'cover', borderRadius: 12, margin: '12px 0' }} />}
              <label className="field">
                <span>{t('meal.photo_note')}</span>
                <textarea rows={2} value={photoNote} placeholder={t('meal.photo_note_ph')} disabled={parsing} onChange={(e) => setPhotoNote(e.target.value)} />
              </label>
              <button type="button" className="btn primary block" disabled={parsing || !photo} onClick={sendPhoto}>{t('meal.send')}</button>
              </>
            ) : (
              <form onSubmit={(e) => { e.preventDefault(); if (text.trim().length >= 3) startText(); }}>
                <label className="field">
                  <span>{t('meal.text_label')}</span>
                  <textarea rows={3} value={text} placeholder={t('meal.text_ph')} onChange={(e) => setText(e.target.value)} />
                </label>
                <button type="submit" className="btn primary block" disabled={parsing || text.trim().length < 3}>{t('meal.parse')}</button>
              </form>
            )}
          </>
        )}
        {s.draft && preview && <img src={preview} alt="" style={{ width: '100%', maxHeight: 220, objectFit: 'cover', borderRadius: 12, margin: '12px 0' }} />}
        {parsing && <div className="loading" role="status">{t('meal.parsing')}</div>}
        {s.status === 'failed' && !s.draft && <div className="msg err" role="alert">{t(REASONS[s.reason ?? 'not_recognized'])}</div>}
        {s.draft && (
          <DraftEditor state={s} dispatch={dispatch} busy={parsing || saving} onCorrect={(c) => void parse(null, c)} onSave={() => void save()} saveLabel={t('meal.save')} />
        )}
        {s.draft && s.reason && <div className="msg err" role="alert">{t(REASONS[s.reason])}</div>}
        {err && <div className="msg err" role="alert">{err}</div>}
      </ProGate>
    </>
  );
}
