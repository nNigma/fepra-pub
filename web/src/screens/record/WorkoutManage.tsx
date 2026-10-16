// Правка и удаление записанной тренировки: /w/:id. Доска правится только у своей (board_source=own).
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { recordApi, type Ambiguous, type Credited, type Scaling, type WorkoutFull } from '../../api/record';
import { Async } from '../../components/ui';
import { useT } from '../../i18n';
import { useFetch } from '../../lib/useFetch';
import { FollowUps } from './FollowUps';
import { errText } from './errors';
import { FormBlocks, HowTo, RpeScale, ScalingPick, useConfirm } from './fields';
import { buildFormResult, isBoardSport, parseDecimal, valuesFromServer } from './logic';
import { trashAdd, trashRemove } from './trash';
import './record.css';

interface Saved {
  credited: Credited[];
  ambiguous: Ambiguous[];
  lines: string[];
}

/** Что отправить в PATCH: только изменённое. Экспорт для тестов. */
export function buildPatch(w: WorkoutFull, s: {
  values: Record<string, string>; rpe: number | null; scaling: Scaling; bodyweight: string; boardText: string; resultText: string;
}): { changes: Record<string, unknown>; errors: Record<string, string> } {
  const changes: Record<string, unknown> = {};
  let errors: Record<string, string> = {};
  const boardChanged = !!w.board_editable && s.boardText.trim() !== (w.board_text ?? '').trim() && !!s.boardText.trim();
  if (boardChanged) changes.board = { text: s.boardText.trim() };
  if (s.rpe !== (w.rpe ?? null)) changes.rpe = s.rpe;
  if (s.scaling !== ((w.scaling as Scaling) ?? null) && isBoardSport(w.sport)) changes.scaling = s.scaling;
  const bw = parseDecimal(s.bodyweight);
  if (bw != null && bw !== (w.bodyweight ?? null)) changes.bodyweight = bw;
  if (w.form && !boardChanged) {
    const init = valuesFromServer(w.form, w.form_values);
    const same = Object.keys({ ...init, ...s.values }).every((k) => (init[k] ?? '') === (s.values[k] ?? ''));
    if (!same) {
      const b = buildFormResult(w.form, s.values);
      errors = b.errors;
      changes.form_result = b.result;
    }
  } else if (!w.form && s.resultText.trim() !== (w.result_text ?? '').trim()) {
    changes.form_result = s.resultText.trim();
  }
  return { changes, errors };
}

function Editor({ w, onSaved, onDeleted }: { w: WorkoutFull; onSaved: (s: Saved) => void; onDeleted: () => void }) {
  const t = useT();
  const [values, setValues] = useState(() => valuesFromServer(w.form, w.form_values));
  const [rpe, setRpe] = useState<number | null>(w.rpe ?? null);
  const [scaling, setScaling] = useState<Scaling>((w.scaling as Scaling) ?? null);
  const [bodyweight, setBodyweight] = useState(w.bodyweight != null ? String(w.bodyweight) : '');
  const [boardText, setBoardText] = useState(w.board_text ?? '');
  const [resultText, setResultText] = useState(w.result_text ?? '');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err' | 'info'; text: string } | null>(null);
  const del = useConfirm();
  const board = isBoardSport(w.sport);

  const save = async () => {
    const { changes, errors } = buildPatch(w, { values, rpe, scaling, bodyweight, boardText, resultText });
    setFieldErrors(errors);
    if (Object.keys(errors).length) { setMsg({ kind: 'err', text: t('rec.err.fix_fields') }); return; }
    if (!Object.keys(changes).length) { setMsg({ kind: 'info', text: t('rec.nothing_changed') }); return; }
    setBusy(true);
    setMsg(null);
    try {
      const r = await recordApi.patch(w.id, changes);
      onSaved({ credited: r.credited ?? [], ambiguous: r.ambiguous ?? [], lines: r.metcon_lines ?? [] });
    } catch (e) {
      setMsg({ kind: 'err', text: errText(e, t) });
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await recordApi.remove(w.id);
      trashAdd({ id: w.id, day: w.day, sport: w.sport });
      onDeleted();
    } catch (e) {
      setMsg({ kind: 'err', text: errText(e, t) });
      del.cancel();
    } finally {
      setBusy(false);
    }
  };

  if (w.editable === false)
    return (
      <div className="msg info">
        {t('rec.readonly_watch')}
        <div style={{ marginTop: 8 }}>{w.score && <span className="reschip">{w.score}</span>}</div>
      </div>
    );

  return (
    <>
      {w.form && (
        <>
          <div className="sec">{t('rec.result_title')}</div>
          <HowTo />
          <FormBlocks form={w.form} values={values} errors={fieldErrors as never} onChange={(k, v) => setValues((x) => ({ ...x, [k]: v }))} />
        </>
      )}
      {!w.form && (
        <label className="field">
          <span>{t('rec.free_text')}</span>
          <textarea className="rec-board" value={resultText} onChange={(e) => setResultText(e.target.value)} />
        </label>
      )}
      <div className="sec">{t('rec.overall')}</div>
      <RpeScale value={rpe} onChange={setRpe} />
      {board && <ScalingPick value={scaling} onChange={setScaling} />}
      <label className="field">
        <span>{t('rec.bodyweight')}</span>
        <input inputMode="decimal" value={bodyweight} onChange={(e) => setBodyweight(e.target.value.replace(/[^\d.,]/g, ''))} />
      </label>
      {board && w.board_text != null && (
        <>
          <div className="sec">{t('rec.board_text')}</div>
          <textarea className="rec-board" value={boardText} disabled={!w.board_editable} aria-label={t('rec.board_text')} onChange={(e) => setBoardText(e.target.value)} />
          {!w.board_editable && <div className="mut" style={{ fontSize: 12.5, marginTop: 4 }}>{t('rec.board_locked')}</div>}
          {w.board_editable && boardText.trim() !== (w.board_text ?? '').trim() && <div className="mut" style={{ fontSize: 12.5, marginTop: 4 }}>{t('rec.board_edit_warn')}</div>}
        </>
      )}
      {msg && <div className={`msg ${msg.kind}`} role={msg.kind === 'err' ? 'alert' : 'status'}>{msg.text}</div>}
      <div className="rec-actions">
        <button type="button" className="btn primary" disabled={busy} onClick={save}>{t('rec.save_changes')}</button>
      </div>
      <div className="sec">{t('rec.danger')}</div>
      {!del.asked ? (
        <button type="button" className="btn danger" onClick={del.ask}>{t('rec.delete')}</button>
      ) : (
        <div className="msg err" role="alertdialog" aria-label={t('rec.delete_q')}>
          {t('rec.delete_q')}
          <div className="rec-actions">
            <button type="button" className="btn danger" disabled={busy} onClick={remove}>{t('rec.delete_yes')}</button>
            <button type="button" className="btn" onClick={del.cancel}>{t('rec.cancel')}</button>
          </div>
        </div>
      )}
    </>
  );
}

export function WorkoutManageScreen() {
  const t = useT();
  const nav = useNavigate();
  const { id = '' } = useParams();
  const state = useFetch(() => recordApi.get(id), `wm:${id}`);
  const [saved, setSaved] = useState<Saved | null>(null);
  const [deleted, setDeleted] = useState(false);
  const [restoreErr, setRestoreErr] = useState<string | null>(null);

  const restore = async () => {
    try {
      await recordApi.restore(id);
      trashRemove(id);
      setDeleted(false);
      state.reload();
    } catch (e) {
      setRestoreErr(errText(e, t));
    }
  };

  return (
    <>
      <button type="button" className="back linkbtn" style={{ textDecoration: 'none', color: 'var(--mut)' }} onClick={() => nav('/workouts')}>{t('workout.back')}</button>
      {deleted ? (
        <>
          <h1>{t('rec.deleted')}</h1>
          <div className="msg info" role="status">{t('rec.deleted_hint')}</div>
          {restoreErr && <div className="msg err" role="alert">{restoreErr}</div>}
          <div className="rec-actions">
            <button type="button" className="btn primary" onClick={restore}>{t('rec.undo')}</button>
            <Link className="btn" to="/workouts">{t('rec.to_list')}</Link>
          </div>
        </>
      ) : (
        <Async state={state}>
          {(w) => (
            <>
              <h1>{t(`rec.sport.${w.sport}`)} · {w.day}</h1>
              <div className="mut" style={{ marginBottom: 10 }}>
                {[w.start_time, w.score, w.scaling, w.rpe ? `RPE ${w.rpe}` : null].filter(Boolean).join(' · ')}
              </div>
              <Editor key={w.updated_at ?? 'x'} w={w} onSaved={(s) => { setSaved(s); state.reload(); }} onDeleted={() => setDeleted(true)} />
              {saved && (
                <>
                  <div className="msg ok" role="status">{t('rec.saved')}</div>
                  {saved.lines.map((l, i) => <div key={i} className="hist">{l}</div>)}
                  <FollowUps id={w.id} credited={saved.credited} ambiguous={saved.ambiguous} />
                </>
              )}
              <div className="rec-actions"><Link className="btn" to={`/workouts/${w.day}`}>{t('rec.open_day')}</Link></div>
            </>
          )}
        </Async>
      )}
    </>
  );
}
