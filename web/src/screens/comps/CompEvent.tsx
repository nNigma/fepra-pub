import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { compsApi, type CompDivision, type CompEvent } from '../../api/comps';
import { Async, Card, SecTitle } from '../../components/ui';
import { useT } from '../../i18n';
import { useFetch } from '../../lib/useFetch';
import { BackLink, apiMessage } from '../ui5';
import { ResultAdd } from './ResultAdd';
import { StageAdd } from './StageAdd';

function Total({ eventId, onDone }: { eventId: number; onDone: () => void }) {
  const t = useT();
  const state = useFetch(() => compsApi.total(eventId), `comp-total:${eventId}`);
  const [pts, setPts] = useState('');
  const [place, setPlace] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function put(body: { total_points?: number; final_place?: number }) {
    try {
      await compsApi.putTotal(eventId, body);
      setMsg({ ok: true, text: t('comp5.total_saved') });
      state.reload();
      onDone();
    } catch (e) {
      setMsg({ ok: false, text: apiMessage(e, t) });
    }
  }
  const manualOk = pts.trim() !== '' && !Number.isNaN(Number(pts.replace(',', '.'))) && /^\d+$/.test(place.trim()) && +place >= 1;
  return (
    <>
      {state.error?.status === 422 ? <div className="mut">{t('comp5.total_none')}</div> : (
        <Async state={state}>
          {(s) => (
            <>
              <div className="kv"><span>{t('comp5.total_points')}</span><b>{s.total_points ?? '—'}</b></div>
              <div className="kv"><span>{t('comp5.total_place')}</span><b>{s.place_str ?? s.final_place ?? '—'}</b></div>
              <button type="button" className="btn block" style={{ margin: '8px 0' }} onClick={() => void put({})}>{t('comp5.total_accept')}</button>
            </>
          )}
        </Async>
      )}
      <form onSubmit={(e) => { e.preventDefault(); if (manualOk) void put({ total_points: Number(pts.replace(',', '.')), final_place: Number(place) }); }} style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <label className="field" style={{ flex: 1, margin: 0 }}><span>{t('comp5.total_points')}</span><input inputMode="decimal" value={pts} onChange={(e) => setPts(e.target.value)} /></label>
        <label className="field" style={{ flex: 1, margin: 0 }}><span>{t('comp5.total_place')}</span><input inputMode="numeric" value={place} onChange={(e) => setPlace(e.target.value)} /></label>
        <button type="submit" className="btn" disabled={!manualOk}>{t('comp5.total_set')}</button>
      </form>
      {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role="status">{msg.text}</div>}
    </>
  );
}

function FieldSize({ d, onDone }: { d: CompDivision; onDone: () => void }) {
  const t = useT();
  const [v, setV] = useState(d.field_size != null ? String(d.field_size) : '');
  const [msg, setMsg] = useState<string | null>(null);
  const ok = /^\d+$/.test(v.trim()) && +v >= 1;
  return (
    <form style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }} onSubmit={(e) => {
      e.preventDefault();
      if (!ok) return;
      compsApi.fieldSize(d.id, Number(v)).then(() => { setMsg(t('comp5.saved')); onDone(); }, (er) => setMsg(apiMessage(er, t)));
    }}>
      <label className="field" style={{ flex: 1, margin: 0 }}><span>{t('comp5.field_size')}</span><input inputMode="numeric" value={v} onChange={(e) => setV(e.target.value)} /></label>
      <button type="submit" className="btn" disabled={!ok}>{t('set.save')}</button>
      {msg && <span className="mut" role="status">{msg}</span>}
    </form>
  );
}

function Body({ ev, reload }: { ev: CompEvent; reload: () => void }) {
  const t = useT();
  const mine = ev.divisions.filter((d) => d.participant_id != null);
  const [divId, setDivId] = useState<number | null>(mine[0]?.id ?? null);
  const [tab, setTab] = useState<'stage' | 'result' | 'total' | null>(null);
  const [joinBusy, setJoinBusy] = useState<number | null>(null);
  const div = ev.divisions.find((d) => d.id === divId) ?? mine[0];
  // division_id нужен серверу только если участие в нескольких дивизионах
  const sendDiv = mine.length > 1 ? (div?.id ?? null) : null;

  return (
    <>
      <h1>{ev.name}</h1>
      <div className="sub">{ev.city} · {ev.date_start}</div>
      {mine.length === 0 && (
        <Card>
          <div style={{ marginBottom: 8 }}>{t('comp5.not_member')}</div>
          {ev.divisions.map((d) => (
            <button key={d.id} type="button" className="btn block" style={{ marginBottom: 6 }} disabled={joinBusy != null}
              onClick={() => { setJoinBusy(d.id); void compsApi.join(ev.id, d.id).then(reload, () => setJoinBusy(null)); }}>
              {t('comp5.join_div', { name: d.name })}
            </button>
          ))}
        </Card>
      )}
      {mine.length > 1 && (
        <label className="field"><span>{t('comp5.division')}</span>
          <select value={div?.id} onChange={(e) => setDivId(Number(e.target.value))}>
            {mine.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select></label>
      )}
      {(div ? [div] : ev.divisions).map((d) => (
        <div key={d.id}>
          <SecTitle>{d.name}{d.field_size ? ` · ${t('comp5.field_n', { n: d.field_size })}` : ''}</SecTitle>
          {d.stages.length === 0 ? <div className="sub">{t('comp5.no_stages')}</div> : d.stages.map((s) => (
            <Card key={s.id}>
              <div style={{ fontWeight: 600 }}>{s.idx}. {s.name}</div>
              {s.prescription && <div className="mut" style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{s.prescription}</div>}
              {(s.results ?? []).map((r, i) => (
                <div key={i} className="kv"><span>{r.athlete ?? t('comp5.athlete_me')}</span><b>{r.value ?? '—'} · {r.place ?? '—'}{r.field_size ? `/${r.field_size}` : ''}</b></div>
              ))}
            </Card>
          ))}
        </div>
      ))}
      {div && div.participant_id != null && (
        <>
          <SecTitle>{t('comp5.actions')}</SecTitle>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            {(['stage', 'result', 'total'] as const).map((k) => (
              <button key={k} type="button" className={`btn ${tab === k ? 'primary' : ''}`} style={{ flex: 1, padding: '0 6px' }} onClick={() => setTab(tab === k ? null : k)}>{t(`comp5.tab.${k}`)}</button>
            ))}
          </div>
          {tab === 'stage' && <StageAdd eventId={ev.id} divisionId={sendDiv} onDone={reload} />}
          {tab === 'result' && <ResultAdd eventId={ev.id} divisionId={sendDiv} stages={div.stages} onDone={reload} />}
          {tab === 'total' && <Total eventId={ev.id} onDone={reload} />}
          <div style={{ marginTop: 14 }}><FieldSize key={div.field_size ?? 'none'} d={div} onDone={reload} /></div>
          <Link className="menu-link" style={{ marginTop: 14 }} to={`/competitions/${ev.id}`}><span>📊 {t('comp5.report')}</span><span className="mut">›</span></Link>
        </>
      )}
    </>
  );
}

export function CompEventScreen() {
  const { id = '' } = useParams();
  const state = useFetch(() => compsApi.event(id), `comp-event:${id}`);
  return (
    <>
      <BackLink to="/comps" />
      <Async state={state}>{(ev) => <Body key={ev.divisions.map((d) => d.participant_id).join()} ev={ev} reload={state.reload} />}</Async>
    </>
  );
}
