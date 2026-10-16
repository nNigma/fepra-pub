import { endpoints } from '../api/endpoints';
import type { Discipline, GoalItem, Goals } from '../api/types';
import { Async } from '../components/ui';
import { useT } from '../i18n';
import { mmss } from '../lib/format';
import { useFetch } from '../lib/useFetch';
import { AddGoal, GoalActions, QuickPm } from './record/GoalsManage';

function Disc({ d }: { d: Discipline }) {
  const t = useT();
  if (!d.has_data)
    return (
      <div className="disc">
        <div className="nm"><b>{d.name}</b> <span className="mut">{t('goals.no_data')}</span></div>
      </div>
    );
  const val = d.unit === 'kg' ? t('goals.kg_1rm', { v: Math.round(d.value ?? 0) }) : d.unit === 'time' ? mmss(d.value) : t('goals.rounds', { v: d.value });
  return (
    <div className="disc">
      <div className="nm">
        <b>{d.name}</b> <span className="mut">· {val}</span>
        <div className="tierbar">{Array.from({ length: 5 }, (_, i) => <span key={i} className={`seg${d.idx != null && i <= d.idx ? ' on' : ''}`} />)}</div>
      </div>
      <div style={{ textAlign: 'right' }}>
        {d.level != null && <span className="pill">{d.level}</span>}
        {d.distance_text && <div className="mut" style={{ marginTop: 3 }}>{d.distance_text}</div>}
      </div>
    </div>
  );
}

function Goal({ g, reload }: { g: GoalItem; reload: () => void }) {
  const t = useT();
  const p = g.progress ?? {};
  const pct = p.pct ?? (p.done ? 100 : 0);
  return (
    <div className="goal">
      <div className="gtop"><span>{g.title}</span><span className="mut">{p.done ? t('goals.done') : p.text || ''}</span></div>
      <div className="bar"><i style={{ width: `${Math.min(pct, 100)}%` }} /></div>
      {g.id != null && <GoalActions id={g.id} onDone={reload} />}
    </div>
  );
}

function Body({ d, reload }: { d: Goals; reload: () => void }) {
  const t = useT();
  const ov = d.overall ?? {};
  return (
    <>
      {ov.level ? (
        <div className="ovr">
          <div className="ring" style={{ ['--p' as string]: Math.round((ov.progress ?? 0) * 100) }}><div>{ov.level}</div></div>
          <div>
            <div><b>{ov.level}</b> {t('goals.level_suffix')}</div>
            <div className="bar" style={{ margin: '5px 0 4px' }}><i style={{ width: `${Math.round((ov.progress ?? 0) * 100)}%` }} /></div>
            <div className="mut">{t('goals.assessed', { a: ov.assessed, t: ov.total })}</div>
          </div>
        </div>
      ) : (
        <div className="ovr"><div className="mut">{t('goals.assessed_prompt', { a: ov.assessed, t: ov.total })}</div></div>
      )}
      <div className="sec">{t('goals.my_goals')}</div>
      {d.goals?.length ? d.goals.map((g, i) => <Goal key={g.id ?? i} g={g} reload={reload} />) : <div className="mut" style={{ padding: '4px 2px' }}>{t('goals.none')}</div>}
      <AddGoal all={[...(d.lifts ?? []), ...(d.benchmarks ?? [])].filter((x) => x.id)} onChanged={reload} />
      <QuickPm lifts={(d.lifts ?? []).filter((x) => x.id)} benchmarks={(d.benchmarks ?? []).filter((x) => x.id)} onChanged={reload} />
      <div className="sec">{t('goals.lifts')}</div>
      {(d.lifts ?? []).map((x) => <Disc key={x.name} d={x} />)}
      <div className="sec">{t('goals.benchmarks')}</div>
      {(d.benchmarks ?? []).map((x) => <Disc key={x.name} d={x} />)}
      <div className="foot">{t('goals.source_note')}</div>
    </>
  );
}

export function GoalsScreen() {
  const t = useT();
  const state = useFetch(() => endpoints.goals(), 'goals');
  return (
    <>
      <h1>{t('goals.title')}</h1>
      <Async state={state}>{(d) => <Body d={d} reload={state.reload} />}</Async>
    </>
  );
}
