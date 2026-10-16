import { useState } from 'react';
import { clubApi } from '../../api/club';
import { Async, SecTitle } from '../../components/ui';
import { useT } from '../../i18n';
import { canManageClub } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { useFetch } from '../../lib/useFetch';
import { BackLink, Guard } from '../ui5';
import { GymPicker, useClubGym } from './clubGym';

function Body() {
  const t = useT();
  const [days, setDays] = useState(30);
  const { gym, gyms, pick, ready, canAdd, add } = useClubGym('manage');
  const stats = useFetch(ready ? () => clubApi.stats(gym) : null, `club-stats:${ready ? 'r' : 'w'}:${gym ?? ''}`);
  const ath = useFetch(ready ? () => clubApi.athletes(days, gym) : null, `club-athletes:${days}:${ready ? 'r' : 'w'}:${gym ?? ''}`);
  return (
    <>
      <GymPicker gym={gym} gyms={gyms} onPick={pick} canAdd={canAdd} onAdd={add} />
      <SecTitle>{t('club.movements')}</SecTitle>
      <Async state={stats}>
        {(s) => s.movements.length === 0 ? <div className="sub">{t('club.no_stats')}</div> : <>{s.movements.slice(0, 30).map((m) => <div key={m.canon} className="kv"><span style={{ color: 'var(--tx)' }}>{m.name}</span><b>{m.count}</b></div>)}</>}
      </Async>
      <SecTitle>{t('club.athletes')}</SecTitle>
      <div className="langsw" style={{ marginBottom: 8 }}>
        {[7, 30, 90].map((d) => <button key={d} type="button" className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{t('club.days', { n: d })}</button>)}
      </div>
      <Async state={ath}>
        {(a) => a.athletes.length === 0 ? <div className="sub">{t('club.no_athletes')}</div> : <>{a.athletes.map((x) => <div key={x.id} className="kv"><span style={{ color: 'var(--tx)' }}>{x.nick ?? `#${x.id}`}</span><b>{x.workouts}</b></div>)}</>}
      </Async>
    </>
  );
}

export function ClubStatsScreen() {
  const t = useT();
  const { me } = useSession();
  return (
    <>
      <BackLink to="/club" />
      <h1>{t('club.stats')}</h1>
      <Guard ok={canManageClub(me)}><Body /></Guard>
    </>
  );
}
