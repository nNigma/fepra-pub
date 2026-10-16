// Управление целями и быстрый ввод ПМ на экране «Цели».
import { useMemo, useState } from 'react';
import { recordApi, type PmResult } from '../../api/record';
import type { Discipline } from '../../api/types';
import { useI18n } from '../../i18n';
import { errText } from './errors';
import { normalizeTime, parseDecimal, parseWeightReps } from './logic';
import { tierText } from './FollowUps';
import './record.css';

const LEVELS = { ru: ['Любитель', 'Средний', 'Продвинутый', 'Элита'], en: ['Amateur', 'Intermediate', 'Advanced', 'Elite'] };

/** Значение цели/ПМ под единицы дисциплины -> то, что понимает бэкенд. */
export function targetFor(unit: string | undefined, raw: string): string | null {
  const v = raw.trim();
  if (!v) return null;
  if (unit === 'time') return normalizeTime(v) || null;
  if (unit === 'rounds') return /^\d{1,4}$/.test(v) ? v : null;
  const n = parseDecimal(v);
  return n != null && n > 0 && n <= 1000 ? String(n) : null;
}

function DiscSelect({ list, value, onChange, label }: { list: Discipline[]; value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">—</option>
        {list.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
      </select>
    </label>
  );
}

export function AddGoal({ all, onChanged }: { all: Discipline[]; onChanged: () => void }) {
  const { t, lang } = useI18n();
  const [kind, setKind] = useState<'numeric' | 'level'>('numeric');
  const [disc, setDisc] = useState('');
  const [target, setTarget] = useState('');
  const [level, setLevel] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const meta = all.find((d) => d.id === disc);
  const hint = meta?.unit === 'time' ? t('rec.goal_target_time') : meta?.unit === 'rounds' ? t('rec.goal_target_rounds') : t('rec.goal_target_kg');

  const submit = async () => {
    setMsg(null);
    if (!disc) { setMsg({ ok: false, text: t('rec.goal_pick_disc') }); return; }
    let tv: string | null;
    if (kind === 'level') tv = level || null;
    else tv = targetFor(meta?.unit, target);
    if (!tv) { setMsg({ ok: false, text: t('rec.goal_bad_target') }); return; }
    setBusy(true);
    try {
      await recordApi.addGoal({ kind, discipline: disc, target: tv });
      setMsg({ ok: true, text: t('rec.goal_added') });
      setTarget('');
      onChanged();
    } catch (e) {
      setMsg({ ok: false, text: errText(e, t) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="card" style={{ marginTop: 10 }}>
      <summary style={{ fontWeight: 600, minHeight: 32 }}>{t('rec.goal_add')}</summary>
      <div className="rec-chips" role="group" aria-label={t('rec.goal_kind')} style={{ marginTop: 10 }}>
        <button type="button" className={`rec-chip${kind === 'numeric' ? ' on' : ''}`} onClick={() => setKind('numeric')}>{t('rec.goal_numeric')}</button>
        <button type="button" className={`rec-chip${kind === 'level' ? ' on' : ''}`} onClick={() => setKind('level')}>{t('rec.goal_level')}</button>
      </div>
      <DiscSelect list={all} value={disc} onChange={setDisc} label={t('rec.discipline')} />
      {kind === 'numeric' ? (
        <label className="field"><span>{t('rec.goal_target')} ({hint})</span>
          <input inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} /></label>
      ) : (
        <label className="field"><span>{t('rec.goal_level_pick')}</span>
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">—</option>
            {LEVELS[lang].map((l) => <option key={l} value={l}>{l}</option>)}
          </select></label>
      )}
      {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role={msg.ok ? 'status' : 'alert'}>{msg.text}</div>}
      <button type="button" className="btn primary" disabled={busy} onClick={submit}>{t('rec.goal_add_btn')}</button>
    </details>
  );
}

export function GoalActions({ id, onDone }: { id: number; onDone: () => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try { await fn(); onDone(); } catch (e) { setErr(errText(e, t)); } finally { setBusy(false); }
  };
  return (
    <div>
      <div className="rec-inline" style={{ marginTop: 6 }}>
        <button type="button" className="btn" disabled={busy} onClick={() => run(() => recordApi.completeGoal(id))}>{t('rec.goal_complete')}</button>
        <button type="button" className="btn" disabled={busy} onClick={() => run(() => recordApi.archiveGoal(id))}>{t('rec.goal_archive')}</button>
      </div>
      {err && <div className="msg err" role="alert">{err}</div>}
    </div>
  );
}

export function QuickPm({ lifts, benchmarks, onChanged }: { lifts: Discipline[]; benchmarks: Discipline[]; onChanged: () => void }) {
  const { t } = useI18n();
  const [type, setType] = useState<'lift' | 'benchmark'>('lift');
  const [disc, setDisc] = useState('');
  const [val, setVal] = useState('');
  const [res, setRes] = useState<PmResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const list = type === 'lift' ? lifts : benchmarks;
  const meta = useMemo(() => list.find((d) => d.id === disc), [list, disc]);

  const submit = async () => {
    setErr(null);
    setRes(null);
    if (!disc) { setErr(t('rec.goal_pick_disc')); return; }
    let body: { discipline: string; value: string | number; reps?: number };
    if (type === 'lift') {
      const p = parseWeightReps(val);
      if (!p || p.weight <= 0) { setErr(t('rec.pm_bad_lift')); return; }
      body = { discipline: disc, value: p.weight, reps: p.reps ?? 1 };
    } else {
      const v = targetFor(meta?.unit, val);
      if (!v) { setErr(t('rec.pm_bad_bench')); return; }
      body = { discipline: disc, value: v };
    }
    setBusy(true);
    try {
      setRes(await recordApi.enterPm(body));
      setVal('');
      onChanged();
    } catch (e) {
      setErr(errText(e, t));
    } finally {
      setBusy(false);
    }
  };
  const tier = res ? tierText({ ...res, weight: 0, reps: 0 }) : null;
  return (
    <details className="card" style={{ marginTop: 10 }}>
      <summary style={{ fontWeight: 600, minHeight: 32 }}>{t('rec.pm_title')}</summary>
      <div className="rec-chips" style={{ marginTop: 10 }} role="group" aria-label={t('rec.pm_title')}>
        <button type="button" className={`rec-chip${type === 'lift' ? ' on' : ''}`} onClick={() => { setType('lift'); setDisc(''); }}>{t('rec.pm_lift')}</button>
        <button type="button" className={`rec-chip${type === 'benchmark' ? ' on' : ''}`} onClick={() => { setType('benchmark'); setDisc(''); }}>{t('rec.pm_bench')}</button>
      </div>
      <DiscSelect list={list} value={disc} onChange={setDisc} label={t('rec.discipline')} />
      <label className="field"><span>{type === 'lift' ? t('rec.pm_lift_hint') : meta?.unit === 'time' ? t('rec.goal_target_time') : t('rec.goal_target_rounds')}</span>
        <input inputMode={type === 'lift' ? 'text' : 'decimal'} value={val} onChange={(e) => setVal(e.target.value)} /></label>
      {err && <div className="msg err" role="alert">{err}</div>}
      {res && (
        <div className="rec-ok" role="status">
          <b>{res.name}</b>: {res.value}{res.reps ? `×${res.reps}` : ''}
          {res.est_1rm != null && <> → {t('rec.est_1rm', { v: res.est_1rm })}</>}
          {tier && <> · {t('rec.tier', { v: tier })}</>}
        </div>
      )}
      <button type="button" className="btn primary" disabled={busy} onClick={submit}>{t('rec.pm_save')}</button>
    </details>
  );
}
