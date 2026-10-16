// «Мои записи»: последние ручные тренировки (правка) и удалённые за сессию (отмена).
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { recordApi, type RecentWorkout } from '../../api/record';
import { useT } from '../../i18n';
import { errText } from './errors';
import { trashList, trashRemove, type TrashItem } from './trash';
import './record.css';

/** Счёт из бота бывает многострочным полотном: в списке показываем начало. */
export function shortScore(s: string | null | undefined, max = 32): string | null {
  const line = (s ?? '').split('\n').map((x) => x.trim()).find(Boolean);
  if (!line) return null;
  return line.length > max ? `${line.slice(0, max - 1)}…` : line;
}

export function RecordFab() {
  const t = useT();
  return <Link to="/record" className="rec-fab" aria-label={t('rec.title')} title={t('rec.title')}>+</Link>;
}

export function RecentWorkouts({ day, limit = 5 }: { day?: string; limit?: number }) {
  const t = useT();
  const [list, setList] = useState<RecentWorkout[] | null>(null);
  const [trash, setTrash] = useState<TrashItem[]>(() => trashList());
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    recordApi.recent(day ? 50 : limit).then(
      (l) => alive && setList(l),
      () => alive && setList([]),
    );
    return () => { alive = false; };
  }, [day, limit, tick]);

  const restore = async (it: TrashItem) => {
    try {
      await recordApi.restore(it.id);
      trashRemove(it.id);
      setTrash(trashList());
      setTick((n) => n + 1);
    } catch (e) {
      setErr(errText(e, t));
    }
  };

  const rows = (list ?? []).filter((w) => !day || w.day === day);
  const tr = trash.filter((x) => !day || x.day === day);
  if (!rows.length && !tr.length) return null;
  return (
    <>
      <div className="sec">{day ? t('rec.my_records_day') : t('rec.my_records')}</div>
      {tr.map((it) => (
        <div key={it.id} className="msg info rec-inline" role="status">
          <span style={{ flex: 1 }}>{t('rec.deleted_item', { day: it.day, sport: t(`rec.sport.${it.sport}`) })}</span>
          <button type="button" className="btn" onClick={() => restore(it)}>{t('rec.undo')}</button>
        </div>
      ))}
      {err && <div className="msg err" role="alert">{err}</div>}
      {rows.map((w) => (
        <Link key={w.id} className="wrow" to={`/w/${w.id}`}>
          <div className="wmain">
            <div className="wt">{t(`rec.sport.${w.sport}`)}{w.start_time ? ` · ${w.start_time}` : ''}</div>
            <div className="wsub">{[w.day, shortScore(w.score), w.scaling, w.rpe ? `RPE ${w.rpe}` : null].filter(Boolean).join(' · ')}</div>
          </div>
          <div className="wchev">✎</div>
        </Link>
      ))}
    </>
  );
}
