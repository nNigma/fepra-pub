import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { endpoints } from '../api/endpoints';
import type { Session, WorkoutDetail, WorkoutRow } from '../api/types';
import { LlmBlock } from '../components/LlmBlock';
import { ReviewText } from '../components/Review';
import { HrLine, MuscleMap } from '../components/svgparts';
import { Async, Card, Narrative, SecTitle } from '../components/ui';
import { useT } from '../i18n';
import { delta, fmt, levelColors, mmss, scoreSec, tier } from '../lib/format';
import { useFetch } from '../lib/useFetch';
import { GymTodayCard } from './record/GymTodayCard';
import { RecentWorkouts, RecordFab } from './record/RecentWorkouts';

function shortResult(w: WorkoutRow, kg: string): string {
  const multi = !!w.score && w.score.includes('\n');
  return [w.scaling, w.load_kg ? `${w.load_kg} ${kg}` : null, !multi && w.score ? w.score : null, w.rpe ? `RPE ${w.rpe}` : null]
    .filter(Boolean)
    .join(' · ');
}

export function WorkoutsScreen() {
  const t = useT();
  const state = useFetch(() => endpoints.workouts(), 'workouts');
  const [filter, setFilter] = useState<string | null>(null);
  return (
    <>
      <h1>{t('workouts.title')}</h1>
      <RecordFab />
      <GymTodayCard />
      <RecentWorkouts />
      <Async state={state}>
        {(list) => {
          const now = new Date();
          const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
          const month = list.filter((w) => w.day?.slice(0, 7) === ym);
          const counts: Record<string, number> = {};
          list.forEach((w) => { if (w.sport) counts[w.sport] = (counts[w.sport] ?? 0) + 1; });
          const sports = Object.keys(counts);
          const prs = list.filter((w) => w.pr).length;
          const shown = filter ? list.filter((w) => w.sport === filter) : list;
          return (
            <>
              <div className="wstats">
                <span>{t('workouts.this_month', { n: month.length })}</span>
                {sports.map((s) => <span key={s}>{s} {counts[s]}</span>)}
                {prs > 0 && <span>PR {prs}</span>}
              </div>
              <div className="wfilters">
                {[null, ...sports].map((s) => (
                  <button key={s ?? 'all'} type="button" className={`wchip${filter === s ? ' wchip-on' : ''}`} onClick={() => setFilter(s)}>
                    {s ?? t('workouts.filter_all')}
                  </button>
                ))}
              </div>
              {shown.map((w) => (
                <Link key={`${w.day}-${w.sport}`} className="wrow" to={`/workouts/${w.day}`}>
                  <div className="wdot" style={{ background: tier(w.readiness)[0] }} />
                  <div className="wmain">
                    <div className="wt">{w.wod_name || w.sport}</div>
                    <div className="wsub">{w.day} · {w.sport}{shortResult(w, t('summary.kg')) ? ` · ${shortResult(w, t('summary.kg'))}` : ''}</div>
                  </div>
                  <div className="wchev">›</div>
                </Link>
              ))}
            </>
          );
        }}
      </Async>
    </>
  );
}

function ScoreBlock({ score }: { score: string }) {
  return (
    <div className="wodresult" style={{ fontSize: 13, lineHeight: 1.5 }}>
      {score.split('\n').filter((l) => l.trim()).map((raw, i) => {
        const line = raw.trim();
        const title = !/^\s/.test(raw) && line.endsWith(':');
        return title
          ? <div key={i} style={{ fontWeight: 600, margin: `${i === 0 ? 0 : 10}px 0 2px` }}>{line}</div>
          : <div key={i} style={{ opacity: 0.9, paddingLeft: 6 }}>{line}</div>;
      })}
    </div>
  );
}

function TeGauge({ label, val }: { label: string; val: number | null | undefined }) {
  if (val == null) return null;
  const pct = Math.min(Math.round((val / 5) * 100), 100);
  return (
    <div style={{ marginTop: 9 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 5 }}><span>{label}</span><span style={{ fontSize: 16, fontWeight: 600 }}>{Math.round(val * 10) / 10}</span></div>
      <div style={{ position: 'relative', display: 'flex', gap: 2, height: 8 }}>
        <div style={{ flex: 1, background: 'var(--mut)', opacity: 0.45, borderRadius: '4px 0 0 4px' }} />
        <div style={{ flex: 1, background: 'var(--mut)', opacity: 0.7 }} />
        <div style={{ flex: 1, background: '#378ADD' }} />
        <div style={{ flex: 1, background: '#4aaa99' }} />
        <div style={{ flex: 1, background: 'var(--amber)' }} />
        <div style={{ flex: 0.5, background: 'var(--red)', borderRadius: '0 4px 4px 0' }} />
        <div style={{ position: 'absolute', left: `${pct}%`, top: -3, width: 14, height: 14, borderRadius: '50%', background: '#378ADD', border: '2px solid var(--card)', transform: 'translateX(-50%)' }} />
      </div>
    </div>
  );
}

function HistLine({ s, prior }: { s: Session; prior?: WorkoutDetail['history'][string] }) {
  const t = useT();
  if (!prior || prior.length === 0) return <div className="hist">{t('workout.first_time')}</div>;
  const last = prior[prior.length - 1];
  const bits = [t('workout.last_time', { day: last.day })];
  if (s.load_kg != null && last.load_kg != null) {
    const d = Math.round((s.load_kg - last.load_kg) * 10) / 10;
    bits.push(t('workout.weight_change', { from: last.load_kg, to: s.load_kg, delta: (d >= 0 ? '+' : '') + d }));
  }
  const cs = scoreSec(s.score), ls = scoreSec(last.score);
  if (cs != null && ls != null) {
    const d = cs - ls;
    bits.push(t('workout.time_change', { from: last.score, to: s.score, delta: (d >= 0 ? '+' : '') + d }));
  }
  return <div className="hist">{bits.join(' · ')} · {t('workout.total_such', { n: prior.length + 1 })}</div>;
}

function SessionCard({ s, rep }: { s: Session; rep: WorkoutDetail }) {
  const t = useT();
  const ex = s.extra ?? {};
  const kg = t('summary.kg');
  const stats = [
    s.duration_min ? `${fmt(s.duration_min)} ${t('common.min')}` : null,
    s.avg_hr ? t('workout.stat_hr', { avg: s.avg_hr, max: s.max_hr || '—' }) : null,
    s.calories ? t('workout.stat_cal', { v: s.calories }) : null,
    t('workout.stat_trimp', { v: rep.trimp }),
  ].filter(Boolean).join(' · ');
  const chip = [s.scaling, s.load_kg ? `${s.load_kg} ${kg}` : null, s.rpe ? `RPE ${s.rpe}` : null].filter(Boolean).join(' · ');
  const multi = !!s.score && s.score.includes('\n');
  let result;
  if (multi) result = <>{chip && <div className="reschip">{chip}</div>}<ScoreBlock score={s.score!} /></>;
  else {
    const one = [chip, s.score].filter(Boolean).join(' · ');
    result = one ? <div className="reschip">{one}</div> : <div className="hist">{t('workout.result_missing')}</div>;
  }
  const paceFmt = (p: number) => `${Math.floor(p / 60)}:${String(Math.round(p % 60)).padStart(2, '0')}`;
  const endurance: { v: string; l: string }[] = [];
  if (s.distance_km != null) endurance.push({ v: `${s.distance_km} ${t('workout.km')}`, l: t('workout.distance') });
  if (s.avg_pace_s_per_km != null) endurance.push({ v: `${paceFmt(s.avg_pace_s_per_km)} ${t('workout.per_km')}`, l: t('workout.pace') });
  if (s.avg_power_w != null) endurance.push({ v: `${s.avg_power_w} ${t('workout.watt')}`, l: t('workout.power') });
  if (s.elevation_gain_m != null) endurance.push({ v: `${s.elevation_gain_m} ${t('workout.m')}`, l: t('workout.elevation') });

  const cal: { v: string | number; l: string; hi?: boolean }[] = [];
  if (ex.active_cal != null) cal.push({ v: ex.active_cal, l: t('workout.tile_active_cal') });
  if (ex.resting_cal != null) cal.push({ v: ex.resting_cal, l: t('workout.tile_resting_cal') });
  if (ex.active_cal != null && ex.resting_cal != null) cal.push({ v: ex.active_cal + ex.resting_cal, l: t('workout.tile_total_cal') });
  if (ex.sweat_loss_ml != null) cal.push({ v: ex.sweat_loss_ml, l: t('workout.tile_sweat') });
  if (ex.intensity_min != null) {
    const im = ex.intensity_min;
    const v = Array.isArray(im) ? `${im[0] || 0}${t('workout.intensity_mod')}${im[1] || 0}${t('workout.intensity_int')}`
      : im && typeof im === 'object' ? `${im.moderate || 0} + ${im.vigorous || 0}` : String(im);
    cal.push({ v, l: t('workout.tile_intensity') });
  }
  if (ex.recovery_h != null) cal.push({ v: ex.recovery_h + t('workout.tile_recovery_h'), l: t('workout.tile_recovery'), hi: true });
  const zones = s.zones && s.zones.length === 5 ? s.zones : null;
  const total = zones ? zones.reduce((a, b) => a + b, 0) || 1 : 1;
  const zc = ['var(--mut)', '#4aaa99', '#b8b84a', 'var(--amber)', 'var(--red)'];

  return (
    <Card>
      <div className="wt">{s.wod_name || s.sport}</div>
      <div className="wsub" style={{ margin: '4px 0 9px' }}>{stats}</div>
      {result}
      {endurance.length > 0 && (
        <div className="det-sec"><div className="det-hd">{t('workout.endurance_title')}</div>
          <div className="det-tiles">{endurance.map((x) => <div key={x.l} className="det-tile"><div className="det-tile-v">{x.v}</div><div className="det-tile-l">{x.l}</div></div>)}</div></div>
      )}
      {(ex.primary_benefit || ex.te_aerobic != null || ex.te_anaerobic != null) && (
        <div className="det-sec"><div className="det-hd">{t('workout.te_title')}</div>
          <div className="det-te">
            {ex.primary_benefit && (<><div className="te-title">{ex.primary_benefit}</div>
              <div className="wsub" style={{ margin: '1px 0 8px' }}>{t('workout.te_primary_benefit')}{ex.exercise_load != null ? t('workout.te_load', { v: ex.exercise_load }) : ''}</div></>)}
            <TeGauge label={t('workout.te_aerobic')} val={ex.te_aerobic} />
            <TeGauge label={t('workout.te_anaerobic')} val={ex.te_anaerobic} />
          </div></div>
      )}
      {s.hr_series && s.hr_series.length > 1 && (
        <div className="det-sec"><div className="det-hd">{t('workout.hr_title')}</div>
          <div style={{ background: 'var(--card)', border: '1px solid var(--bd)', borderRadius: 12, padding: '8px 6px 4px' }}>
            <HrLine series={s.hr_series} hrMax={rep.hr_max || s.max_hr || 184} />
            <div style={{ display: 'flex', gap: 9, justifyContent: 'center', fontSize: 10.5, opacity: 0.75, marginTop: 2 }}>
              {['Z1', 'Z2', 'Z3', 'Z4', 'Z5'].map((z, i) => (
                <span key={z}><span style={{ display: 'inline-block', width: 10, height: 3, background: ['var(--mut)', '#378ADD', '#4aaa99', 'var(--amber)', 'var(--red)'][i], verticalAlign: 'middle' }} /> {z}</span>
              ))}
            </div>
          </div></div>
      )}
      {zones && (
        <div className="det-sec"><div className="det-hd">{t('workout.zones_title')}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {zones.map((v, i) => {
              const pct = Math.round((v / total) * 100);
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 22, fontSize: 12, opacity: 0.8 }}>Z{i + 1}</span>
                  <div style={{ flex: 1, background: 'var(--bd)', borderRadius: 4, height: 11 }}><div style={{ width: `${pct}%`, height: '100%', background: zc[i], borderRadius: 4, minWidth: v ? 2 : 0 }} /></div>
                  <span style={{ width: 68, textAlign: 'right', fontSize: 12, opacity: 0.8 }}>{mmss(v)} · {pct}%</span>
                </div>
              );
            })}
          </div></div>
      )}
      {cal.length > 0 && (
        <div className="det-sec"><div className="det-hd">{t('workout.energy_title')}</div>
          <div className="det-tiles">{cal.map((x) => <div key={x.l} className={`det-tile${x.hi ? ' det-tile-hi' : ''}`}><div className="det-tile-v">{x.v}</div><div className="det-tile-l">{x.l}</div></div>)}</div></div>
      )}
      {(ex.respiration_avg != null || ex.respiration_max != null) && (
        <div className="det-sec"><div className="det-hd">{t('workout.resp_title')}</div>
          <div style={{ fontSize: 13, display: 'flex', gap: 14 }}>
            {ex.respiration_avg != null && <span>{t('workout.resp_avg')} <b>{ex.respiration_avg}</b></span>}
            {ex.respiration_max != null && <span>{t('workout.resp_max')} <b>{ex.respiration_max}</b></span>}
          </div></div>
      )}
      {s.narrative && s.narrative.length > 0 && (
        <div className="det-sec"><div className="det-hd">{t('workout.narrative_title')}</div><Narrative blocks={s.narrative} /></div>
      )}
      {s.wod_name && <HistLine s={s} prior={rep.history[s.wod_name]} />}
    </Card>
  );
}

function ClaudeBlock({ day, pro }: { day: string; pro: boolean }) {
  const t = useT();
  const state = useFetch(pro ? () => endpoints.claude(day) : null, `claude:${day}`);
  const text = state.data?.available ? state.data.text : null;
  return (
    <>
      {text && (
        <div className="clwrap">
          <div className="clhead">{t('claude.head')}</div>
          <ReviewText text={text} className="cltext" />
        </div>
      )}
      {!text && <LlmBlock kind="workout" refKey={day} pro={pro} />}
    </>
  );
}

export function WorkoutDetailScreen() {
  const t = useT();
  const nav = useNavigate();
  const { day = '' } = useParams();
  const state = useFetch(() => endpoints.workout(day), `workout:${day}`);
  const dayHeading = useMemo(() => day, [day]);
  return (
    <>
      <button type="button" className="back linkbtn" style={{ textDecoration: 'none', color: 'var(--mut)' }} onClick={() => nav('/workouts')}>{t('workout.back')}</button>
      <h1>{dayHeading}</h1>
      <Async state={state}>
        {(rep) => {
          const c = rep.condition;
          const hc = c ? levelColors(c.verdict.level) : ['var(--card)', 'var(--mut)'];
          return (
            <>
              {c && (
                <div className="hero" style={{ background: hc[0], color: hc[1] }}>
                  <div className="t">
                    {t('workout.approach')} · readiness {c.readiness ?? '—'}
                    {c.hrv_delta != null ? ` · HRV ${delta(c.hrv_delta)}` : ''}
                    {c.sleep_delta != null ? ` · ${t('metric.sleep.name')} ${delta(c.sleep_delta)}${t('workout.sleep_h')}` : ''}
                  </div>
                  <div className="h">{c.verdict.title}</div>
                  <div className="r">{c.verdict.reason}</div>
                </div>
              )}
              {rep.sessions.map((s, i) => <SessionCard key={i} s={s} rep={rep} />)}
              <RecentWorkouts day={rep.day} />
              {rep.muscles && (<><SecTitle>{t('workout.muscles_title')}</SecTitle><Card><MuscleMap m={rep.muscles} /></Card></>)}
              <ClaudeBlock day={rep.day} pro={!!rep.pro} />
            </>
          );
        }}
      </Async>
    </>
  );
}
