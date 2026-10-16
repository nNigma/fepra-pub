import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { mealsApi, type Meal, type MealsDay } from '../../api/meals';
import { Async, Card, SecTitle } from '../../components/ui';
import { MBar, Tile } from '../Nutrition';
import { useT } from '../../i18n';
import { useFetch } from '../../lib/useFetch';
import { ProGate, apiMessage, shiftDay, todayIso } from '../ui5';

const WATER = [-500, -250, 250, 500];

function MealRow({ m, day }: { m: Meal; day: string }) {
  const t = useT();
  return (
    <Link className="wrow" to={`/meals/${m.id}?day=${day}`}>
      {m.photo_url && <img src={m.photo_url} alt="" width={44} height={44} style={{ borderRadius: 8, objectFit: 'cover', marginRight: 10 }} />}
      <div className="wmain">
        <div className="wt">{m.foods.map((f) => f.name).join(', ') || m.note || t('meal.meal')}</div>
        <div className="wsub">{m.ts.slice(11, 16)} · {m.kcal ?? '—'} {t('meal.kcal_unit')} · {m.protein_g ?? 0}/{m.fat_g ?? 0}/{m.carb_g ?? 0}</div>
      </div>
      <div className="wchev">›</div>
    </Link>
  );
}

function Water({ day, ml, target, onChange }: { day: string; ml: number; target?: number | null; onChange: () => void }) {
  const t = useT();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function add(d: number) {
    setBusy(true);
    setErr(null);
    try {
      await mealsApi.water(d, day);
      onChange();
    } catch (e) {
      setErr(apiMessage(e, t));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <SecTitle>{t('meal.water')}</SecTitle>
      <Card>
        <div style={{ fontSize: 22, fontWeight: 600, marginBottom: 8 }} data-testid="water-ml">{ml}{target ? ` / ${Math.round(target * 1000)}` : ''} {t('meal.ml')}</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {WATER.map((d) => (
            <button key={d} type="button" className="btn" disabled={busy || (d < 0 && ml <= 0)} style={{ flex: 1, minWidth: 64 }} onClick={() => void add(d)}>
              {d > 0 ? '+' : '−'}{Math.abs(d)}
            </button>
          ))}
        </div>
        {err && <div className="msg err" role="alert">{err}</div>}
      </Card>
    </>
  );
}

function Summary({ d }: { d: MealsDay }) {
  const t = useT();
  const tot = d.totals ?? {};
  const g = t('nut.g'), mg = t('nut.mg');
  const tg = d.targets;
  const eaten = Math.round(tot.kcal ?? 0);
  const budget = tg ? tg.kcal + (d.burned || 0) : null;
  const remain = budget != null ? budget - eaten : null;
  const mt = d.micro_targets ?? {};
  const limit = new Set(d.micro_limit ?? []);
  const micro = (k: string, l: string, u: string) => (
    <Tile key={k} label={l} unit={u} v={`${limit.has(k) ? '≤' : ''}${Math.round(tot[k] || 0)}${mt[k] ? `/${mt[k]}` : ''}`} />
  );
  return (
    <div style={{ marginTop: 14 }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <div>
            <span style={{ fontSize: 26, fontWeight: 700 }}>{eaten}</span>
            {tg && <span style={{ fontSize: 14, opacity: 0.7 }}> / {budget}</span>}
            <span style={{ fontSize: 12, opacity: 0.6, marginLeft: 4 }}>{t('meal.kcal')}</span>
          </div>
          {remain != null && (
            <div style={{ fontSize: 13, color: remain >= 0 ? 'var(--mut)' : 'var(--red)' }}>
              {remain >= 0 ? `${t('nut.remaining')}: ${remain}` : t('nut.over', { v: -remain })}
            </div>
          )}
        </div>
        {tg && (d.burned ?? 0) > 0 && <div style={{ fontSize: 12, color: 'var(--mut)', marginTop: 2 }}>{t('nut.norm', { v: tg.kcal })} + {t('nut.burned').toLowerCase()} {d.burned}</div>}
        {tg ? (
          <div style={{ display: 'flex', gap: 8, marginTop: 9 }}>
            <MBar label={t('nut.protein')} val={tot.protein_g || 0} tgt={tg.protein_g} color="#e5484d" g={g} />
            <MBar label={t('nut.fat')} val={tot.fat_g || 0} tgt={tg.fat_g} color="#b088f9" g={g} />
            <MBar label={t('nut.carb')} val={tot.carb_g || 0} tgt={tg.carb_g} color="#4c8dff" g={g} />
          </div>
        ) : (
          <>
            <div className="det-tiles" style={{ marginTop: 9 }}>
              <Tile label={t('nut.protein')} unit={g} v={Math.round(tot.protein_g || 0)} />
              <Tile label={t('nut.fat')} unit={g} v={Math.round(tot.fat_g || 0)} />
              <Tile label={t('nut.carb')} unit={g} v={Math.round(tot.carb_g || 0)} />
            </div>
            <div style={{ fontSize: 12, color: 'var(--mut)', marginTop: 7 }}>{t('meal.no_targets')} <Link to="/profile">{t('meal.fill_profile')}</Link></div>
          </>
        )}
        {d.protein_per_kg != null && <div style={{ fontSize: 12, color: d.protein_per_kg >= 1.6 ? 'var(--green)' : 'var(--amber)', marginTop: 7 }}>{t('nut.protein_per_kg', { v: d.protein_per_kg })}</div>}
      </Card>
      <SecTitle>{t('nut.micro_hd')}</SecTitle>
      <Card>
        <div className="det-tiles" style={{ gridTemplateColumns: 'repeat(2,1fr)' }}>
          {micro('fiber_g', t('nut.m_fiber'), g)}{micro('sodium_mg', t('nut.m_sodium'), mg)}
          {micro('calcium_mg', t('nut.m_calcium'), mg)}{micro('potassium_mg', t('nut.m_potassium'), mg)}
          {micro('sugar_g', t('nut.m_sugar'), g)}{micro('iron_mg', t('nut.m_iron'), mg)}
          {micro('magnesium_mg', t('nut.m_magnesium'), mg)}
        </div>
        <div style={{ fontSize: 11, color: 'var(--mut)', marginTop: 7 }}>{t('nut.micro_note')}</div>
      </Card>
    </div>
  );
}

export function MealsScreen() {
  const t = useT();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const day = sp.get('day') || todayIso();
  const state = useFetch(() => mealsApi.day(day), `meals:${day}`);
  const go = (d: string) => setSp(d === todayIso() ? {} : { day: d });
  return (
    <>
      <h1>{t('meal.title')}</h1>
      <ProGate>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '8px 0 12px' }}>
          <button type="button" className="btn" aria-label={t('meal.prev_day')} onClick={() => go(shiftDay(day, -1))}>‹</button>
          <div style={{ fontWeight: 600 }}>{day === todayIso() ? t('meal.today') : day}</div>
          <button type="button" className="btn" aria-label={t('meal.next_day')} disabled={day >= todayIso()} onClick={() => go(shiftDay(day, 1))}>›</button>
        </div>
        <button type="button" className="btn primary block" onClick={() => nav(`/meals/new?day=${day}`)}>＋ {t('meal.add')}</button>
        <Async state={state}>
          {(d) => (
            <>
              <Summary d={d} />
              {d.meals.length === 0 ? <div className="sub">{t('meal.empty')}</div> : d.meals.map((m) => <MealRow key={m.id} m={m} day={day} />)}
              <Water day={day} ml={d.water_ml} target={d.water_target_l} onChange={state.reload} />
            </>
          )}
        </Async>
        <Link className="menu-link" style={{ marginTop: 14 }} to="/nutrition"><span>📊 {t('meal.report')}</span><span className="mut">›</span></Link>
      </ProGate>
    </>
  );
}
