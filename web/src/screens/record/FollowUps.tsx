// Что делать после записи: вопросы «рывок/взятие», подтверждение предложенных максов, зачтённые максы.
import { useState } from 'react';
import { recordApi, type Ambiguous, type Credited, type ProposedMax, type ProposedMaxes } from '../../api/record';
import { useT } from '../../i18n';
import { errText } from './errors';

export function tierText(c: Credited): string | null {
  const tr = c.tier;
  if (!tr) return null;
  return typeof tr === 'string' ? tr : tr.level ?? null;
}

export function CreditedRow({ c }: { c: Credited }) {
  const t = useT();
  const tier = tierText(c);
  return (
    <div className="rec-ok">
      <b>{c.name || c.discipline}</b> {c.weight}×{c.reps}
      {c.est_1rm != null && <> → {t('rec.est_1rm', { v: c.est_1rm })}</>}
      {tier && <> · {t('rec.tier', { v: tier })}</>}
    </div>
  );
}

const qKey = (a: Ambiguous) => `${a.movement}|${a.weight}|${a.reps}`;

export function AmbiguousQuestions({ id, items, onCredited }: { id: string; items: Ambiguous[]; onCredited?: (c: Credited) => void }) {
  const t = useT();
  const [done, setDone] = useState<Record<string, true>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!items.length) return null;
  const pick = async (a: Ambiguous, variant: string) => {
    setBusy(qKey(a));
    setErr(null);
    try {
      const c = await recordApi.resolveLift(id, { movement: a.movement, variant, weight: a.weight, reps: a.reps });
      setDone((d) => ({ ...d, [qKey(a)]: true }));
      onCredited?.(c);
    } catch (e) {
      setErr(errText(e, t));
    } finally {
      setBusy(null);
    }
  };
  return (
    <div>
      {items.map((a) => {
        const k = qKey(a);
        const r = done[k];
        return r ? null : (
          <div key={k} className="rec-q" role="group" aria-label={a.movement}>
            <div style={{ marginBottom: 8 }}>{t('rec.ambig_q', { m: a.movement, w: a.weight, r: a.reps })}</div>
            <div className="rec-chips" style={{ marginBottom: 0 }}>
              {a.variants.map((v) => (
                <button key={v.id} type="button" className="rec-chip" disabled={busy === k} onClick={() => pick(a, v.id)}>{v.label}</button>
              ))}
            </div>
          </div>
        );
      })}
      {err && <div className="msg err" role="alert">{err}</div>}
    </div>
  );
}

export function ProposedMaxesBox({ id, proposed, onCredited, onAmbiguous }: {
  id: string; proposed: ProposedMaxes; onCredited: (c: Credited[]) => void; onAmbiguous: (a: Ambiguous[]) => void;
}) {
  const t = useT();
  const [rows, setRows] = useState(() => proposed.maxes.map((m) => ({ ...m, on: true, w: String(m.weight_kg), r: String(m.reps) })));
  const [state, setState] = useState<'idle' | 'busy' | 'done' | 'skipped'>('idle');
  const [err, setErr] = useState<string | null>(null);
  if (!rows.length || state === 'skipped') return null;
  if (state === 'done') return <div className="msg ok">{t('rec.maxes_saved')}</div>;
  const upd = (i: number, p: Partial<(typeof rows)[number]>) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const submit = async () => {
    const maxes: ProposedMax[] = [];
    for (const x of rows) {
      if (!x.on) continue;
      const w = Number(x.w.replace(',', '.'));
      const r = Number(x.r);
      if (!(w > 0) || !(r >= 1)) { setErr(t('rec.maxes_bad')); return; }
      maxes.push({ movement: x.movement, weight_kg: w, reps: r });
    }
    if (!maxes.length) { setState('skipped'); return; }
    setState('busy');
    setErr(null);
    try {
      const res = await recordApi.confirmMaxes(id, maxes);
      onCredited(res.credited ?? []);
      if (res.ambiguous?.length) onAmbiguous(res.ambiguous);
      setState('done');
    } catch (e) {
      setErr(errText(e, t));
      setState('idle');
    }
  };
  return (
    <div className="card" style={{ marginTop: 10 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{t('rec.maxes_title')}</div>
      <div className="mut" style={{ fontSize: 13, marginBottom: 6 }}>{t('rec.maxes_hint')}</div>
      {rows.map((x, i) => (
        <div key={i} className="rec-row" style={{ gridTemplateColumns: 'auto 1fr auto' }}>
          <input type="checkbox" checked={x.on} aria-label={x.movement} style={{ width: 22, height: 22 }} onChange={(e) => upd(i, { on: e.target.checked })} />
          <label>{x.movement}</label>
          <span className="rec-pair">
            <input className="rec-in" inputMode="decimal" aria-label={`${x.movement}: ${t('rec.kg')}`} value={x.w} onChange={(e) => upd(i, { w: e.target.value })} />
            <span aria-hidden="true">×</span>
            <input className="rec-in" inputMode="numeric" aria-label={`${x.movement}: ${t('rec.reps')}`} value={x.r} onChange={(e) => upd(i, { r: e.target.value })} />
          </span>
        </div>
      ))}
      {err && <div className="msg err" role="alert">{err}</div>}
      <div className="rec-actions">
        <button type="button" className="btn primary" disabled={state === 'busy'} onClick={submit}>{t('rec.maxes_confirm')}</button>
        <button type="button" className="btn" onClick={() => setState('skipped')}>{t('rec.skip')}</button>
      </div>
    </div>
  );
}

/** Общий блок «после сохранения» для экрана записи и правки. */
export function FollowUps({ id, credited, ambiguous, proposed, skippedQuota }: {
  id: string; credited?: Credited[]; ambiguous?: Ambiguous[]; proposed?: ProposedMaxes | null; skippedQuota?: boolean;
}) {
  const t = useT();
  const [extra, setExtra] = useState<Credited[]>([]);
  const [moreAmb, setMoreAmb] = useState<Ambiguous[]>([]);
  const all = [...(credited ?? []), ...(proposed?.credited ?? []), ...extra];
  const amb = [...(ambiguous ?? []), ...(proposed?.ambiguous ?? []), ...moreAmb];
  return (
    <>
      {all.length > 0 && (
        <>
          <div className="sec">{t('rec.new_maxes')}</div>
          {all.map((c, i) => <CreditedRow key={`${c.discipline}${i}`} c={c} />)}
        </>
      )}
      <AmbiguousQuestions id={id} items={amb} onCredited={(c) => setExtra((x) => [...x, c])} />
      {proposed && proposed.maxes.length > 0 && (
        <ProposedMaxesBox id={id} proposed={proposed} onCredited={(c) => setExtra((x) => [...x, ...c])} onAmbiguous={(a) => setMoreAmb((x) => [...x, ...a])} />
      )}
      {skippedQuota && <div className="msg info">{t('rec.maxes_quota')}</div>}
    </>
  );
}
