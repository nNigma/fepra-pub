import { Link } from 'react-router-dom';
import { compsApi, type CompEventRow } from '../../api/comps';
import { Async, SecTitle } from '../../components/ui';
import { useT } from '../../i18n';
import { useFetch } from '../../lib/useFetch';

function Row({ e }: { e: CompEventRow }) {
  const t = useT();
  const mine = e.divisions.filter((d) => d.participant_id != null).map((d) => d.name);
  return (
    <Link className="wrow" to={`/comps/${e.id}`}>
      <div className="wmain">
        <div className="wt">{e.name}</div>
        <div className="wsub">{e.city ?? ''} · {e.date_start}{mine.length ? ` · ${mine.join(', ')}` : ` · ${e.divisions.map((d) => d.name).join(', ')}`}</div>
      </div>
      <div className="wchev" aria-label={t('comp5.open')}>›</div>
    </Link>
  );
}

export function CompsScreen() {
  const t = useT();
  const state = useFetch(() => compsApi.list(), 'comps-list');
  return (
    <>
      <h1>{t('comp5.title')}</h1>
      <Link className="btn primary block" to="/comps/new" style={{ margin: '10px 0' }}>＋ {t('comp5.create')}</Link>
      <Async state={state}>
        {(d) => (
          <>
            <SecTitle>{t('comp5.mine')}</SecTitle>
            {d.mine.length === 0 ? <div className="sub">{t('comp5.none_mine')}</div> : d.mine.map((e) => <Row key={e.id} e={e} />)}
            <SecTitle>{t('comp5.others')}</SecTitle>
            {d.others.length === 0 ? <div className="sub">{t('comp5.none_others')}</div> : d.others.map((e) => <Row key={e.id} e={e} />)}
          </>
        )}
      </Async>
      <Link className="menu-link" style={{ marginTop: 14 }} to="/competitions"><span>📊 {t('comp5.reports')}</span><span className="mut">›</span></Link>
    </>
  );
}
