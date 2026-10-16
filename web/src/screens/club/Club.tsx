import { Link, useSearchParams } from 'react-router-dom';
import { clubApi } from '../../api/club';
import { Async, Card } from '../../components/ui';
import { useT } from '../../i18n';
import { canManageClub } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { useFetch } from '../../lib/useFetch';
import { BackLink, shiftDay, todayIso } from '../ui5';
import { GymPicker, useClubGym } from './clubGym';

export function ClubScreen() {
  const t = useT();
  const { me } = useSession();
  const [sp, setSp] = useSearchParams();
  const day = sp.get('day') || todayIso();
  const { gym, gyms, pick, ready, canAdd, add } = useClubGym();
  const state = useFetch(ready ? () => clubApi.program(day, gym) : null, `club:${day}:${ready ? 'r' : 'w'}:${gym ?? ''}`);
  const go = (d: string) => setSp((prev) => { const n = new URLSearchParams(prev); if (d === todayIso()) n.delete('day'); else n.set('day', d); return n; });
  const q = gym ? `&gym=${encodeURIComponent(gym)}` : '';
  const manage = canManageClub(me);
  return (
    <>
      <BackLink to="/more" label={t('tab.more')} />
      <h1>{t('club.title')}</h1>
      <GymPicker gym={gym} gyms={gyms} onPick={pick} canAdd={canAdd} onAdd={add} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '8px 0 12px' }}>
        <button type="button" className="btn" aria-label={t('meal.prev_day')} onClick={() => go(shiftDay(day, -1))}>‹</button>
        <div style={{ fontWeight: 600 }}>{day === todayIso() ? t('meal.today') : day}</div>
        <button type="button" className="btn" aria-label={t('meal.next_day')} onClick={() => go(shiftDay(day, 1))}>›</button>
      </div>
      <Async state={state}>
        {(d) => (
          <>
            <div className="sub">{d.gym}</div>
            {d.program ? (
              <Card>
                <div className="mut" style={{ fontSize: 12, marginBottom: 6 }}>{d.program.format}</div>
                <div style={{ whiteSpace: 'pre-wrap' }}>{d.program.raw_text}</div>
                {d.program.movements.length > 0 && (
                  <div style={{ marginTop: 8 }}>{d.program.movements.map((m) => <span key={m} className="wchip" style={{ marginRight: 4 }}>{m}</span>)}</div>
                )}
              </Card>
            ) : (
              <>
                <div className="sub">{t('club.no_program')}</div>
                {d.last_day && <button type="button" className="btn block" onClick={() => go(d.last_day!)}>{t('club.last_day', { day: d.last_day })}</button>}
              </>
            )}
            {d.program && (
              <Link className="btn primary block" style={{ marginTop: 12, minHeight: 56 }} to={`/record?gym=${encodeURIComponent(d.gym)}&day=${d.day}`}>
                🏋️ {t('club.record_this')}
              </Link>
            )}
            {manage && d.can_manage && (
              <Link className="btn block" style={{ marginTop: 8 }} to={`/club/edit?day=${d.day}${q}`}>✏️ {d.program ? t('club.edit') : t('club.create')}</Link>
            )}
          </>
        )}
      </Async>
      {manage && (
        <div style={{ marginTop: 14 }}>
          <Link className="menu-link" to={`/club/pending?${q.slice(1)}`}><span>📥 {t('club.pending')}</span><span className="mut">›</span></Link>
          <Link className="menu-link" to={`/club/stats?${q.slice(1)}`}><span>📈 {t('club.stats')}</span><span className="mut">›</span></Link>
        </div>
      )}
    </>
  );
}
