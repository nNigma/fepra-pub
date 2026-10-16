// Программа зала на выбранный день: тренер загрузил доску один раз, атлет открывает её сразу.
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { recordApi, type GymProgram } from '../../api/record';
import { Card } from '../../components/ui';
import { useT } from '../../i18n';
import { canManageClub } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { todayIso } from './draft';
import './record.css';

/** Первые строки доски для превью на карточке. */
export function previewLines(text: string | undefined, max = 5): string {
  const lines = (text ?? '').split('\n').map((l) => l.trim()).filter(Boolean);
  return lines.slice(0, max).join('\n') + (lines.length > max ? '\n…' : '');
}

/** «2026-09-29» -> «29.09» */
export function shortDay(iso: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso.slice(8)}.${iso.slice(5, 7)}` : iso;
}

/** Программа зала на день, если она есть. Ошибки и отсутствие программы дают null (без шума). */
export function useGymProgram(day: string, enabled = true, gym?: string): GymProgram | null {
  const [p, setP] = useState<GymProgram | null>(null);
  useEffect(() => {
    if (!enabled) { setP(null); return; }
    let alive = true;
    recordApi.gymProgram(day, gym).then(
      (r) => { if (alive) setP(r.found ? r : null); },
      () => { if (alive) setP(null); },
    );
    return () => { alive = false; };
  }, [day, enabled, gym]);
  return p;
}

/** Карточка на Сводке и «Тренировках»: программа зала на сегодня и вход в запись.
 *  Админу и тренеру — ещё и добавить или изменить программу (для остальных карточки нет, пока её нет). */
export function GymTodayCard() {
  const t = useT();
  const { me } = useSession();
  const manage = canManageClub(me);
  const day = todayIso();
  const p = useGymProgram(day);
  if (!p && !manage) return null;
  return (
    <Card>
      <div>
        <b>🏢 {t('rec.gym_today_title')}</b>
        {p?.gym && <span className="mut"> · {p.gym}</span>}
      </div>
      {p ? (
        <>
          <pre className="gym-prev">{previewLines(p.board_text, 4)}</pre>
          <Link className="btn primary block" to={`/record?gym=${encodeURIComponent(p.gym || '1')}&day=${day}`}>{t('rec.gym_use')}</Link>
        </>
      ) : (
        <div className="mut" style={{ margin: '6px 0 10px' }}>{t('rec.gym_none_today')}</div>
      )}
      {manage && (
        <Link className={`btn block${p ? '' : ' primary'}`} style={{ marginTop: 8 }} to={`/club/edit?day=${day}`}>
          {p ? `✏️ ${t('rec.gym_edit')}` : `📷 ${t('rec.gym_add')}`}
        </Link>
      )}
    </Card>
  );
}
