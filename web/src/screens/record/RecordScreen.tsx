import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { SPORTS, recordApi, type Engine, type ParseResult, type Sport } from '../../api/record';
import { useT } from '../../i18n';
import { pollJob } from '../../lib/jobs';
import { canManageClub } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { FollowUps } from './FollowUps';
import { GymPicker, useClubGym } from '../club/clubGym';
import { previewLines, shortDay, useGymProgram } from './GymTodayCard';
import {
  clearDraft, draftHasContent, loadDraft, newDraft, newUuid, nowHHMM, saveDraft, todayIso, yesterdayIso,
  type Draft, type Source, type Step,
} from './draft';
import { classifyError, errText } from './errors';
import { FormBlocks, HowTo, RpeScale, ScalingPick } from './fields';
import { buildPutBody, isBoardSport, parseDecimal } from './logic';
import './record.css';

export const MAX_UPLOAD = 10 * 1024 * 1024;

const STEPS_BOARD: Step[] = ['setup', 'board', 'check', 'result', 'done'];
const STEPS_PLAIN: Step[] = ['setup', 'result', 'done'];

function Progress({ step, sport }: { step: Step; sport: Sport }) {
  const list = isBoardSport(sport) ? STEPS_BOARD : STEPS_PLAIN;
  const at = list.indexOf(step);
  return <div className="rec-steps" aria-hidden="true">{list.map((s, i) => <i key={s} className={i <= at ? 'on' : ''} />)}</div>;
}

function EnginePick({ value, onChange }: { value: Engine; onChange: (e: Engine) => void }) {
  const t = useT();
  return (
    <div className="rec-inline" role="group" aria-label={t('rec.engine')}>
      <span className="mut" style={{ fontSize: 13 }}>{t('rec.engine')}</span>
      {(['fast', 'slow'] as Engine[]).map((e) => (
        <button key={e} type="button" className={`rec-chip${value === e ? ' on' : ''}`} aria-pressed={value === e} onClick={() => onChange(e)}>{t(`rec.engine.${e}`)}</button>
      ))}
    </div>
  );
}

export function RecordScreen() {
  const t = useT();
  const nav = useNavigate();
  const { me } = useSession();
  const manageClub = canManageClub(me);
  const [sp] = useSearchParams();
  // ссылка из уведомления «Программа зала готова» и с карточки на Сводке: сразу форма по программе зала
  const deepGym = useMemo(() => !!sp.get('gym'), []); // eslint-disable-line react-hooks/exhaustive-deps
  const initial = useMemo(() => {
    if (deepGym) {
      const d = newDraft();
      const q = sp.get('day');
      if (q && /^\d{4}-\d{2}-\d{2}$/.test(q) && q <= todayIso()) d.day = q;
      return { draft: { ...d, step: 'board' as Step, source: 'gym' as Source }, restored: false };
    }
    const d = loadDraft();
    return d && draftHasContent(d) ? { draft: d, restored: true } : { draft: newDraft(), restored: false };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [draft, setDraft] = useState<Draft>(initial.draft);
  const [restored, setRestored] = useState(initial.restored);
  const [busy, setBusy] = useState<null | 'upload' | 'parse' | 'gym' | 'save'>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<null | 'quota' | 'no_vision' | 'not_recognized' | 'no_gym'>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const cancel = useRef({ cancelled: false });

  useEffect(() => {
    cancel.current = { cancelled: false };
    const c = cancel.current;
    return () => { c.cancelled = true; };
  }, []);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  useEffect(() => { saveDraft(draft); }, [draft]);

  const patch = useCallback((p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p })), []);
  const go = (step: Step) => { setError(null); setNotice(null); patch({ step }); };
  const board = isBoardSport(draft.sport);

  // смена дня/вида после разбора доски делает разбор неактуальным
  const patchSetup = (p: Partial<Pick<Draft, 'day' | 'sport'>>) =>
    setDraft((d) => (d.parse || d.source ? { ...d, ...p, parse: null, source: null, values: {}, boardText: '', gymDay: null, gymName: null } : { ...d, ...p }));

  // ---------- разбор доски ----------
  const runParse = async (o: { uploadId?: string; text?: string; verbatim?: boolean; engine?: Engine }) => {
    setBusy('parse');
    setError(null);
    setNotice(null);
    try {
      const { job_id } = await recordApi.parse({
        sport: draft.sport, engine: o.engine ?? draft.engine, verbatim: o.verbatim,
        ...(o.uploadId ? { upload_id: o.uploadId } : { text: o.text }),
      });
      const job = await pollJob(job_id, { intervalMs: 1500, signal: cancel.current });
      const res = job.result as ParseResult;
      if (!res.recognized) {
        setNotice(res.reason === 'quota' || res.reason === 'no_vision' ? res.reason : 'not_recognized');
        return;
      }
      setDraft((d) => ({ ...d, parse: res, boardText: res.board_text ?? '', values: {}, step: 'check' }));
    } catch (e) {
      if ((e as Error).message === 'cancelled') return;
      if (classifyError(e) === 'quota') setNotice('quota');
      else setError(errText(e, t));
    } finally {
      setBusy(null);
    }
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setNotice(null);
    if (file.size > MAX_UPLOAD) { setError(t('rec.err.file_big')); return; }
    if (file.type && !file.type.startsWith('image/')) { setError(t('rec.err.file_type')); return; }
    setBusy('upload');
    try {
      const up = await recordApi.upload(file, 'board');
      setPreviewUrl(URL.createObjectURL(file));
      patch({ uploadId: up.id, uploadName: file.name, source: 'photo', parse: null, values: {} });
    } catch (e) {
      setError(errText(e, t));
    } finally {
      setBusy(null);
    }
  };

  const { gym: gymSel, gyms: gymList, pick: pickGymName, ready: gymsReady } = useClubGym('all');

  const pickGym = async (gymName?: string) => {
    setBusy('gym');
    setError(null);
    setNotice(null);
    try {
      const p = await recordApi.gymProgram(draft.day, gymName ?? gymSel);
      if (!p.found || !p.form) { setNotice('no_gym'); return; }
      const res: ParseResult = {
        recognized: true, reason: null, board_text: p.board_text ?? '', blocks: p.blocks ?? [],
        blocks_verified: p.blocks_verified, form: p.form, template_text: p.template_text,
      };
      setDraft((d) => ({ ...d, source: 'gym', parse: res, boardText: res.board_text ?? '', gymDay: d.day, gymName: p.gym ?? null, values: {}, step: 'result' }));
    } catch (e) {
      setError(errText(e, t));
    } finally {
      setBusy(null);
    }
  };

  // с deep link сразу открываем программу зала
  const autoGym = useRef(deepGym);
  useEffect(() => {
    if (autoGym.current && gymsReady) {    // ждём список залов: в ссылке может быть название зала
      autoGym.current = false;
      const fromUrl = sp.get('gym');
      void pickGym(fromUrl && fromUrl !== '1' ? fromUrl : undefined);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gymsReady]);

  // ---------- сохранение ----------
  const built = useMemo(() => buildPutBody(draft), [draft]);
  const submit = async () => {
    setError(null);
    if (Object.keys(built.errors).length) { setError(t('rec.err.fix_fields')); return; }
    const bw = draft.bodyweight.trim();
    if (bw && (parseDecimal(bw) == null || parseDecimal(bw)! < 20 || parseDecimal(bw)! > 500)) { setError(t('rec.err.bodyweight')); return; }
    setBusy('save');
    try {
      const saved = await recordApi.put(draft.uuid, built.body);
      setDraft((d) => ({ ...d, saved, step: 'done' }));
    } catch (e) {
      const k = classifyError(e);
      setError(k === 'network' ? t('rec.err.save_network') : errText(e, t));
    } finally {
      setBusy(null);
    }
  };

  const restart = () => {
    clearDraft();
    setDraft(newDraft());
    setRestored(false);
    setError(null);
    setNotice(null);
    setPreviewUrl(null);
  };
  const another = () => {
    clearDraft();
    setDraft({ ...newDraft(), day: draft.day, sport: draft.sport, uuid: newUuid(), startTime: nowHHMM() });
    setPreviewUrl(null);
  };

  // ---------- шаги ----------
  const today = todayIso();
  const yest = yesterdayIso();
  // программа зала на выбранный день: если тренер её загрузил, показываем сразу
  const gymCard = useGymProgram(draft.day, board && draft.step === 'setup', gymSel);

  const stepSetup = (
    <>
      <div className="sec">{t('rec.when')}</div>
      <div className="rec-chips">
        <button type="button" className={`rec-chip${draft.day === today ? ' on' : ''}`} onClick={() => patchSetup({ day: today })}>{t('rec.today')}</button>
        <button type="button" className={`rec-chip${draft.day === yest ? ' on' : ''}`} onClick={() => patchSetup({ day: yest })}>{t('rec.yesterday')}</button>
      </div>
      <label className="field">
        <span>{t('rec.date')}</span>
        <input type="date" value={draft.day} max={today} onChange={(e) => e.target.value && patchSetup({ day: e.target.value })} />
      </label>
      <label className="field">
        <span>{t('rec.start_time')}</span>
        <input type="time" value={draft.startTime} onChange={(e) => patch({ startTime: e.target.value })} />
      </label>
      <GymPicker gym={gymSel} gyms={gymList} onPick={pickGymName} />
      {gymCard && (
        <div className="gym-card">
          <div><b>🏢 {t('rec.gym_card_title', { day: shortDay(draft.day) })}</b>{gymCard.gym ? <span className="mut"> · {gymCard.gym}</span> : null}</div>
          <pre className="gym-prev">{previewLines(gymCard.board_text)}</pre>
          <button type="button" className="btn primary block" disabled={busy === 'gym'} onClick={() => { patch({ source: 'gym' }); void pickGym(); }}>{t('rec.gym_use')}</button>
          <div className="mut" style={{ fontSize: 12.5, marginTop: 6 }}>{t('rec.gym_or_own')}</div>
        </div>
      )}
      {manageClub && (
        <Link className="btn block" style={{ marginTop: 10 }} to={`/club/edit?day=${draft.day}`}>
          {gymCard ? `✏️ ${t('rec.gym_edit_day', { day: shortDay(draft.day) })}` : `📷 ${t('rec.gym_add_day', { day: shortDay(draft.day) })}`}
        </Link>
      )}
      <div className="sec">{t('rec.kind')}</div>
      <div className="rec-chips" role="group" aria-label={t('rec.kind')}>
        {SPORTS.map((s) => (
          <button key={s} type="button" className={`rec-chip${draft.sport === s ? ' on' : ''}`} aria-pressed={draft.sport === s} onClick={() => patchSetup({ sport: s })}>{t(`rec.sport.${s}`)}</button>
        ))}
      </div>
      <div className="mut" style={{ fontSize: 13 }}>{t('rec.multi_hint')}</div>
      <div className="rec-actions">
        <button type="button" className="btn primary block" disabled={busy === 'gym'}
          onClick={() => {
            // программа зала на этот день уже есть: сразу по ней, доску не просим
            if (board && gymCard && !draft.parse) { patch({ source: 'gym' }); void pickGym(); return; }
            go(board ? 'board' : 'result');
          }}>{board && gymCard && !draft.parse ? t('rec.next_gym') : t('rec.next')}</button>
      </div>
    </>
  );

  const sourceCards: { s: Source; icon: string; k: string }[] = [
    { s: 'photo', icon: '📷', k: 'rec.src.photo' },
    { s: 'text', icon: '✍️', k: 'rec.src.text' },
    { s: 'gym', icon: '🏢', k: 'rec.src.gym' },
    { s: 'free', icon: '📝', k: 'rec.src.free' },
  ];
  const fileCam = useRef<HTMLInputElement>(null);
  const fileAny = useRef<HTMLInputElement>(null);

  const stepBoard = (
    <>
      <div className="sec">{t('rec.board_title')}</div>
      <div className="rec-chips" role="group" aria-label={t('rec.board_title')}>
        {sourceCards.map((c) => (
          <button key={c.s} type="button" className={`rec-chip${draft.source === c.s ? ' on' : ''}`} aria-pressed={draft.source === c.s}
            onClick={() => { setNotice(null); setError(null); patch({ source: c.s }); if (c.s === 'gym') void pickGym(); }}>
            {c.icon} {t(c.k)}
          </button>
        ))}
      </div>

      {draft.source === 'photo' && (
        <div>
          <input ref={fileCam} type="file" accept="image/*" capture="environment" className="hidden-file" data-testid="file-cam" onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = ''; }} />
          <input ref={fileAny} type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" className="hidden-file" data-testid="file-any" onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = ''; }} />
          <div className="rec-actions" style={{ marginTop: 0 }}>
            <button type="button" className="btn" disabled={busy === 'upload'} onClick={() => fileCam.current?.click()}>📷 {t('rec.take_photo')}</button>
            <button type="button" className="btn" disabled={busy === 'upload'} onClick={() => fileAny.current?.click()}>🖼 {t('rec.choose_file')}</button>
          </div>
          <div className="mut" style={{ fontSize: 12.5 }}>{t('rec.photo_limit')}</div>
          {busy === 'upload' && <div className="loading" role="status">{t('rec.uploading')}</div>}
          {draft.uploadId && (
            <>
              <img className="rec-preview" alt={t('rec.preview_alt')} src={previewUrl ?? `/api/uploads/${draft.uploadId}`} />
              <EnginePick value={draft.engine} onChange={(e) => patch({ engine: e })} />
              <div className="rec-actions">
                <button type="button" className="btn primary" disabled={busy === 'parse'} onClick={() => runParse({ uploadId: draft.uploadId! })}>{t('rec.recognize')}</button>
              </div>
            </>
          )}
        </div>
      )}

      {draft.source === 'text' && (
        <div>
          <textarea className="rec-board" value={draft.boardText} placeholder={t('rec.text_ph')} aria-label={t('rec.src.text')} onChange={(e) => patch({ boardText: e.target.value })} />
          <EnginePick value={draft.engine} onChange={(e) => patch({ engine: e })} />
          <div className="rec-actions">
            <button type="button" className="btn primary" disabled={busy === 'parse' || !draft.boardText.trim()} onClick={() => runParse({ text: draft.boardText })}>{t('rec.recognize')}</button>
          </div>
        </div>
      )}

      {draft.source === 'gym' && busy === 'gym' && <div className="loading" role="status">{t('common.loading')}</div>}

      {draft.source === 'free' && (
        <div>
          <div className="mut" style={{ fontSize: 13, marginBottom: 8 }}>{t('rec.free_hint')}</div>
          <div className="rec-actions"><button type="button" className="btn primary" onClick={() => go('result')}>{t('rec.next')}</button></div>
        </div>
      )}

      {busy === 'parse' && <div className="loading" role="status">{t('rec.parsing')}</div>}
      {notice && (
        <div className="msg info" role="alert">
          {t(`rec.notice.${notice}`)}
          <div className="rec-actions">
            {notice !== 'no_gym' && <button type="button" className="btn" onClick={() => { setNotice(null); patch({ source: 'text' }); }}>{t('rec.enter_text')}</button>}
            <button type="button" className="btn" onClick={() => { setNotice(null); patch({ source: 'free' }); go('result'); }}>{t('rec.enter_manual')}</button>
          </div>
        </div>
      )}
      <div className="rec-actions"><button type="button" className="btn" onClick={() => go('setup')}>{t('rec.back')}</button></div>
    </>
  );

  const parse = draft.parse;
  const edited = !!parse && draft.source !== 'gym' && draft.boardText.trim() !== (parse.board_text ?? '').trim();
  const stepCheck = parse && (
    <>
      <div className="sec">{t('rec.check_title')}</div>
      {draft.source === 'photo' && draft.uploadId && <img className="rec-preview" alt={t('rec.preview_alt')} src={previewUrl ?? `/api/uploads/${draft.uploadId}`} />}
      {draft.source === 'gym' && <div className="msg info">{t('rec.gym_readonly', { day: draft.gymDay ?? draft.day })}</div>}
      <textarea className="rec-board" value={draft.boardText} readOnly={draft.source === 'gym'} aria-label={t('rec.board_text')} onChange={(e) => patch({ boardText: e.target.value })} />
      {parse.annotated && draft.source !== 'gym' && !edited && (
        <details style={{ marginTop: 8 }}><summary className="mut">{t('rec.annotated')}</summary><div className="rec-pre">{parse.annotated}</div></details>
      )}
      {parse.blocks_verified && <div className="mut" style={{ fontSize: 12.5, marginTop: 6 }}>{t('rec.verified')}</div>}
      {busy === 'parse' && <div className="loading" role="status">{t('rec.parsing')}</div>}
      {notice && <div className="msg info" role="alert">{t(`rec.notice.${notice}`)}</div>}
      <div className="rec-actions">
        <button type="button" className="btn primary" disabled={edited || busy === 'parse'} onClick={() => go('result')}>{t('rec.accept')}</button>
        {edited && <button type="button" className="btn" disabled={busy === 'parse'} onClick={() => runParse({ text: draft.boardText, verbatim: true })}>{t('rec.reparse_text')}</button>}
      </div>
      {draft.source !== 'gym' && (
        <>
          <EnginePick value={draft.engine} onChange={(e) => patch({ engine: e })} />
          <div className="rec-actions">
            <button type="button" className="btn" disabled={busy === 'parse'}
              onClick={() => runParse(draft.source === 'photo' && draft.uploadId ? { uploadId: draft.uploadId } : { text: draft.boardText })}>{t('rec.again')}</button>
            <button type="button" className="btn" onClick={() => go('board')}>{t('rec.back')}</button>
          </div>
        </>
      )}
      {draft.source === 'gym' && <div className="rec-actions"><button type="button" className="btn" onClick={() => go('board')}>{t('rec.back')}</button></div>}
    </>
  );

  const showForm = board && draft.source !== 'free' && parse;
  const stepResult = (
    <>
      <div className="sec">{t('rec.result_title')}</div>
      {draft.source === 'gym' && draft.boardText && (
        <details className="gym-prog"><summary className="mut">{t('rec.gym_card_title', { day: shortDay(draft.gymDay ?? draft.day) })}</summary><pre className="gym-prev">{draft.boardText}</pre></details>
      )}
      {showForm && (
        <>
          <HowTo />
          <FormBlocks form={parse.form} values={draft.values} errors={built.errors} onChange={(k, v) => setDraft((d) => ({ ...d, values: { ...d.values, [k]: v } }))} />
        </>
      )}
      {board && draft.source === 'free' && (
        <label className="field">
          <span>{t('rec.free_text')}</span>
          <textarea className="rec-board" value={draft.freeText} placeholder={t('rec.free_ph')} onChange={(e) => patch({ freeText: e.target.value })} />
        </label>
      )}
      {!board && (
        <div className="card" style={{ marginBottom: 10 }}>
          <label className="field"><span>{t('rec.duration')}</span>
            <input inputMode="decimal" value={draft.duration} onChange={(e) => patch({ duration: e.target.value.replace(/[^\d.,]/g, '') })} /></label>
          <label className="field"><span>{t('rec.distance')}</span>
            <input inputMode="decimal" value={draft.distance} onChange={(e) => patch({ distance: e.target.value.replace(/[^\d.,]/g, '') })} /></label>
          <label className="field"><span>{t('rec.note')}</span>
            <textarea rows={2} value={draft.freeText} onChange={(e) => patch({ freeText: e.target.value })} /></label>
        </div>
      )}
      <div className="sec">{t('rec.overall')}</div>
      <RpeScale value={draft.rpe} onChange={(v) => patch({ rpe: v })} />
      {board && <ScalingPick value={draft.scaling} onChange={(v) => patch({ scaling: v })} />}
      <label className="field">
        <span>{t('rec.bodyweight')}</span>
        <input inputMode="decimal" placeholder="kg" value={draft.bodyweight} onChange={(e) => patch({ bodyweight: e.target.value.replace(/[^\d.,]/g, '') })} />
      </label>
      {error && <div className="msg err" role="alert">{error}</div>}
      <div className="rec-actions">
        <button type="button" className="btn primary" disabled={busy === 'save'} onClick={submit}>{busy === 'save' ? t('rec.saving') : t('rec.save')}</button>
        <button type="button" className="btn" onClick={() => go(board ? (draft.source === 'free' ? 'board' : 'check') : 'setup')}>{t('rec.back')}</button>
      </div>
    </>
  );

  const sv = draft.saved;
  const stepDone = sv && (
    <>
      <div className="msg ok" role="status">{t('rec.saved')}</div>
      <div className="card" style={{ marginBottom: 8 }}>
        <div style={{ fontWeight: 600 }}>{t(`rec.sport.${sv.sport}`)} · {sv.day}</div>
        {sv.score && <div className="reschip" style={{ marginTop: 6 }}>{[sv.scaling?.toUpperCase(), sv.score, sv.rpe ? `RPE ${sv.rpe}` : null].filter(Boolean).join(' · ')}</div>}
        {sv.metcon_lines?.map((l, i) => <div key={i} className="hist">{l}</div>)}
        {sv.bodyweight != null && <div className="hist">{t('rec.bodyweight')}: {sv.bodyweight}</div>}
      </div>
      <FollowUps id={draft.uuid} credited={sv.credited} ambiguous={sv.ambiguous} proposed={sv.proposed_maxes} skippedQuota={sv.lifts_skipped_quota} />
      <div className="rec-actions">
        <Link className="btn" to={`/workouts/${sv.day}`}>{t('rec.open_day')}</Link>
        <Link className="btn" to={`/w/${draft.uuid}`}>{t('rec.edit')}</Link>
      </div>
      <div className="rec-actions">
        <button type="button" className="btn" onClick={another}>{t('rec.another')}</button>
        <button type="button" className="btn primary" onClick={() => { clearDraft(); nav('/workouts'); }}>{t('rec.done')}</button>
      </div>
    </>
  );

  return (
    <>
      <button type="button" className="back linkbtn" style={{ textDecoration: 'none', color: 'var(--mut)' }} onClick={() => nav(-1)}>{t('workout.back')}</button>
      <h1>{t('rec.title')}</h1>
      <Progress step={draft.step} sport={draft.sport} />
      {restored && draft.step !== 'done' && (
        <div className="msg info" role="status">
          {t('rec.restored')}{' '}
          <button type="button" className="linkbtn" onClick={restart}>{t('rec.restart')}</button>
        </div>
      )}
      {error && draft.step !== 'result' && <div className="msg err" role="alert">{error}</div>}
      {draft.step === 'setup' && stepSetup}
      {draft.step === 'board' && stepBoard}
      {draft.step === 'check' && (stepCheck || <button type="button" className="btn" onClick={() => go('board')}>{t('rec.back')}</button>)}
      {draft.step === 'result' && stepResult}
      {draft.step === 'done' && (stepDone || <button type="button" className="btn" onClick={restart}>{t('rec.restart')}</button>)}
    </>
  );
}
