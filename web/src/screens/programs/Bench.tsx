import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  newId, programsApi, type Checkin, type FinishResult, type SessionView, type SetRow,
} from '../../api/programs';
import { ApiError } from '../../api/client';
import { Card } from '../../components/ui';
import { useI18n } from '../../i18n';
import { mmss } from '../../lib/format';
import { FocusChips } from './describe';
import { Crumbs, liftLabel, type LiftNames } from './parts';
import {
  currentSet, diffPlanned, emptyLocal, groupDiffs, loadLocal, overlayLocal, pendingPuts, progress, pruneLocal, saveLocal,
  type LocalSession, type PlanDiff,
} from './benchState';
import { alertRestOver, primeAudio, restEndAt, useCountdown, useWakeLock } from './rest';
import { parseKg } from './enrollForm';
import { fmtKg, loc } from './tree';
import './programs.css';

interface Toast { why: string; diffs: PlanDiff[]; lifts: LiftNames }

function RestBar({ endAt, label, onClear }: { endAt: number; label: string | null; onClear: () => void }) {
  const { t } = useI18n();
  const [over, setOver] = useState(false);
  const left = useCountdown(endAt, () => {
    setOver(true);
    alertRestOver();
  });
  return (
    <div className={`rest${over ? ' over' : ''}`} role="timer" aria-live="off">
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 12, opacity: 0.8 }}>{over ? t('pg.rest_over') : t('pg.rest')}{label ? ` · ${label}` : ''}</div>
        <div className="tm" data-testid="rest-left">{over ? '0:00' : mmss(left)}</div>
      </div>
      <button type="button" onClick={onClear}>{over ? t('pg.ok') : t('pg.skip')}</button>
    </div>
  );
}

function CheckinCard({ busy, onSubmit, onSkip }: { busy: boolean; onSubmit: (c: Checkin) => void; onSkip: () => void }) {
  const { t } = useI18n();
  const [c, setC] = useState<Checkin>({});
  const flag = (k: 'tired' | 'sleepy' | 'joint' | 'ill') => (
    <button type="button" className={`chip${c[k] ? ' on' : ''}`} aria-pressed={!!c[k]} onClick={() => setC({ ...c, [k]: !c[k] })}>{t(`pg.ci.${k}`)}</button>
  );
  return (
    <Card>
      <b>{t('pg.ci.title')}</b>
      <div className="mut" style={{ fontSize: 13 }}>{t('pg.ci.hint')}</div>
      <div style={{ marginTop: 8, fontSize: 13 }}>{t('pg.ci.energy')}</div>
      <div className="grid5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" className={`chip${c.energy === n ? ' on' : ''}`} aria-pressed={c.energy === n}
            onClick={() => setC({ ...c, energy: c.energy === n ? undefined : n })}>{n}</button>
        ))}
      </div>
      <div className="chips">{flag('joint')}{flag('tired')}{flag('sleepy')}{flag('ill')}</div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button type="button" className="btn primary" style={{ minHeight: 56, flex: 1 }} disabled={busy} onClick={() => onSubmit(c)}>{t('pg.ci.apply')}</button>
        <button type="button" className="btn" style={{ minHeight: 56 }} disabled={busy} onClick={onSkip}>{t('pg.ci.skip')}</button>
      </div>
    </Card>
  );
}

function FinishPanel({ busy, onFinish }: { busy: boolean; onFinish: (rpe: number, feel: number | null) => void }) {
  const { t } = useI18n();
  const [rpe, setRpe] = useState<number | null>(null);
  const [feel, setFeel] = useState<number | null>(null);
  return (
    <Card>
      <b>{t('pg.fin.title')}</b>
      <div style={{ marginTop: 8, fontSize: 13 }}>{t('pg.fin.rpe')}</div>
      <div className="grid5">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
          <button key={n} type="button" className={`chip${rpe === n ? ' on' : ''}`} aria-pressed={rpe === n} onClick={() => setRpe(n)}>{n}</button>
        ))}
      </div>
      <div style={{ fontSize: 13 }}>{t('pg.fin.feel')}</div>
      <div className="grid5">
        {['😖', '🙁', '😐', '🙂', '😄'].map((e, i) => (
          <button key={e} type="button" className={`chip${feel === i + 1 ? ' on' : ''}`} aria-pressed={feel === i + 1} onClick={() => setFeel(i + 1)}>{e}</button>
        ))}
      </div>
      <button type="button" className="btn primary block" style={{ minHeight: 60, marginTop: 8 }} disabled={busy || rpe == null} onClick={() => rpe != null && onFinish(rpe, feel)}>
        {t('pg.fin.submit')}
      </button>
    </Card>
  );
}

function Summary({ res, enrollmentId, names, onRefresh, refreshed }: {
  res: FinishResult; enrollmentId: string; names: LiftNames; onRefresh: () => void; refreshed: string[] | null;
}) {
  const { t, lang } = useI18n();
  return (
    <>
      <div className="msg ok" role="status">✅ {t('pg.fin.done')}{res.enrollment_done ? ` ${t('pg.fin.enr_done')}` : ''}</div>
      <Card>
        <b>{t('pg.fin.maxes')}</b>
        {res.maxes.length === 0 && <div className="mut">{t('pg.fin.no_maxes')}</div>}
        {res.maxes.map((m) => (
          <div className="kv" key={m.lift}><span>{liftLabel(m.lift, names, lang)}</span><b>{fmtKg(m.kg)} {t('pg.kg')}</b></div>
        ))}
        {res.base_updated.length > 0 && <div className="msg info">{t('pg.fin.base_updated', { lifts: res.base_updated.map((l) => liftLabel(l, names, lang)).join(', ') })}</div>}
      </Card>
      {res.refresh.length > 0 && refreshed == null && (
        <Card>
          <b>{t('pg.fin.refresh_q')}</b>
          {res.refresh.map((r) => <div key={r.lift} style={{ fontSize: 14, margin: '4px 0' }}>{lang === 'en' ? r.en : r.ru}</div>)}
          <button type="button" className="btn primary block" style={{ minHeight: 56, marginTop: 8 }} onClick={onRefresh}>{t('pg.fin.refresh_yes')}</button>
        </Card>
      )}
      {refreshed && <div className="msg ok">{t('pg.refreshed', { lifts: refreshed.map((l) => liftLabel(l, names, lang)).join(', ') || '—' })}</div>}
      <Link className="btn block" style={{ minHeight: 56 }} to={`/programs/my/${enrollmentId}`}>{t('pg.back_to_program')}</Link>
    </>
  );
}

export function BenchScreen() {
  const { sid = '' } = useParams();
  const { t, lang } = useI18n();
  const [session, setSession] = useState<SessionView | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [local, setLocalState] = useState<LocalSession>(() => loadLocal(sid) ?? emptyLocal(sid, newId()));
  const [toast, setToast] = useState<Toast | null>(null);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [custom, setCustom] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [finishOpen, setFinishOpen] = useState(false);
  const [result, setResult] = useState<FinishResult | null>(null);
  const [refreshed, setRefreshed] = useState<string[] | null>(null);
  const [names, setNames] = useState<LiftNames>({});
  const sessionRef = useRef<SessionView | null>(null);
  const localRef = useRef(local);
  const chain = useRef<Promise<void>>(Promise.resolve());

  const patchLocal = useCallback((fn: (l: LocalSession) => LocalSession) => {
    const next = fn(localRef.current);
    localRef.current = next;
    setLocalState(next);
    saveLocal(next);
  }, []);
  const putSession = useCallback((s: SessionView) => {
    sessionRef.current = s;
    setSession(s);
    const m: LiftNames = {};
    for (const b of s.blocks) for (const e of b.exercises) m[e.lift] = e.name;
    setNames(m);
  }, []);
  const settle = useCallback((setId: string) => {
    patchLocal((l) => (l.sets[setId] ? { ...l, sets: { ...l.sets, [setId]: { ...l.sets[setId], pending: false } } } : l));
  }, [patchLocal]);

  /** Сервер — источник правды: грузим сессию, дошлём неподтверждённые отметки, накладываем локальное. */
  const loadAll = useCallback(async () => {
    try {
      let srv = await programsApi.session(sid);
      const puts = pendingPuts(srv, localRef.current);
      let sent = 0;
      for (const p of puts) {
        try {
          await programsApi.putSet(sid, p.setId, p.body);
          settle(p.setId);
          sent++;
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) settle(p.setId); // сессия закрыта: повторять нечего
          else throw e;
        }
      }
      if (sent) srv = await programsApi.session(sid);
      if (localRef.current.restEnd != null && localRef.current.restEnd <= Date.now()) {
        patchLocal((x) => ({ ...x, restEnd: null, restLabel: null }));
      }
      putSession(overlayLocal(srv, localRef.current));
      setOffline(false);
      setError(null);
      if (srv.status === 'done') {
        // повторный finish идемпотентен: вернёт итоги уже завершённой сессии
        const fin = localRef.current.finished ?? (await programsApi.finish(sid).catch(() => null));
        if (fin) setResult(fin);
      }
    } catch (e) {
      if (e instanceof ApiError && e.isNetwork) setOffline(true);
      else setError(e instanceof ApiError ? e : new ApiError(-1, String(e)));
    }
  }, [sid, patchLocal, putSession, settle]);

  useEffect(() => {
    pruneLocal();
    void loadAll();
    const online = () => void loadAll();
    window.addEventListener('online', online);
    return () => window.removeEventListener('online', online);
  }, [loadAll]);

  const curId = session ? currentSet(session)?.id : undefined;
  useEffect(() => {
    // текущий подход — в центр экрана, чтобы его не закрывал таймер отдыха
    if (curId) document.querySelector('[data-testid="current-set"]')?.scrollIntoView?.({ block: 'center', behavior: 'auto' });
  }, [curId]);

  const finished = session?.status === 'done';
  const wakeOk = useWakeLock(!!session && !finished);

  function enqueue(job: () => Promise<void>) {
    chain.current = chain.current.then(job, job);
  }

  function mark(row: SetRow, ok: boolean) {
    const s = sessionRef.current;
    if (!s) return;
    primeAudio(); // звук по окончании отдыха браузер разрешает только после жеста
    const kg = parseKg(custom) ?? row.planned_kg ?? 0;
    const ts = new Date().toISOString();
    const wasEditing = editing === row.id;
    setCustom('');
    setEditing(null);
    setToast(null);
    patchLocal((l) => ({
      ...l,
      sets: { ...l.sets, [row.id]: { done_kg: kg, ok, ts, pending: true } },
      ...(wasEditing ? {} : { restEnd: restEndAt(Date.now(), row.rest_sec), restLabel: null }),
    }));
    const before = overlayLocal(s, localRef.current);
    putSession(before);
    enqueue(async () => {
      try {
        const r = await programsApi.putSet(sid, row.id, { done_kg: kg, reps: row.reps, ok, ts });
        settle(row.id);
        setOffline(false);
        if (r.changed.length) {
          // в ответе только id пересчитанных подходов: новые веса берём из GET и показываем «было → стало»
          const fresh = overlayLocal(await programsApi.session(sid), localRef.current);
          setToast({ why: loc(r.why, lang), diffs: diffPlanned(before, fresh, r.changed), lifts: names });
          putSession(fresh);
        } else if (wasEditing) {
          putSession(overlayLocal(await programsApi.session(sid), localRef.current));
        }
      } catch (e) {
        if (e instanceof ApiError && e.isNetwork) setOffline(true); // отметка осталась pending, уйдёт при возврате сети
        else if (e instanceof ApiError && e.status === 409) void loadAll();
        else setError(e instanceof ApiError ? e : new ApiError(-1, String(e)));
      }
    });
  }

  async function submitCheckin(c: Checkin) {
    setBusy(true);
    try {
      const res = await programsApi.checkin(sid, c);
      patchLocal((l) => ({ ...l, checkinSkipped: true }));
      putSession(overlayLocal(res, localRef.current));
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(-1, String(e)));
    } finally {
      setBusy(false);
    }
  }

  async function finish(rpe: number, feel: number | null) {
    const s = sessionRef.current;
    if (!s) return;
    setBusy(true);
    try {
      await chain.current; // сначала дойдут все подходы
      const res = await programsApi.finish(sid, { rpe, ...(feel != null ? { feel } : {}), activity_id: localRef.current.activityId });
      patchLocal((l) => ({ ...l, finished: res, restEnd: null }));
      setResult(res);
      putSession({ ...s, status: 'done' });
    } catch (e) {
      if (e instanceof ApiError && e.isNetwork) setOffline(true);
      else setError(e instanceof ApiError ? e : new ApiError(-1, String(e)));
    } finally {
      setBusy(false);
    }
  }

  async function refreshBase() {
    const s = sessionRef.current;
    if (!s) return;
    try {
      const r = await programsApi.refreshBase(s.enrollment_id, result?.refresh.map((x) => x.lift));
      setRefreshed(r.refreshed ?? []);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(-1, String(e)));
    }
  }

  if (error && !session) {
    return (
      <div className="msg err" role="alert">
        {error.status === 404 ? t('err.not_found') : t('err.generic', { msg: error.detail })}
        <div style={{ marginTop: 8 }}><button type="button" className="btn" onClick={() => { setError(null); void loadAll(); }}>{t('net.retry')}</button></div>
      </div>
    );
  }
  if (!session) {
    return offline ? (
      <div className="msg err" role="alert">
        {t('pg.offline_load')}
        <div style={{ marginTop: 8 }}><button type="button" className="btn" onClick={() => void loadAll()}>{t('net.retry')}</button></div>
      </div>
    ) : (
      <div className="loading" role="status">{t('common.loading')}</div>
    );
  }

  const prog = progress(session);
  const cur = currentSet(session);
  const why = lang === 'en' ? session.why_en ?? session.why : session.why;
  const isTest = session.kind === 'test';
  const showCheckin = !finished && !session.checkin && !local.checkinSkipped && prog.done === 0;
  const pending = Object.values(local.sets).filter((x) => x.pending).length;
  const weekNote = loc(session.week_note, lang);

  return (
    <div className="bench">
      <Crumbs items={[{ to: '/programs', label: t('pg.title') }, { to: `/programs/my/${session.enrollment_id}`, label: t('pg.program') }, { label: t('pg.bench') }]} />
      <h1>{loc(session.title, lang)}</h1>
      <div className="sub">
        {loc(session.week_title, lang)} · {t('pg.minutes', { n: session.minutes })} · {t('pg.sets_progress', { done: prog.done, total: prog.total })}
        {isTest && <span className="pg-badge bad" style={{ marginLeft: 8 }}>{t('pg.test_badge')}</span>}
      </div>
      {!wakeOk && !finished && <div className="msg info" role="note">{t('pg.no_wake')}</div>}
      {(offline || pending > 0) && (
        <div className="msg err" role="status">
          {t('pg.offline_marks', { n: pending })}
          <button type="button" className="linkbtn" style={{ marginLeft: 8 }} onClick={() => void loadAll()}>{t('net.retry')}</button>
        </div>
      )}
      {error && <div className="msg err" role="alert">{t('err.generic', { msg: error.detail })}</div>}
      {isTest && (
        <div className="msg info" role="note">
          <b>{t('pg.test_title')}</b>
          <div>{t('pg.test_text')}</div>
          {session.adjust.postpone_advised && <div style={{ marginTop: 6 }}>⚠️ {t('pg.test_postpone')}</div>}
        </div>
      )}
      {session.purpose && (
        <details className="pg-det pg-why" open={prog.done === 0}>
          <summary>{t('pg.why_day')}</summary>
          <p>{loc(session.purpose, lang)}</p>
          <FocusChips focus={session.focus} />
          {session.week_type_info && <p className="mut"><b>{loc(session.week_type_info.title, lang)}.</b> {loc(session.week_type_info.text, lang)}</p>}
        </details>
      )}
      {why && <div className="msg info" role="status">💡 {why}</div>}
      {toast && (
        <div className="msg info" role="status" data-testid="miss-toast">
          <b>{toast.why || t('pg.miss_default')}</b>
          {groupDiffs(toast.diffs).map((d) => (
            <div key={`${d.lift}-${d.from}-${d.to}`} style={{ fontSize: 13 }}>
              {fmtKg(d.from)} → <b>{fmtKg(d.to)}</b> {t('pg.kg')} · {liftLabel(d.lift, toast.lifts, lang)}{d.count > 1 ? ` ×${d.count}` : ''}
            </div>
          ))}
        </div>
      )}
      {weekNote && <div className="mut" style={{ fontSize: 13, marginBottom: 8 }}>{weekNote}</div>}

      {finished && result ? (
        <Summary res={result} enrollmentId={session.enrollment_id} names={names} onRefresh={() => void refreshBase()} refreshed={refreshed} />
      ) : (
        <>
          {showCheckin && <CheckinCard busy={busy} onSubmit={(c) => void submitCheckin(c)} onSkip={() => patchLocal((l) => ({ ...l, checkinSkipped: true }))} />}
          {session.blocks.map((b, bi) => (
            <div key={bi}>
              <div className="mut" style={{ fontSize: 12, textTransform: 'uppercase', margin: '10px 0 4px' }}>{loc(b.title, lang)}</div>
              {b.exercises.map((ex) => (
                <Card key={ex.id} className="ex">
                  <h3>{loc(ex.name, lang)}</h3>
                  {ex.sets.map((row) => {
                    const active = !showCheckin && (editing === row.id || (editing == null && cur?.id === row.id));
                    if (active) {
                      return (
                        <div className="cur-box" key={row.id} data-testid="current-set">
                          <div className="mut" style={{ textAlign: 'center', fontSize: 13 }}>
                            {t('pg.set_n', { n: row.n + 1 })} · {row.kind === 'attempt' ? t('pg.kind.attempt') : row.kind === 'day_max' ? t('pg.kind.day_max') : row.pct ? `${row.pct}%` : ''}
                          </div>
                          <div className="big">{fmtKg(row.planned_kg)} {t('pg.kg')} × {row.reps ?? 1}</div>
                          <div className="row">
                            <button type="button" className="btn btn-xl no" onClick={() => mark(row, false)}>✗ {t('pg.miss')}</button>
                            <button type="button" className="btn btn-xl ok" onClick={() => mark(row, true)}>✓ {t('pg.done')}</button>
                          </div>
                          <div className="alt">
                            <label htmlFor="alt-kg">{t('pg.other_kg')}</label>
                            <input id="alt-kg" inputMode="decimal" placeholder={fmtKg(row.planned_kg)} value={custom} onChange={(e) => setCustom(e.target.value)} />
                          </div>
                        </div>
                      );
                    }
                    const isDone = row.ok != null;
                    return (
                      <button type="button" key={row.id} className={`sr${isDone ? ' done' : ''}${row.ok === false ? ' fail' : ''}`}
                        onClick={() => isDone && setEditing(row.id)} disabled={!isDone} aria-label={isDone ? t('pg.edit_set') : undefined}>
                        <span aria-hidden="true">{row.ok == null ? '○' : row.ok ? '✓' : '✗'}</span>
                        <span className="w">
                          {fmtKg(isDone && row.done_kg != null ? row.done_kg : row.planned_kg)} {t('pg.kg')} × {row.reps ?? 1}
                          <small>{isDone && row.done_kg != null && row.done_kg !== row.planned_kg ? `${t('pg.plan')} ${fmtKg(row.planned_kg)} · ` : ''}{row.pct ? `${row.pct}%` : ''}</small>
                        </span>
                      </button>
                    );
                  })}
                </Card>
              ))}
            </div>
          ))}
          {session.extra_sets.length > 0 && (
            <Card>
              <b>{t('pg.extra')}</b>
              {session.extra_sets.map((r) => (
                <div className="kv" key={r.id}><span>{r.exercise ? liftLabel(r.exercise, names, lang) : ''}</span><span>{fmtKg(r.done_kg)} {t('pg.kg')} × {r.reps ?? 1}</span></div>
              ))}
            </Card>
          )}
          {!showCheckin && !finishOpen && (
            <button type="button" className={`btn block${cur ? '' : ' primary'}`} style={{ minHeight: 60, marginTop: 8 }} disabled={prog.done === 0}
              onClick={() => {
                if (!cur || window.confirm(t('pg.fin.partial'))) setFinishOpen(true);
              }}>{t('pg.fin.open')}</button>
          )}
          {finishOpen && <FinishPanel busy={busy} onFinish={(r, f) => void finish(r, f)} />}
        </>
      )}
      <div className="spacer" />
      {local.restEnd != null && !finished && (
        <RestBar key={local.restEnd} endAt={local.restEnd} label={local.restLabel} onClear={() => patchLocal((l) => ({ ...l, restEnd: null, restLabel: null }))} />
      )}
    </div>
  );
}
