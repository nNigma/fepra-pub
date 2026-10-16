import { useState } from 'react';
import type { FieldType, FormField, ResultForm, Scaling } from '../../api/record';
import { useT } from '../../i18n';
import {
  CARDIO_UNITS, TIME_UNITS, groupFields, joinBar, joinCardio, joinPair, joinSled, maskTime, normalizeTime, parseCardio, splitBar,
  splitPair, splitSled,
  type FieldError,
} from './logic';
import './record.css';

interface FieldProps {
  field: FormField;
  value: string;
  error?: FieldError;
  onChange: (v: string) => void;
}

function digitsOnly(s: string, max = 5) {
  return s.replace(/\D/g, '').slice(0, max);
}
function decimalOnly(s: string) {
  return s.replace(/[^\d.,]/g, '').slice(0, 7);
}

const COMPOUND = new Set<string>(['cardio', 'weight_distance', 'reps_load']);

export function FieldInput({ field, value, error, onChange }: FieldProps) {
  const t = useT();
  const id = `rf-${field.key}`;
  let control;
  switch (field.type as FieldType) {
    case 'weight_reps': {
      const [w, r] = splitPair(value, 'x');
      // повторы по схеме (5×5, 21-15-9) стоят готовым значением: атлет правит их, только если подход отличался
      const shownReps = r !== '' ? r : field.reps_default ? String(field.reps_default) : '';
      control = (
        <span className="rec-pair">
          <input
            id={id} className="rec-in" inputMode="decimal" autoComplete="off" placeholder={t('rec.kg')} aria-label={`${field.label}: ${t('rec.kg')}`}
            value={w}
            onChange={(e) => {
              const raw = e.target.value;
              // вставили «100x5» целиком — делим на вес и повторы
              if (/[x×хХX*]/.test(raw)) onChange(joinPair(...splitPair(raw, 'x'), 'x'));
              else onChange(joinPair(decimalOnly(raw), r, 'x'));
            }}
          />
          <span aria-hidden="true">×</span>
          <input
            className={`rec-in${r === '' && field.reps_default ? ' preset' : ''}`} inputMode="numeric" autoComplete="off"
            placeholder={field.reps_optional ? t('rec.reps_opt') : t('rec.reps')}
            title={field.reps_default ? t('rec.repsDefaultHint', { n: field.reps_default }) : undefined}
            aria-label={`${field.label}: ${t('rec.reps')}`}
            value={shownReps}
            onChange={(e) => onChange(joinPair(w, digitsOnly(e.target.value, 4), 'x'))}
          />
        </span>
      );
      break;
    }
    case 'cardio': {
      // ккал, метры ИЛИ время: единицу выбирает атлет, значение — одно
      const { unit, value: cv } = parseCardio(value, field.default_unit);
      control = (
        <span className="rec-pair">
          <input
            id={id} className="rec-in" inputMode="decimal" autoComplete="off"
            aria-label={`${field.label}: ${t(`rec.unit.${unit}`)}`}
            value={cv}
            onChange={(e) => onChange(joinCardio(unit, decimalOnly(e.target.value)))}
          />
          <select
            className="rec-in" aria-label={t('rec.unit.choose')} value={unit}
            onChange={(e) => onChange(joinCardio(e.target.value as (typeof CARDIO_UNITS)[number], cv))}
          >
            {CARDIO_UNITS.map((u) => <option key={u} value={u}>{t(`rec.unit.${u}`)}</option>)}
          </select>
        </span>
      );
      break;
    }
    case 'weight_distance': {
      // сани: вес, дистанция и/или время (сек или мин) — три ячейки в ряд, у каждой своя подпись
      const [w, d, tm, tu] = splitSled(value);
      control = (
        <div className="rec-multi">
          <label className="cell">
            <span className="cap">{t('rec.kg')}</span>
            <input
              id={id} className="rec-in" inputMode="decimal" autoComplete="off"
              aria-label={`${field.label}: ${t('rec.kg')}`} value={w}
              onChange={(e) => onChange(joinSled(decimalOnly(e.target.value), d, tm, tu))}
            />
          </label>
          <label className="cell">
            <span className="cap">{t('rec.meters')}</span>
            <input
              className="rec-in" inputMode="decimal" autoComplete="off"
              aria-label={`${field.label}: ${t('rec.meters')}`} value={d}
              onChange={(e) => onChange(joinSled(w, decimalOnly(e.target.value), tm, tu))}
            />
          </label>
          <div className="cell time">
            <span className="cap">{t('rec.time')}</span>
            <span className="tpair">
              <input
                className="rec-in" inputMode="decimal" autoComplete="off"
                aria-label={`${field.label}: ${t('rec.time')}`} value={tm}
                onChange={(e) => onChange(joinSled(w, d, decimalOnly(e.target.value), tu))}
              />
              <select
                className="rec-in" aria-label={t('rec.unit.choose_time')} value={tu}
                onChange={(e) => onChange(joinSled(w, d, tm, e.target.value as (typeof TIME_UNITS)[number]))}
              >
                {TIME_UNITS.map((u) => <option key={u} value={u}>{t(`rec.unit.${u}`)}</option>)}
              </select>
            </span>
          </div>
        </div>
      );
      break;
    }
    case 'reps_load': {
      // как везде: вес × повторы. Вес по желанию (жилет, блин), повторы обязательны
      const [w, r] = splitBar(value);
      control = (
        <span className="rec-pair">
          <input
            id={id} className="rec-in" inputMode="decimal" autoComplete="off" placeholder={t('rec.kg')}
            aria-label={`${field.label}: ${t('rec.weight_opt')}`} title={t('rec.weight_opt')} value={w}
            onChange={(e) => onChange(joinBar(decimalOnly(e.target.value), r))}
          />
          <span aria-hidden="true">×</span>
          <input
            className="rec-in" inputMode="numeric" autoComplete="off" placeholder={t('rec.reps')}
            aria-label={`${field.label}: ${t('rec.reps')}`} value={r}
            onChange={(e) => onChange(joinBar(w, digitsOnly(e.target.value, 4)))}
          />
        </span>
      );
      break;
    }
    case 'rounds_reps': {
      const [a, b] = splitPair(value, '+');
      control = (
        <span className="rec-pair">
          <input id={id} className="rec-in" inputMode="numeric" autoComplete="off" placeholder={t('rec.rounds')} aria-label={`${field.label}: ${t('rec.rounds')}`}
            value={a} onChange={(e) => onChange(joinPair(digitsOnly(e.target.value, 4), b, '+'))} />
          <span aria-hidden="true">+</span>
          <input className="rec-in" inputMode="numeric" autoComplete="off" placeholder={t('rec.reps')} aria-label={`${field.label}: ${t('rec.reps')}`}
            value={b} onChange={(e) => onChange(joinPair(a, digitsOnly(e.target.value, 4), '+'))} />
        </span>
      );
      break;
    }
    case 'time':
      control = (
        <input
          id={id} className="rec-in wide" inputMode="numeric" autoComplete="off" placeholder={t('rec.mmss')} value={value}
          onChange={(e) => onChange(maskTime(e.target.value))}
          onBlur={() => { const n = normalizeTime(value); if (n && n !== value) onChange(n); }}
        />
      );
      break;
    case 'int':
      control = <input id={id} className="rec-in" inputMode="numeric" autoComplete="off" value={value} onChange={(e) => onChange(digitsOnly(e.target.value))} />;
      break;
    case 'weight':
      control = <input id={id} className="rec-in" inputMode="decimal" autoComplete="off" placeholder={t('rec.kg')} value={value} onChange={(e) => onChange(e.target.value.slice(0, 24))} />;
      break;
    default:
      control = <input id={id} className="rec-in wide" autoComplete="off" value={value} onChange={(e) => onChange(e.target.value)} />;
  }
  // у составных полей название не должно навязывать единицу: её выбирает атлет
  const rowLabel = field.type === 'cardio' ? t('rec.label.cardio')
    : field.type === 'weight_distance' ? t('rec.label.sled')
    : field.type === 'reps_load' ? t('rec.label.reps_load') : field.label;
  return (
    <div className={`rec-row${error ? ' bad' : ''}${field.type === 'weight_distance' ? ' stack' : ''}`}>
      <label htmlFor={id}>
        {rowLabel}
        {field.unit && !COMPOUND.has(field.type) && <span className="unit">{field.unit}</span>}
      </label>
      {control}
      {error && <div className="rec-err" role="alert">{t(`rec.fmt.${error}`)}</div>}
    </div>
  );
}

export function FormBlocks({ form, values, errors, onChange }: {
  form: ResultForm; values: Record<string, string>; errors: Record<string, FieldError>; onChange: (key: string, v: string) => void;
}) {
  const t = useT();
  if (!form.blocks.length) return <div className="msg info">{t('rec.no_form')}</div>;
  return (
    <>
      {form.blocks.map((b) => (
        <div key={b.index} className="card" style={{ marginBottom: 10 }}>
          <div style={{ fontWeight: 600 }}>{b.title}{b.has_cap ? ` · ${t('rec.cap')}` : ''}</div>
          {groupFields(b.fields).map((g, gi) => (
            <div key={gi}>
              {g.group && <div className="rec-sub">{g.group}</div>}
              {g.fields.map((f) => (
                <FieldInput key={f.key} field={f} value={values[f.key] ?? ''} error={errors[f.key]} onChange={(v) => onChange(f.key, v)} />
              ))}
            </div>
          ))}
        </div>
      ))}
    </>
  );
}

const HOW_KEYS = ['barbell', 'dumbbell', 'gym', 'cardio', 'time', 'amrap', 'scaling'] as const;

export function HowTo() {
  const t = useT();
  return (
    <details className="methelp">
      <summary>{t('rec.how.title')}</summary>
      <ul className="rec-how">{HOW_KEYS.map((k) => <li key={k}>{t(`rec.how.${k}`)}</li>)}</ul>
    </details>
  );
}

export function RpeScale({ value, onChange }: { value: number | null; onChange: (v: number | null) => void }) {
  const t = useT();
  return (
    <div>
      <div className="mut" style={{ fontSize: 13, marginBottom: 4 }}>{t('rec.rpe')} <span>{t('rec.rpe_hint')}</span></div>
      <div className="rec-grid5" role="group" aria-label={t('rec.rpe')}>
        {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
          <button key={n} type="button" className={value === n ? 'on' : ''} aria-pressed={value === n} onClick={() => onChange(value === n ? null : n)}>{n}</button>
        ))}
      </div>
    </div>
  );
}

export function ScalingPick({ value, onChange }: { value: Scaling; onChange: (v: Scaling) => void }) {
  const t = useT();
  const opts: { v: Scaling; k: string }[] = [{ v: 'rx', k: 'rec.rx' }, { v: 'scaled', k: 'rec.scaled' }, { v: null, k: 'rec.no_mark' }];
  return (
    <div>
      <div className="mut" style={{ fontSize: 13, marginBottom: 4 }}>{t('rec.scaling')}</div>
      <div className="rec-chips" role="group" aria-label={t('rec.scaling')}>
        {opts.map((o) => (
          <button key={String(o.v)} type="button" className={`rec-chip${value === o.v ? ' on' : ''}`} aria-pressed={value === o.v} onClick={() => onChange(o.v)}>{t(o.k)}</button>
        ))}
      </div>
    </div>
  );
}

/** Подтверждение опасного действия без window.confirm. */
export function useConfirm() {
  const [asked, setAsked] = useState(false);
  return { asked, ask: () => setAsked(true), cancel: () => setAsked(false) };
}
