import { useState } from 'react';
import { endpoints } from '../api/endpoints';
import { Async } from '../components/ui';
import { useT } from '../i18n';
import { useFetch } from '../lib/useFetch';

export function LeaderboardScreen() {
  const t = useT();
  const [metric, setMetric] = useState('overall');
  const state = useFetch(() => endpoints.leaderboard(metric), `lb:${metric}`);
  return (
    <>
      <h1>{t('lb.title')}</h1>
      <Async state={state}>
        {(d) => {
          if (d.no_gym) return <div className="sub">{t('lb.no_gym')}</div>;
          return (
            <>
              <div className="lbsel">
                <select aria-label={t('lb.title')} value={metric} onChange={(e) => setMetric(e.target.value)}>
                  <option value="overall">{t('lb.overall')}</option>
                  {(d.disciplines ?? []).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                </select>
              </div>
              <div className="lblist">
                {d.rows?.length ? d.rows.map((r) => (
                  <div key={`${r.place}-${r.user_id ?? r.tg_id ?? r.nick}`} className={`lbrow${r.is_me ? ' me' : ''}`}>
                    <span className="pl">{r.place}</span>
                    <span className="nk">{r.nick || `#${r.user_id ?? r.tg_id}`}</span>
                    <span className="vl">{r.value}{r.tier ? ` · ${r.tier}` : ''}</span>
                  </div>
                )) : <div className="sub">{t('lb.no_data')}</div>}
              </div>
            </>
          );
        }}
      </Async>
    </>
  );
}
