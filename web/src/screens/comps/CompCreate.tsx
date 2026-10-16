import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { compsApi, type CompEventRow } from '../../api/comps';
import { useT } from '../../i18n';
import { BackLink, Field, apiMessage } from '../ui5';
import {
  CATEGORIES, joinDivisionChoice, parseCreateResponse, serializeCreateEvent, validDateInput, type CreateForm,
} from './serialize';

function Candidate({ c, onJoin }: { c: CompEventRow; onJoin: (id: number, div?: number) => void }) {
  const t = useT();
  const choice = joinDivisionChoice(c);
  const [div, setDiv] = useState<number>(c.divisions[0]?.id ?? 0);
  return (
    <div className="card" style={{ marginBottom: 8 }}>
      <div style={{ fontWeight: 600 }}>{c.name}</div>
      <div className="mut" style={{ fontSize: 13, marginBottom: 8 }}>{c.city} · {c.date_start}</div>
      {choice === 'choose' && (
        <label className="field">
          <span>{t('comp5.division')}</span>
          <select value={div} onChange={(e) => setDiv(Number(e.target.value))}>
            {c.divisions.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
      )}
      <button type="button" className="btn block" onClick={() => onJoin(c.id, choice === 'choose' ? div : choice ?? undefined)}>{t('comp5.join')}</button>
    </div>
  );
}

export function CompCreateScreen() {
  const t = useT();
  const nav = useNavigate();
  const [f, setF] = useState<CreateForm>({ name: '', date: '', city: '', category: 'rx', division: '' });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cands, setCands] = useState<CompEventRow[] | null>(null);
  const set = (k: keyof CreateForm) => (e: { target: { value: string } }) => setF((s) => ({ ...s, [k]: e.target.value }) as CreateForm);

  async function submit(force = false) {
    const er: Record<string, string> = {};
    if (!f.name.trim()) er.name = t('comp5.err.name');
    if (!validDateInput(f.date)) er.date = t('comp5.err.date');
    if (!f.city.trim()) er.city = t('comp5.err.city');
    if (f.category === 'custom' && !f.division.trim()) er.division = t('comp5.err.division');
    setErrs(er);
    setGeneral(null);
    if (Object.keys(er).length) return;
    setBusy(true);
    try {
      const res = parseCreateResponse(await compsApi.create(serializeCreateEvent(f, force)));
      if (res.kind === 'duplicate') setCands(res.candidates);
      else nav(`/comps/${res.eventId}`, { replace: true });
    } catch (e) {
      setGeneral(apiMessage(e, t));
    } finally {
      setBusy(false);
    }
  }
  async function join(id: number, div?: number) {
    setBusy(true);
    try {
      await compsApi.join(id, div);
      nav(`/comps/${id}`, { replace: true });
    } catch (e) {
      setGeneral(apiMessage(e, t));
      setBusy(false);
    }
  }

  if (cands) {
    return (
      <>
        <BackLink to="/comps" />
        <h1>{t('comp5.dup_title')}</h1>
        <p className="sub">{t('comp5.dup_text')}</p>
        {cands.map((c) => <Candidate key={c.id} c={c} onJoin={(id, d) => void join(id, d)} />)}
        {general && <div className="msg err" role="alert">{general}</div>}
        <button type="button" className="btn primary block" disabled={busy} onClick={() => void submit(true)}>{t('comp5.force_new')}</button>
        <button type="button" className="btn block" style={{ marginTop: 8 }} onClick={() => setCands(null)}>{t('common.back')}</button>
      </>
    );
  }
  return (
    <>
      <BackLink to="/comps" />
      <h1>{t('comp5.create')}</h1>
      <form onSubmit={(e) => { e.preventDefault(); void submit(); }} noValidate>
        <Field label={t('comp5.name')} error={errs.name}><input value={f.name} onChange={set('name')} /></Field>
        <Field label={t('comp5.date')} error={errs.date} hint={t('comp5.date_hint')}><input value={f.date} inputMode="numeric" placeholder="12.04.2026" onChange={set('date')} /></Field>
        <Field label={t('comp5.city')} error={errs.city}><input value={f.city} onChange={set('city')} /></Field>
        <Field label={t('comp5.division')}>
          <select value={f.category} onChange={set('category')}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{t(`comp5.cat.${c}`)}</option>)}
            <option value="custom">{t('comp5.cat.custom')}</option>
          </select>
        </Field>
        {f.category === 'custom' && <Field label={t('comp5.division_name')} error={errs.division}><input value={f.division} onChange={set('division')} /></Field>}
        {general && <div className="msg err" role="alert">{general}</div>}
        <button type="submit" className="btn primary block" disabled={busy}>{t('comp5.create_btn')}</button>
      </form>
    </>
  );
}
