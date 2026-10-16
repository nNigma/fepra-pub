import { useI18n } from '../../i18n';
import type { AboutBlock, DayBrief, Loc } from '../../api/programs';
import { loc } from './tree';

const DOW_RU = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const DOW_EN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export const dowLabel = (dow: number, lang: string): string => (lang === 'en' ? DOW_EN : DOW_RU)[dow] ?? '';

/** «Над чем работаем»: чипы из focus. */
export function FocusChips({ focus }: { focus?: { ru: string[]; en: string[] } | null }) {
  const { lang } = useI18n();
  const list = (lang === 'en' ? focus?.en : focus?.ru) ?? focus?.ru ?? [];
  if (!list.length) return null;
  return <div className="pg-focus">{list.map((f) => <span key={f} className="sp">{f}</span>)}</div>;
}

/** Блоки «О программе»: раскрывающиеся, первый открыт. */
export function AboutBlocks({ blocks }: { blocks: AboutBlock[] }) {
  const { lang } = useI18n();
  return (
    <div className="pg-about">
      {blocks.map((b, i) => (
        <details key={b.id} className="pg-det" open={i === 0}>
          <summary>{loc(b.title, lang)}</summary>
          <p>{loc(b.text, lang)}</p>
        </details>
      ))}
    </div>
  );
}

/** Один день недели: название, минуты, зачем он нужен и над чем идёт работа. */
export function DayInfo({ d }: { d: DayBrief }) {
  const { t, lang } = useI18n();
  return (
    <div className="pg-day">
      <div className="pg-day-h">
        <b>{dowLabel(d.dow, lang)} · {loc(d.title, lang)}</b>
        <span className="mut"> · {t('pg.minutes', { n: d.minutes })}</span>
        {d.intensity && <span className={`pg-badge ${INTENSITY_CLS[d.intensity] ?? ''}`} style={{ marginLeft: 6 }}>{t(`pg.int.${d.intensity}`)}</span>}
      </div>
      {d.purpose && <div className="pg-day-p">{loc(d.purpose as Loc, lang)}</div>}
      <FocusChips focus={d.focus} />
    </div>
  );
}

const INTENSITY_CLS: Record<string, string> = { max: 'bad', heavy: 'warn', medium: '', light: 'ok', technique: 'ok', base: '' };
