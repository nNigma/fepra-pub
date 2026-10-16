import { Link } from 'react-router-dom';
import type { Loc, Reference } from '../../api/programs';
import { useI18n } from '../../i18n';
import { fmtDay, fmtKg, isStale, loc, sourceKey } from './tree';

export type LiftNames = Record<string, Loc>;

export function liftLabel(lift: string, names: LiftNames | undefined, lang: string): string {
  const n = names?.[lift];
  return n ? loc(n, lang) : lift.replace(/_/g, ' ');
}

export function Crumbs({ items }: { items: { to?: string; label: string }[] }) {
  return (
    <nav className="pg-crumbs" aria-label="breadcrumbs">
      {items.map((c, i) => (
        <span key={i}>
          {i > 0 && <span aria-hidden="true"> › </span>}
          {c.to ? <Link to={c.to}>{c.label}</Link> : <b style={{ color: 'var(--tx)' }}>{c.label}</b>}
        </span>
      ))}
    </nav>
  );
}

/** Строка опорного веса: лифт, кг и откуда взялась цифра (best / derived / starter / needs_input …). */
export function ReferenceRow({ ref_, name, names }: { ref_: Reference; name: string; names?: LiftNames }) {
  const { t, lang } = useI18n();
  const key = sourceKey(ref_);
  const stale = isStale(ref_);
  let src = t(key);
  if (ref_.source === 'best' && ref_.day) src = t('pg.src.best_day', { day: fmtDay(ref_.day) });
  if (ref_.source === 'derived' && ref_.from?.length) {
    src = t('pg.src.derived_from', { lifts: ref_.from.map((l) => liftLabel(l, names, lang)).join(', ') });
  }
  if (ref_.source === 'starter' && ref_.level) src = t('pg.src.starter_level', { level: t(`pg.level.${ref_.level}`) });
  const estimate = ref_.source === 'derived' || ref_.source === 'starter';
  const cls = ref_.source === 'best' && !stale ? 'ok' : ref_.source === 'needs_input' || stale ? 'warn' : '';
  return (
    <div className="pg-ref" data-source={ref_.source}>
      <div className="nm">
        <b>{name}</b>
        <div className="src">
          <span className={`pg-badge ${cls}`}>{src}</span>
          {stale && <span className="pg-badge warn" style={{ marginLeft: 6 }}>{t('pg.stale')}</span>}
        </div>
        {estimate && <div className="src">{t('pg.estimate_hint')}</div>}
      </div>
      <div className="kg">{ref_.kg == null ? '—' : <>{fmtKg(ref_.kg)}<small className="mut"> {t('pg.kg')}</small></>}</div>
    </div>
  );
}
