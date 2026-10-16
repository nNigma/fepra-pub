import { useMemo } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { endpoints } from '../api/endpoints';
import type { CompetitionDetail, Competitions } from '../api/types';
import { ChartCanvas, placeChartConfig } from '../components/charts';
import { LlmBlock } from '../components/LlmBlock';
import { Radar } from '../components/svgparts';
import { Async, Card, Narrative } from '../components/ui';
import { useT } from '../i18n';
import { useFetch } from '../lib/useFetch';

function Body({ data }: { data: Competitions }) {
  const t = useT();
  const rows = useMemo(() => data.totals ?? [], [data.totals]);
  const bw = data.best_worst ?? {};
  const cfg = useMemo(() => placeChartConfig(rows.map((r) => r.date), rows.map((r) => r.final_place)), [rows]);
  if (data.starts === 0) return <div className="sub">{t('comp.none')}</div>;
  const list = (items: typeof bw.best, color: string) =>
    (items ?? []).map((s) => (
      <div key={s.name} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0' }}>
        <span>{s.name}</span><span style={{ color }}>{s.result?.place ?? '—'}/{s.field}</span>
      </div>
    ));
  return (
    <>
      <div className="grid">
        <div className="mc"><div className="l">{t('comp.starts')}</div><div className="v">{data.starts}</div></div>
        <div className="mc"><div className="l">{t('comp.best_place')}</div><div className="v">{data.best_place ?? '—'}</div></div>
      </div>
      <h2>{t('comp.place_by_start')}</h2>
      <ChartCanvas config={cfg} height={220} />
      {data.radars?.length ? (<><h2>{t('comp.compare_title')}</h2><Radar sets={data.radars} /></>) : null}
      {(bw.best?.length || bw.worst?.length) ? (
        <>
          <h2>{t('comp.career_wods')}</h2>
          {bw.best?.length ? <Card style={{ background: 'var(--greenb)', border: 0 }}><div style={{ color: 'var(--green)', fontSize: 11, fontWeight: 700, marginBottom: 6 }}>{t('comp.best')}</div>{list(bw.best, 'var(--green)')}</Card> : null}
          {bw.worst?.length ? <Card style={{ background: 'var(--redb)', border: 0 }}><div style={{ color: 'var(--red)', fontSize: 11, fontWeight: 700, marginBottom: 6 }}>{t('comp.worst')}</div>{list(bw.worst, 'var(--red)')}</Card> : null}
        </>
      ) : null}
      {data.narrative?.length ? (<><h2>{t('comp.conclusions')}</h2><Narrative blocks={data.narrative} /></>) : null}
      <h2>{t('comp.starts_title')}</h2>
      {rows.map((r) => (
        <Link key={r.id} className="wrow" to={`/competitions/${r.id}`}>
          <div className="wmain">
            <div className="wt">{r.name}</div>
            <div className="wsub">{r.date} · {t('comp.place_of_field', { place: r.final_place, field: r.field })}</div>
          </div>
          <div className="wchev">›</div>
        </Link>
      ))}
      <LlmBlock kind="competitions" refKey="total" pro={!!data.pro} />
    </>
  );
}

export function CompetitionsScreen() {
  const t = useT();
  const state = useFetch(() => endpoints.competitions(), 'competitions');
  return (
    <>
      <h1>{t('comp.title')}</h1>
      <Link className="menu-link" to="/comps"><span>📝 {t('comp5.title')}</span><span className="mut">›</span></Link>
      <Async state={state}>{(d) => <Body data={d} />}</Async>
    </>
  );
}

function Detail({ rep }: { rep: CompetitionDetail }) {
  const t = useT();
  const dyn = useMemo(() => rep.dynamics ?? [], [rep.dynamics]);
  const tbl = rep.table ?? [];
  const sc = rep.scenario ?? {};
  const pctCol = (p: number) => (p >= 66 ? 'var(--green)' : p >= 40 ? 'var(--amber)' : 'var(--red)');
  const cfg = useMemo(() => placeChartConfig(dyn.map((d) => `${t('compd.round_prefix')}${d.idx}`), dyn.map((d) => d.place)), [dyn, t]);
  return (
    <>
      <h1>{rep.name}</h1>
      <div className="sub">{rep.city} · {rep.date} · {t('compd.division', { v: rep.division })}</div>
      <div className="grid" style={{ marginTop: 10 }}>
        <div className="mc"><div className="l">{t('compd.place')}</div><div className="v">{rep.final_place ?? '—'}<span style={{ fontSize: 13, opacity: 0.5 }}>/{rep.field}</span></div></div>
        <div className="mc"><div className="l">{t('compd.points')}</div><div className="v">{rep.total_points ?? '—'}</div></div>
      </div>
      {dyn.length > 0 && (<><h2>{t('compd.dynamics')}</h2><ChartCanvas config={cfg} height={200} /></>)}
      <h2>{t('compd.profile')}</h2>
      <Radar sets={[{ name: '', grades: rep.radar ?? {} }]} />
      <h2>{t('compd.stages')}</h2>
      <div style={{ fontSize: 13 }}>
        <div style={{ display: 'flex', padding: '7px 8px', background: 'var(--card)', borderRadius: '8px 8px 0 0', opacity: 0.55, fontSize: 11 }}>
          <span style={{ flex: 2 }}>{t('compd.wod_col')}</span><span style={{ width: 38, textAlign: 'center' }}>{t('compd.place_col')}</span><span style={{ width: 48, textAlign: 'right' }}>{t('compd.pct_col')}</span>
        </div>
        {tbl.map((s, i) => (
          <div key={i} style={{ display: 'flex', padding: 8, borderLeft: `3px solid ${pctCol(s.percentile)}`, background: i % 2 ? 'rgba(128,128,128,.05)' : undefined }}>
            <span style={{ flex: 2 }}>{s.name}</span>
            <span style={{ width: 38, textAlign: 'center' }}>{s.place ?? '—'}</span>
            <span style={{ width: 48, textAlign: 'right', color: pctCol(s.percentile) }}>{s.percentile}%</span>
          </div>
        ))}
      </div>
      {rep.narrative?.length ? (<><h2>{t('compd.narrative')}</h2>{rep.narrative.map((b, i) => <Card key={i}><div style={{ fontWeight: 700, marginBottom: 5 }}>{b.title}</div><div style={{ fontSize: 13 }}>{b.body}</div></Card>)}</>) : null}
      {(sc.gain ?? 0) > 0 && (<><h2>{t('compd.cost_title')}</h2><Card style={{ borderLeft: '3px solid #6f9bd9' }}>{t('compd.cost_text', { gain: sc.gain, place: sc.target_place })}</Card></>)}
    </>
  );
}

export function CompetitionDetailScreen() {
  const t = useT();
  const nav = useNavigate();
  const { id = '' } = useParams();
  const state = useFetch(() => endpoints.competition(id), `competition:${id}`);
  return (
    <>
      <button type="button" className="back linkbtn" style={{ textDecoration: 'none', color: 'var(--mut)' }} onClick={() => nav('/competitions')}>{t('compd.back')}</button>
      <Async state={state}>{(rep) => <Detail rep={rep} />}</Async>
    </>
  );
}
