import { useState, type Dispatch } from 'react';
import type { Food } from '../../api/meals';
import { Card } from '../../components/ui';
import { useT } from '../../i18n';
import { splitEmoji } from '../../lib/format';
import { canSave, type DraftAction, type DraftState } from './draft';

const NUMS: { k: 'kcal' | 'protein_g' | 'fat_g' | 'carb_g'; l: string }[] = [
  { k: 'kcal', l: 'meal.kcal' }, { k: 'protein_g', l: 'meal.p' }, { k: 'fat_g', l: 'meal.f' }, { k: 'carb_g', l: 'meal.c' },
];

function num(v: string): number | null {
  if (v.trim() === '') return null;
  const n = Number(v.replace(',', '.'));
  return Number.isFinite(n) ? n : null;
}

function FoodRow({ f, i, dispatch }: { f: Food; i: number; dispatch: Dispatch<DraftAction> }) {
  const t = useT();
  return (
    <Card>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input
          aria-label={t('meal.food_name')} value={f.name} placeholder={t('meal.food_name')}
          style={{ flex: 1, minHeight: 44, padding: '6px 10px', borderRadius: 10, border: '1px solid var(--bd)', background: 'var(--bg)' }}
          onChange={(e) => dispatch({ type: 'food', index: i, patch: { name: e.target.value } })}
        />
        <button type="button" className="btn" aria-label={t('meal.remove_food')} onClick={() => dispatch({ type: 'removeFood', index: i })}>✕</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6, marginTop: 8 }}>
        {[{ k: 'grams', l: 'meal.grams' }, ...NUMS].map(({ k, l }) => (
          <label key={k} style={{ fontSize: 11, color: 'var(--mut)' }}>
            {t(l)}
            <input
              type="number" inputMode="decimal" min={0} step="any" value={f[k] ?? ''}
              style={{ width: '100%', minHeight: 44, padding: '4px 6px', borderRadius: 8, border: '1px solid var(--bd)', background: 'var(--bg)', fontSize: 15 }}
              onChange={(e) => dispatch({ type: 'food', index: i, patch: { [k]: num(e.target.value) } })}
            />
          </label>
        ))}
      </div>
    </Card>
  );
}

/** Черновик приёма: блюда (правка), тоталы, качество, вопрос ИИ, поле «поправить» и накопленные уточнения. */
export function DraftEditor({
  state, dispatch, busy, onCorrect, onSave, saveLabel,
}: {
  state: DraftState;
  dispatch: Dispatch<DraftAction>;
  busy: boolean;
  onCorrect: (text: string) => void;
  onSave: () => void;
  saveLabel: string;
}) {
  const t = useT();
  const [corr, setCorr] = useState('');
  const d = state.draft;
  if (!d) return null;
  const tot = d.totals;
  const q = d.quality ? splitEmoji(t(`q.meal.${d.quality}`)) : null;
  return (
    <>
      {d.question && <div className="msg info" role="note">🤔 {d.question}</div>}
      <div className="grid" style={{ marginBottom: 12 }}>
        <div className="mc"><div className="l">{t('meal.kcal')}</div><div className="v">{tot?.kcal ?? '—'}</div></div>
        <div className="mc"><div className="l">{t('meal.pfc')}</div><div className="v" style={{ fontSize: 17 }}>{tot ? `${tot.protein_g} / ${tot.fat_g} / ${tot.carb_g}` : '—'}</div></div>
      </div>
      {q && <div className="mut" style={{ marginBottom: 8 }}>{q.emoji} {q.label}{d.quality_note ? ` — ${d.quality_note}` : ''}</div>}
      {d.foods.map((f, i) => <FoodRow key={i} f={f} i={i} dispatch={dispatch} />)}
      <button type="button" className="btn block" style={{ marginBottom: 12 }} onClick={() => dispatch({ type: 'addFood' })}>＋ {t('meal.add_food')}</button>

      <form
        onSubmit={(e) => { e.preventDefault(); if (corr.trim()) { onCorrect(corr.trim()); setCorr(''); } }}
        style={{ marginBottom: 12 }}
      >
        <label className="field">
          <span>{t('meal.correct')}</span>
          <input value={corr} placeholder={t('meal.correct_ph')} onChange={(e) => setCorr(e.target.value)} disabled={busy} />
        </label>
        {state.notes.length > 0 && (
          <div className="mut" style={{ fontSize: 13, marginBottom: 8 }} data-testid="notes">
            {t('meal.notes')}: {state.notes.map((n, i) => <span key={i} className="wchip" style={{ marginRight: 4 }}>{n}</span>)}
          </div>
        )}
        <button type="submit" className="btn block" disabled={busy || !corr.trim()}>✏️ {t('meal.correct_btn')}</button>
      </form>

      <button type="button" className="btn primary block" disabled={busy || !canSave(state)} onClick={onSave}>{saveLabel}</button>
    </>
  );
}
