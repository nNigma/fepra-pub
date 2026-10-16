import { useMemo, useState } from 'react';
import { endpoints } from '../api/endpoints';
import type { Advice, Bench, NutritionWeek, Summary } from '../api/types';
import { ChartCanvas, MetricChart, OverlayChart, readinessChartConfig } from '../components/charts';
import { LlmBlock } from '../components/LlmBlock';
import { MuscleMap } from '../components/svgparts';
import { Async, Card, SecTitle } from '../components/ui';
import { useT } from '../i18n';
import { fmt, delta, deltaColor, levelColors, METRIC_IDS, tier, LEVEL_COLORS } from '../lib/format';
import { useFetch } from '../lib/useFetch';
import { GymTodayCard } from './record/GymTodayCard';
import { QuickWidgets } from './record/QuickWidgets';

function AdviceCard({ adv }: { adv: Advice }) {
  const t = useT();
  const c = levelColors(adv.level);
  const src = adv.source === 'claude' ? t('summary.advice_src_claude') : adv.source === 'gemini' ? t('summary.advice_src_gemini') : t('summary.advice_src_rules');
  const dot = adv.level === 'red' ? '🔴' : adv.level === 'amber' ? '🟡' : '🟢';
  const dt = adv.date ? `${adv.date.slice(8, 10)}.${adv.date.slice(5, 7)} · ` : '';
  return (
    <div className="advice" style={{ background: c[0] }}>
      <div className="advice-hd"><span>{t('summary.advice_hd')}</span><span className="advice-src">{dt}{src}</span></div>
      <div className="advice-ttl" style={{ color: c[1] }}>{dot} {adv.title}</div>
      <div className="advice-txt">{adv.text}</div>
      {adv.stale && <div className="advice-stale">{t('summary.advice_stale')}</div>}
    </div>
  );
}

function MetricTile({ id, label, b, note, hiBad, onTap }: {
  id: string; label: string; b?: Bench | null; note: string; hiBad: boolean; onTap: (id: string) => void;
}) {
  return (
    <div className="mc" role="button" tabIndex={0} onClick={() => onTap(id)} onKeyDown={(e) => e.key === 'Enter' && onTap(id)}>
      <div className="l">{label} ›</div>
      <div className="v">{b ? fmt(b.latest) : '—'} <span className="d" style={{ color: b ? deltaColor(b.delta, hiBad) : 'var(--mut)' }}>{b ? delta(b.delta) : ''}</span></div>
      <div className="n">{note}</div>
    </div>
  );
}

function MetricDetail({ id, data }: { id: string; data: Summary }) {
  const t = useT();
  const md = data.metrics?.[id];
  const dm = data.metrics ?? {};
  let chart;
  if (id === 'sleep_deep' || id === 'sleep_rem')
    chart = <OverlayChart a={dm.sleep_deep?.series ?? []} b={dm.sleep_rem?.series ?? []} labA={t('metric.sleep_deep.name')} labB={t('metric.sleep_rem.name')} baseA={dm.sleep_deep?.base} baseB={dm.sleep_rem?.base} />;
  else if (md) chart = <MetricChart series={md.series} base={md.base} dir={md.dir} />;
  let extra = null;
  if (id === 'hrv' && data.hrv_status) {
    const key = `hrv.status.${String(data.hrv_status).toLowerCase()}`;
    const label = t(key);
    const col = ({ BALANCED: 'var(--green)', UNBALANCED: 'var(--amber)', LOW: 'var(--red)', POOR: 'var(--red)' } as Record<string, string>)[data.hrv_status] ?? 'var(--mut)';
    if (label !== key) extra = <div style={{ marginTop: 8, fontSize: 13 }}>{t('metric.hrv.name')}: <b style={{ color: col }}>{label}</b></div>;
  }
  if (id === 'sleep' && (data.sleep_deep_h != null || data.sleep_rem_h != null)) {
    extra = (
      <div style={{ marginTop: 8, fontSize: 13 }}>
        {data.sleep_deep_h != null && <>{t('sleep.deep')} <b>{data.sleep_deep_h}</b> {t('common.h')}</>}
        {data.sleep_deep_h != null && data.sleep_rem_h != null && ' · '}
        {data.sleep_rem_h != null && <>{t('sleep.rem')} <b>{data.sleep_rem_h}</b> {t('common.h')}</>}
      </div>
    );
  }
  return (
    <div className="mdetail" data-testid="metric-detail">
      <div className="mdetail-hd">{t(`metric.${id}.name`)}{md?.base != null ? t('mdetail.bench', { base: md.base }) : ''}</div>
      <div className="mdetail-desc">{t(`metric.${id}.desc`)}</div>
      {extra}{chart}
      <div className="mdetail-hint">{t('mdetail.hint')}</div>
    </div>
  );
}

function NutrWeek({ nw }: { nw: NutritionWeek }) {
  const t = useT();
  const [open, setOpen] = useState<string | null>(null);
  const labels: Record<string, string> = {
    kcal: t('nut.kcal'), protein_g: t('nut.protein'), fat_g: t('nut.fat'), carb_g: t('nut.carb'), fiber_g: t('nut.m_fiber'),
    sugar_g: t('nut.m_sugar'), sodium_mg: t('nut.m_sodium'), iron_mg: t('nut.m_iron'), calcium_mg: t('nut.m_calcium'),
    magnesium_mg: t('nut.m_magnesium'), potassium_mg: t('nut.m_potassium'),
  };
  const k = nw.kcal ?? {};
  const clsC: Record<string, string> = { green: 'var(--green)', amber: 'var(--amber)', red: 'var(--red)' };
  const dTxt = k.delta == null ? '' : k.cls === 'green' ? t('nutw.on_target') : k.delta < 0 ? t('nutw.under', { v: -k.delta }) : t('nutw.over', { v: k.delta });
  const toggle = (id: string) => setOpen((o) => (o === id ? null : id));
  const macro = (id: string, label: string, color: string) => {
    const m = nw.metrics?.[id];
    if (!m) return null;
    const pct = m.target_week ? Math.min(100, Math.round((m.sum / m.target_week) * 100)) : 0;
    return (
      <div key={id} role="button" tabIndex={0} onClick={() => toggle(id)} style={{ flex: 1, background: 'rgba(128,128,128,.08)', borderRadius: 10, padding: 8, cursor: 'pointer' }}>
        <div style={{ fontSize: 11, color: 'var(--mut)' }}>{label} ›</div>
        <div style={{ fontWeight: 700 }}>{Math.round(m.sum)}{m.target_week ? `/${m.target_week}` : ''} {t('nut.g')}</div>
        {m.target_week ? <div style={{ height: 4, background: 'rgba(128,128,128,.25)', borderRadius: 2, marginTop: 4 }}><div style={{ width: `${pct}%`, height: 4, background: color, borderRadius: 2 }} /></div> : null}
        <div style={{ fontSize: 11, color: 'var(--mut)', marginTop: 4 }}>{t('nutw.avg_day', { v: `${Math.round(m.avg)} ${t('nut.g')}` })}</div>
      </div>
    );
  };
  const micro: [string, string][] = [['fiber_g', t('nut.g')], ['sugar_g', t('nut.g')], ['sodium_mg', t('nut.mg')], ['iron_mg', t('nut.mg')], ['calcium_mg', t('nut.mg')], ['magnesium_mg', t('nut.mg')], ['potassium_mg', t('nut.mg')]];
  const list = (title: string, items?: string[]) =>
    items && items.length ? (
      <>
        <SecTitle>{title}</SecTitle>
        <Card>{items.map((x, i) => <div key={i} style={{ fontSize: 13, margin: '3px 0' }}>• {x}</div>)}</Card>
      </>
    ) : null;
  const opened = open ? nw.metrics?.[open] : null;
  return (
    <>
      <h2>{t('nutw.title')}</h2>
      <div className="sub">{t('nutw.sub', { a: `${nw.range[0].slice(8)}.${nw.range[0].slice(5, 7)}`, b: `${nw.range[1].slice(8)}.${nw.range[1].slice(5, 7)}`, n: nw.days_recorded })}</div>
      <Card>
        <div role="button" tabIndex={0} style={{ cursor: 'pointer' }} onClick={() => toggle('kcal')}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <div><span style={{ fontSize: 26, fontWeight: 700 }}>{k.sum ?? '—'}</span><span style={{ fontSize: 12, opacity: 0.6, marginLeft: 4 }}>{k.target_week ? `/ ${k.target_week} ` : ''}{t('nut.kcal')} ›</span></div>
            <div style={{ fontSize: 13, fontWeight: 600, color: clsC[k.cls ?? ''] ?? 'var(--mut)' }}>{dTxt}</div>
          </div>
          <div style={{ fontSize: 12, color: 'var(--mut)', marginTop: 3 }}>{t('nutw.avg_day', { v: `${k.avg} ${t('nut.kcal')}` })}</div>
        </div>
      </Card>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        {macro('protein_g', t('nut.protein'), '#e5484d')}{macro('fat_g', t('nut.fat'), '#b088f9')}{macro('carb_g', t('nut.carb'), '#4c8dff')}
      </div>
      {nw.protein_per_kg_avg != null && (
        <div style={{ fontSize: 12, color: nw.protein_ok ? 'var(--green)' : 'var(--amber)', margin: '-2px 0 8px' }}>{t('nutw.protein_per_kg', { v: nw.protein_per_kg_avg })}</div>
      )}
      {open && (
        <div className="mdetail">
          <div className="mdetail-hd">{labels[open] ?? open}{opened?.base != null ? ` · ${t('nutw.bench', { v: opened.base })}` : ''}</div>
          <MetricChart series={opened?.series ?? []} base={opened?.base} dir={opened?.dir} sparse />
          <div className="mdetail-hint">{t('mdetail.hint')}</div>
        </div>
      )}
      <div className="det-tiles" style={{ gridTemplateColumns: 'repeat(2,1fr)' }}>
        {micro.map(([id, unit]) => {
          const m = nw.metrics?.[id];
          if (!m) return null;
          return (
            <div key={id} className="det-tile" role="button" tabIndex={0} style={{ cursor: 'pointer' }} onClick={() => toggle(id)}>
              <div className="det-tile-v" style={m.flag ? { color: 'var(--red)' } : undefined}>{Math.round(m.sum)}/{m.dir === 'high_bad' ? '≤' : ''}{m.target_week}</div>
              <div className="det-tile-l">{labels[id]}, {unit} · {t('nutw.avg_day', { v: Math.round(m.avg) })} ›</div>
            </div>
          );
        })}
      </div>
      {list(t('nutw.conclusions_hd'), nw.conclusions)}
      {list(t('nut.advice_hd'), nw.advice)}
    </>
  );
}

function Calendar({ rows }: { rows: Summary['series'] }) {
  const t = useT();
  const days = [t('day.mon'), t('day.tue'), t('day.wed'), t('day.thu'), t('day.fri'), t('day.sat'), t('day.sun')];
  const pad = (new Date(rows[0][0]).getDay() + 6) % 7;
  return (
    <div className="cal">
      {days.map((d) => <div key={d} className="hd">{d}</div>)}
      {Array.from({ length: pad }, (_, i) => <div key={`p${i}`} />)}
      {rows.map((r) => {
        const [bg, fg] = tier(r[1]);
        const title = t('summary.cal_tooltip', { day: r[0], rdy: r[1], sleep: r[2] }) + (r[4] ? t('summary.cal_tooltip_load', { load: r[3] }) : t('summary.cal_tooltip_rest'));
        return (
          <div key={r[0]} className="cell" title={title} style={{ background: bg, color: fg }}>
            <span className="dd">{+r[0].slice(8)}</span>{r[4] ? <span className="bb" /> : null}
          </div>
        );
      })}
    </div>
  );
}

function SummaryBody({ data, reload }: { data: Summary; reload: () => void }) {
  const t = useT();
  const [open, setOpen] = useState<string | null>(null);
  const m = data.m;
  const st = data.state ?? {};
  const rdy = st.readiness ?? {};
  const risk = st.risk ?? {};
  const mc = data.microcycle ?? {};
  const toggle = (id: string) => setOpen((o) => (o === id ? null : id));

  const metricCard = (id: string, hiBad: boolean, unit: string) => {
    const md = data.metrics?.[id];
    if (!md?.series?.length) return null;
    const latest = md.series[md.series.length - 1][1];
    const dl = md.base != null ? Math.round((latest - md.base) * 10) / 10 : null;
    return <MetricTile key={id} id={id} label={t(`metric.${id}.name`)} b={{ latest, delta: dl }} note={unit} hiBad={hiBad} onTap={toggle} />;
  };

  const rdyC = tier(rdy.value);
  const hero = rdy.items?.length ? (
    <div className="hero" style={{ background: rdyC[0], color: rdyC[1] }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div className="t">{t('summary.readiness')}</div>
        {rdy.base != null && <div style={{ fontSize: 11, opacity: 0.6 }}>{t('summary.your_base', { base: Math.round(rdy.base) })}</div>}
      </div>
      <div className="h">{rdy.value ?? '—'} <span style={{ fontSize: 14, fontWeight: 400, opacity: 0.7 }}>{rdy.delta != null ? (rdy.delta >= 0 ? t('summary.above_base') : t('summary.below_base')) : ''}</span></div>
      <div className="rdy-items">
        {rdy.items.map((it) => {
          const pos = it.weight >= 0;
          const col = pos ? 'var(--green)' : 'var(--red)';
          return (
            <div className="rdy-row" key={it.name}>
              <span className="rdy-name">{it.name}</span>
              <div className="rdy-bar"><div className="rdy-fill" style={{ background: col, [pos ? 'left' : 'right']: '50%', width: `${Math.min(Math.abs(it.weight) * 3, 45)}%` }} /></div>
              <span className="rdy-w" style={{ color: col }}>{it.weight >= 0 ? '+' : ''}{it.weight}</span>
            </div>
          );
        })}
      </div>
    </div>
  ) : (
    (() => {
      const vd = data.verdict;
      const c = levelColors(vd.level);
      const label = vd.source === 'self' ? t('summary.self_readiness', { today: data.today }) : t('summary.readiness_dated', { today: data.today });
      return (
        <div className="hero" style={{ background: c[0], color: c[1] }}>
          <div className="t">{label}</div><div className="h">{vd.title}</div><div className="r">{vd.reason}</div>
        </div>
      );
    })()
  );

  const riskLv = risk.level ?? 'green';
  const riskC = levelColors(riskLv);
  const riskEmpty = riskLv === 'green' && (!risk.title || risk.title === '—');
  const sigEntries = Object.entries(st.signals ?? {});
  const wser = data.metrics?.weight?.series ?? [];
  const fo = st.form ?? {};
  const wt = data.watch_tuning;
  const mcDays = mc.days ?? [];
  const maxLoad = Math.max(...mcDays.map((d) => d.load ?? 0), 1);
  const dayLabels = [t('day.mon'), t('day.tue'), t('day.wed'), t('day.thu'), t('day.fri'), t('day.sat'), t('day.sun')];
  const acwr = m.acwr;
  const chartCfg = useMemo(() => readinessChartConfig(data.series.slice(-30)), [data.series]);
  const calRows = data.series.slice(-31);

  return (
    <>
      <h1>{t('summary.title')}</h1>
      <div className="sub">{t('summary.on_date', { day: data.last_data_day || data.range[1] || '—', hrmax: data.hr_max })}</div>
      {hero}
      <GymTodayCard />
      <QuickWidgets />
      {data.advice && <AdviceCard adv={data.advice} />}
      <div className="grid">
        <MetricTile id="sleep" label={t('metric.sleep.name')} b={m.sleep} note={t('summary.sleep_note')} hiBad={false} onTap={toggle} />
        <MetricTile id="hrv" label={t('metric.hrv.name')} b={m.hrv} note={t('summary.hrv_note')} hiBad={false} onTap={toggle} />
        <MetricTile id="rhr" label={t('metric.rhr.name')} b={m.rhr} note={t('summary.rhr_note')} hiBad onTap={toggle} />
        <MetricTile id="vo2max" label={t('metric.vo2max.name')} b={m.vo2max} note={t('summary.vo2max_note')} hiBad={false} onTap={toggle} />
        {metricCard('spo2', false, t('metric.spo2.note'))}
        {metricCard('respiration', true, t('metric.respiration.note'))}
        {metricCard('sleep_deep', false, t('metric.sleep_deep.note'))}
        {metricCard('sleep_rem', false, t('metric.sleep_rem.note'))}
      </div>
      {open && <MetricDetail id={open} data={data} />}

      <Lens label={t('summary.lens_body')} color="var(--green)" />
      <Card style={{ borderLeft: `3px solid ${riskC[1]}` }}>
        <div style={{ fontWeight: 700, color: riskC[1] }}>{riskEmpty ? t('summary.data_collecting') : risk.title || '—'}</div>
        {risk.drivers?.length ? <div style={{ fontSize: 12.5, marginTop: 4, opacity: 0.85 }}>{risk.drivers.join(' · ')}</div> : null}
      </Card>
      {sigEntries.length > 0 && (
        <Card style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {sigEntries.map(([id, sg]) => {
            const c = LEVEL_COLORS[sg.cls ?? 'green'] ?? LEVEL_COLORS.green;
            return (
              <div key={id} role="button" tabIndex={0} style={{ cursor: 'pointer' }} onClick={() => toggle(id)}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                  <span>{sg.label} › <b>{sg.value ?? '—'}</b></span><span style={{ color: c[1] }}>{sg.base ?? ''}</span>
                </div>
                {sg.base && <div className="sig-bar"><div className="sig-fill" style={{ background: `${c[1]}22` }} /><div className="sig-cur" style={{ background: c[1] }} /></div>}
              </div>
            );
          })}
        </Card>
      )}
      <Card>
        <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.5px', opacity: 0.55, marginBottom: 8 }}>{t('summary.form_direction')}</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div><span style={{ fontWeight: 700 }}>{fo.vo2max ?? '—'}</span><span style={{ fontSize: 11, opacity: 0.55, marginLeft: 4 }}>VO₂max</span></div>
          <div style={{ fontSize: 13, color: 'var(--mut)' }}>{fo.status || '—'}</div>
          <div><span style={{ fontWeight: 700 }}>{fo.weight ?? '—'}</span><span style={{ fontSize: 11, opacity: 0.55, marginLeft: 4 }}>{t('summary.kg')}</span></div>
        </div>
        {wser.length > 1 && (
          <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--bd)' }}>
            <div style={{ fontSize: 10.5, opacity: 0.5, marginBottom: 2 }}>{t('summary.weight_chart')}</div>
            <MetricChart series={wser} dir="low_bad" sparse />
          </div>
        )}
      </Card>
      {wt?.watch && (() => {
        const items = wt.items ?? [];
        const off = items.filter((i) => i.state === 'off');
        const unsup = items.filter((i) => i.state === 'unsupported');
        const ok = items.filter((i) => i.state === 'ok').length;
        return (
          <Card>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.5px', opacity: 0.55, marginBottom: 6 }}>{t('watch.title')}</div>
            <div style={{ fontSize: 12.5, color: 'var(--mut)' }}>⌚ {wt.watch}{wt.others?.length ? ` + ${wt.others.join(', ')}` : ''} · {t('watch.ok_count', { ok, total: items.length })}</div>
            {off.map((i) => (
              <div key={i.id} style={{ marginTop: 9, paddingTop: 8, borderTop: '1px solid var(--bd)' }}>
                <div style={{ fontWeight: 600 }}>⚠️ {t(`watch.${i.id}.name`)}</div>
                <div style={{ fontSize: 12.5, opacity: 0.85, marginTop: 2 }}>{t(`watch.${i.id}.gain`)}</div>
                <div style={{ fontSize: 12, color: 'var(--amber)', marginTop: 3 }}>{t(`watch.${i.id}.how`)}</div>
              </div>
            ))}
            {off.length === 0 && <div style={{ fontSize: 12.5, color: 'var(--green)', marginTop: 6 }}>{t('watch.all_ok')}</div>}
            {unsup.length > 0 && <div style={{ fontSize: 11, color: 'var(--mut)', marginTop: 8 }}>{t('watch.unsupported')}: {unsup.map((i) => t(`watch.${i.id}.name`)).join(', ')}</div>}
          </Card>
        );
      })()}

      <Lens label={t('summary.lens_load')} color="var(--amber)" />
      <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.5px', opacity: 0.55, margin: '0 0 8px' }}>{t('summary.microcycle_week')}</div>
      {mcDays.length ? (
        <Card>
          <div style={{ height: 64, display: 'flex', alignItems: 'flex-end', gap: 5, marginBottom: 5 }}>
            {mcDays.map((d, i) => {
              const h = d.load ? Math.round((d.load / maxLoad) * 100) : 0;
              return (
                <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
                  <div style={{ width: '65%', height: `${Math.max(h, 4)}%`, background: h === 0 ? 'var(--bd)' : 'var(--amber)', borderRadius: 3 }} />
                </div>
              );
            })}
          </div>
          <div style={{ display: 'flex', gap: 5, fontSize: 10, opacity: 0.55, textAlign: 'center' }}>{mcDays.map((d, i) => <span key={i} style={{ flex: 1 }}>{d.label || dayLabels[i] || ''}</span>)}</div>
          <div style={{ display: 'flex', gap: 5, fontSize: 9.5, opacity: 0.4, textAlign: 'center', marginTop: 2 }}>{mcDays.map((d, i) => <span key={i} style={{ flex: 1 }}>{d.readiness ?? '—'}</span>)}</div>
          {(mc.max_streak ?? 0) >= 3 && <div style={{ fontSize: 12.5, marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--bd)', color: 'var(--amber)' }}>{t('summary.microcycle_streak')}</div>}
        </Card>
      ) : (
        <Card style={{ color: 'var(--mut)', fontSize: 13 }}>{t('summary.microcycle_soon')}</Card>
      )}
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
          <span>{t('summary.acwr_label')} <b>{fmt(acwr)}</b></span>
          <span style={{ color: acwr == null ? 'var(--mut)' : acwr >= 0.8 && acwr <= 1.3 ? 'var(--green)' : acwr > 1.3 ? 'var(--red)' : 'var(--amber)' }}>
            {acwr == null ? '—' : acwr >= 0.8 && acwr <= 1.3 ? t('summary.acwr_in_zone') : acwr > 1.3 ? t('summary.acwr_overload') : t('summary.acwr_underload')}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--mut)' }}>
          <span>{t('summary.acute', { v: fmt(m.acute7) })}</span><span>{t('summary.chronic', { v: fmt(m.chronic28) })}</span>
        </div>
        <div style={{ display: 'flex', gap: 18, marginTop: 9, fontSize: 12 }}><span>Monotony <b>{fmt(m.monotony)}</b></span><span>Strain <b>{fmt(m.strain)}</b></span></div>
      </Card>
      {data.muscles_week && (
        <Card>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.5px', opacity: 0.55, marginBottom: 8 }}>{t('summary.muscles_title')}</div>
          <MuscleMap m={data.muscles_week} />
          {data.muscles_week.idle?.length ? (
            <div style={{ fontSize: 12, marginTop: 9, paddingTop: 8, borderTop: '1px solid var(--bd)' }}>
              <span style={{ color: 'var(--mut)' }}>{t('summary.muscles_idle')}</span>{' '}
              {data.muscles_week.idle.map((g) => <span key={g} className="sp">{t(`muscle.${g}`)}</span>)}
            </div>
          ) : null}
        </Card>
      )}

      {calRows.length > 0 && (
        <>
          <h2>{t('summary.cal_title')}</h2>
          <div className="leg">
            <span><span className="sw" style={{ background: 'var(--greenb)' }} />{t('summary.leg_ready')}</span>
            <span><span className="sw" style={{ background: 'var(--amberb)' }} />{t('summary.leg_mid')}</span>
            <span><span className="sw" style={{ background: 'var(--redb)' }} />{t('summary.leg_tired')}</span>
            <span>{t('summary.leg_dot')}</span>
          </div>
          <Calendar rows={calRows} />
          <h2>{t('summary.rdy_load_title')}</h2>
          <div className="leg">
            <span><span className="sw" style={{ background: '#1D9E75', height: 3, borderRadius: 0 }} />{t('summary.leg_readiness')}</span>
            <span><span className="sw" style={{ background: '#888780' }} />{t('summary.leg_load')}</span>
          </div>
          <ChartCanvas config={chartCfg} height={240} />
        </>
      )}
      <h2>{t('summary.sports_title')}</h2>
      <Card>{data.sports.map((s) => <span key={s[0]} className="sp">{s[0]} · {s[1]}</span>)}</Card>

      {data.nutrition_week && <NutrWeek nw={data.nutrition_week} />}
      {data.narrative30?.length ? (
        <>
          <h2>{t('summary.narrative_30d')}</h2>
          {data.narrative30.map((b, i) => <div key={i} className="mdsec"><div className="mdh">{b.title}</div><div>{b.body}</div></div>)}
        </>
      ) : null}
      <LlmBlock kind="summary" refKey="30d" pro={!!data.pro} onDone={reload} />
      <details className="methelp">
        <summary>{t('methelp.title')}</summary>
        {METRIC_IDS.map((id) => <div key={id} className="methelp-it"><b>{t(`metric.${id}.name`)}</b> - {t(`metric.${id}.desc`)}</div>)}
      </details>
    </>
  );
}

function Lens({ label, color }: { label: string; color: string }) {
  return (
    <div className="lens-hd">
      <span style={{ color }}>{label}</span>
      <div className="lens-line" style={{ background: `color-mix(in srgb, ${color} 14%, transparent)` }} />
    </div>
  );
}

export function SummaryScreen() {
  const state = useFetch(() => endpoints.summary(), 'summary');
  return <Async state={state}>{(d) => <SummaryBody data={d} reload={state.reload} />}</Async>;
}
