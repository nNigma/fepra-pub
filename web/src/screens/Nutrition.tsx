import { Link, useNavigate, useParams } from 'react-router-dom';
import { endpoints } from '../api/endpoints';
import type { NutritionDay } from '../api/types';
import { LlmBlock } from '../components/LlmBlock';
import { Async, Card, SecTitle } from '../components/ui';
import { useT } from '../i18n';
import { splitEmoji } from '../lib/format';
import { useFetch } from '../lib/useFetch';

export function NutritionScreen() {
  const t = useT();
  const state = useFetch(() => endpoints.nutritionDays(), 'nutrition-days');
  return (
    <>
      <h1>{t('nut.title')}</h1>
      <div className="sub">{t('nut.days_sub')}</div>
      <Link className="btn primary block" to="/meals" style={{ marginBottom: 10 }}>＋ {t('meal.add')}</Link>
      <Async state={state}>
        {(d) => {
          const w = d.weight_kg;
          return d.days?.length ? (
            <>
              {d.days.map((r) => {
                const ppk = w && r.protein_g ? Math.round((r.protein_g / w) * 100) / 100 : null;
                return (
                  <Link key={r.day} to={`/nutrition/${r.day}`} className="wrow">
                    <div className="wdot" style={{ background: ppk != null && ppk >= 1.6 ? 'var(--green)' : 'var(--amber)' }} />
                    <div className="wmain">
                      <div className="wt">{r.day} · {Math.round(r.kcal || 0)} {t('nut.kcal')}</div>
                      <div className="wsub">{t('nut.bju')}: {Math.round(r.protein_g || 0)} / {Math.round(r.fat_g || 0)} / {Math.round(r.carb_g || 0)} {t('nut.g')} · {r.meals} {t('nut.meals_n')}</div>
                    </div>
                    <span style={{ fontSize: 16, marginRight: 2 }}>{r.verdict ? splitEmoji(t(`q.day.${r.verdict}`)).emoji : ''}</span>
                    <div className="wchev">›</div>
                  </Link>
                );
              })}
            </>
          ) : (
            <Card style={{ color: 'var(--mut)', fontSize: 13 }}>{t('nut.no_meals')}</Card>
          );
        }}
      </Async>
      <div className="foot">{t('nut.hint')}</div>
    </>
  );
}

export const MICRO_T: Record<string, number> = { fiber_g: 30, sugar_g: 50, sodium_mg: 2300, iron_mg: 8, calcium_mg: 1000, magnesium_mg: 400, potassium_mg: 3500 };
export const MICRO_LIMIT = new Set(['sugar_g', 'sodium_mg']);

export function Tile({ label, v, unit }: { label: string; v: string | number; unit?: string }) {
  return <div className="det-tile"><div className="det-tile-v">{v}</div><div className="det-tile-l">{label}{unit ? `, ${unit}` : ''}</div></div>;
}

export function MBar({ label, val, tgt, color, g }: { label: string; val: number; tgt?: number; color: string; g: string }) {
  const pct = tgt ? Math.min(100, Math.round((val / tgt) * 100)) : 0;
  return (
    <div style={{ flex: 1, background: 'rgba(128,128,128,.08)', borderRadius: 10, padding: 8 }}>
      <div style={{ fontSize: 11, color: 'var(--mut)' }}>{label}</div>
      <div style={{ fontWeight: 700 }}>{Math.round(val)}{tgt ? `/${tgt}` : ''} {g}</div>
      {tgt ? <div style={{ height: 4, background: 'rgba(128,128,128,.25)', borderRadius: 2, marginTop: 4 }}><div style={{ width: `${pct}%`, height: 4, background: color, borderRadius: 2 }} /></div> : null}
    </div>
  );
}

function DayBody({ d }: { d: NutritionDay }) {
  const t = useT();
  const tot = d.totals ?? {};
  const g = t('nut.g'), mg = t('nut.mg');
  const ppk = d.protein_per_kg;
  const micro = (k: string, l: string, u: string) => <Tile key={k} label={l} unit={u} v={`${MICRO_LIMIT.has(k) ? '≤' : ''}${Math.round(tot[k] || 0)}/${MICRO_T[k]}`} />;

  let ring = null;
  if (d.targets) {
    const budget = d.targets.kcal + (d.burned || 0);
    const eaten = Math.round(tot.kcal || 0);
    const remain = budget - eaten;
    const deg = Math.min(360, budget > 0 ? (eaten / budget) * 360 : 0);
    ring = (
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ textAlign: 'center', width: 76 }}><div style={{ fontSize: 11, color: 'var(--mut)' }}>{t('nut.eaten')}</div><div style={{ fontSize: 18, fontWeight: 700 }}>{eaten}</div></div>
          <div style={{ position: 'relative', width: 118, height: 118, borderRadius: '50%', background: `conic-gradient(var(--btn) 0 ${deg}deg, rgba(128,128,128,.18) ${deg}deg 360deg)`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 94, height: 94, borderRadius: '50%', background: 'var(--bg)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ fontSize: 10, color: 'var(--mut)' }}>{t('nut.remaining')}</div>
              <div style={{ fontSize: 22, fontWeight: 800 }}>{remain >= 0 ? remain : <span style={{ color: 'var(--red)' }}>{t('nut.over', { v: -remain })}</span>}</div>
              <div style={{ fontSize: 9, color: 'var(--mut)' }}>{t('nut.norm', { v: d.targets.kcal })}</div>
            </div>
          </div>
          <div style={{ textAlign: 'center', width: 76 }}><div style={{ fontSize: 11, color: 'var(--mut)' }}>{t('nut.burned')}</div><div style={{ fontSize: 18, fontWeight: 700, color: 'var(--green)' }}>+{d.burned || 0}</div></div>
        </div>
      </Card>
    );
  }
  return (
    <>
      {ring}
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <div><span style={{ fontSize: 26, fontWeight: 700 }}>{Math.round(tot.kcal || 0)}</span><span style={{ fontSize: 12, opacity: 0.6, marginLeft: 4 }}>{t('nut.kcal')}</span></div>
          <div style={{ fontSize: 13, color: 'var(--mut)' }}>
            💧 {d.water_l ?? 0}{d.water_target_l != null ? ` / ${d.water_target_l}` : ''} {t('nut.l')}
            {(d.water_target_l ?? 0) > 2.2 && <span style={{ marginLeft: 6 }}>{t('nut.water_sweat', { v: ((d.water_target_l as number) - 2.2).toFixed(1) })}</span>}
          </div>
        </div>
        {d.targets ? (
          <div style={{ display: 'flex', gap: 8, marginTop: 9 }}>
            <MBar label={t('nut.protein')} val={tot.protein_g || 0} tgt={d.targets.protein_g} color="#e5484d" g={g} />
            <MBar label={t('nut.fat')} val={tot.fat_g || 0} tgt={d.targets.fat_g} color="#b088f9" g={g} />
            <MBar label={t('nut.carb')} val={tot.carb_g || 0} tgt={d.targets.carb_g} color="#4c8dff" g={g} />
          </div>
        ) : (
          <div className="det-tiles" style={{ marginTop: 9 }}>
            <Tile label={t('nut.protein')} unit={g} v={Math.round(tot.protein_g || 0)} />
            <Tile label={t('nut.fat')} unit={g} v={Math.round(tot.fat_g || 0)} />
            <Tile label={t('nut.carb')} unit={g} v={Math.round(tot.carb_g || 0)} />
          </div>
        )}
        {ppk != null && <div style={{ fontSize: 12, color: ppk >= 1.6 ? 'var(--green)' : 'var(--amber)', marginTop: 7 }}>{t('nut.protein_per_kg', { v: ppk })}</div>}
      </Card>
      <SecTitle>{t('nut.meals_hd')}</SecTitle>
      {d.meals.length ? d.meals.map((m, i) => {
        const foods = (m.foods ?? []).map((f) => `${f.name} ~${f.grams != null ? Math.round(f.grams) : '—'}г`).join(', ');
        const q = m.quality ? splitEmoji(t(`q.meal.${m.quality}`)) : null;
        const card = (
          <Card key={i}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
              <b>{(m.ts || '').slice(11, 16) || '—'}</b>
              <b>{q && <span style={{ marginRight: 6 }}>{q.emoji}</span>}{Math.round(m.kcal || 0)} {t('nut.kcal')}</b>
            </div>
            <div style={{ fontSize: 12.5, opacity: 0.85, marginTop: 3 }}>{foods}</div>
            <div style={{ fontSize: 11.5, color: 'var(--mut)', marginTop: 3 }}>{t('nut.bju')}: {Math.round(m.protein_g || 0)} / {Math.round(m.fat_g || 0)} / {Math.round(m.carb_g || 0)} {g}</div>
            {(m.quality === 3 || m.quality === 4) && q && <div style={{ fontSize: 11.5, color: 'var(--mut)', marginTop: 3 }}>{q.label} — {m.quality_note || ''}</div>}
          </Card>
        );
        return m.id != null ? <Link key={i} to={`/meals/${m.id}?day=${d.day}`} style={{ color: 'inherit', textDecoration: 'none' }}>{card}</Link> : card;
      }) : <Card style={{ color: 'var(--mut)', fontSize: 13 }}>{t('nut.no_meals')}</Card>}
      {d.day_verdict && <Card style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700 }}><span>{d.day}</span><span>{t(`q.day.${d.day_verdict}`)}</span></Card>}
      <SecTitle>{t('nut.micro_hd')}</SecTitle>
      <Card>
        <div className="det-tiles" style={{ gridTemplateColumns: 'repeat(2,1fr)' }}>
          {micro('fiber_g', t('nut.m_fiber'), g)}{micro('sodium_mg', t('nut.m_sodium'), mg)}
          {micro('calcium_mg', t('nut.m_calcium'), mg)}{micro('potassium_mg', t('nut.m_potassium'), mg)}
        </div>
        <details style={{ marginTop: 8 }}>
          <summary style={{ fontSize: 12, color: 'var(--mut)', cursor: 'pointer' }}>{t('nut.micro_more')}</summary>
          <div className="det-tiles" style={{ gridTemplateColumns: 'repeat(3,1fr)', marginTop: 8 }}>
            {micro('sugar_g', t('nut.m_sugar'), g)}{micro('iron_mg', t('nut.m_iron'), mg)}{micro('magnesium_mg', t('nut.m_magnesium'), mg)}
          </div>
        </details>
        <div style={{ fontSize: 11, color: 'var(--mut)', marginTop: 7 }}>{t('nut.micro_note')}</div>
      </Card>
      {d.advice && d.advice.length > 0 && (
        <>
          <SecTitle>{t('nut.advice_hd')}</SecTitle>
          <Card>{d.advice.map((a, i) => <div key={i} style={{ fontSize: 13, margin: '3px 0' }}>• {a}</div>)}</Card>
        </>
      )}
      <LlmBlock kind="nutr_day" refKey={d.day} pro={!!d.pro} />
      <div className="foot">{t('nut.hint')}</div>
    </>
  );
}

export function NutritionDayScreen() {
  const t = useT();
  const nav = useNavigate();
  const { day = '' } = useParams();
  const state = useFetch(() => endpoints.nutritionDay(day), `nutrition:${day}`);
  return (
    <>
      <button type="button" className="back linkbtn" style={{ textDecoration: 'none', color: 'var(--mut)' }} onClick={() => nav('/nutrition')}>← {t('nut.title')}</button>
      <h1>{day}</h1>
      <Link className="btn primary block" to={`/meals/new?day=${day}`} style={{ marginBottom: 10 }}>＋ {t('meal.add')}</Link>
      <Async state={state}>{(d) => <DayBody d={d} />}</Async>
    </>
  );
}
