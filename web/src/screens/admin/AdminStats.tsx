import { useMemo, useState } from 'react';
import type { ChartConfiguration } from 'chart.js';
import { adminApi, type AdminStats } from '../../api/admin';
import { ChartCanvas } from '../../components/charts';
import { Async, Card } from '../../components/ui';
import { useT } from '../../i18n';
import { isAdmin } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { useFetch } from '../../lib/useFetch';
import { BackLink, Guard } from '../ui5';

/** Столбцы «действий на пользователя» (топ N). */
export function statsChartConfig(s: AdminStats, top = 12): ChartConfiguration {
  const rows = [...s.users].sort((a, b) => b.total - a.total).slice(0, top);
  return {
    type: 'bar',
    data: {
      labels: rows.map((u) => u.nick ?? `#${u.id}`),
      datasets: [{ data: rows.map((u) => u.total), backgroundColor: '#1D9E75', borderRadius: 4 }],
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { x: { ticks: { precision: 0, font: { size: 10 } } }, y: { ticks: { font: { size: 11 } } } },
    },
  } as unknown as ChartConfiguration;
}

function View({ s }: { s: AdminStats }) {
  const t = useT();
  const cfg = useMemo(() => statsChartConfig(s), [s]);
  const h = Math.max(120, Math.min(12, s.users.length) * 30 + 30);
  return (
    <>
      <div className="grid"><div className="mc"><div className="l">{t('adm.total_actions')}</div><div className="v">{s.total}</div></div>
        <div className="mc"><div className="l">{t('adm.active_users')}</div><div className="v">{s.users.filter((u) => u.total > 0).length}</div></div></div>
      {s.users.length > 0 && <ChartCanvas config={cfg} height={h} />}
      <div style={{ marginTop: 12 }}>
        {s.users.map((u) => (
          <details key={u.id} className="card" style={{ marginBottom: 6 }}>
            <summary style={{ minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}>
              <span>{u.nick ?? `#${u.id}`}</span><b>{u.total}</b>
            </summary>
            {u.actions.map((a) => <div key={a.key} className="kv"><span style={{ color: 'var(--tx)' }}>{a.label}</span><b>{a.n}</b></div>)}
          </details>
        ))}
      </div>
    </>
  );
}

function Body() {
  const t = useT();
  const [days, setDays] = useState(7);
  const state = useFetch(() => adminApi.stats(days), `admin-stats:${days}`);
  return (
    <>
      <div className="langsw" style={{ marginBottom: 10 }}>
        {[1, 7, 30, 90, 0].map((d) => <button key={d} type="button" className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{d ? t('club.days', { n: d }) : t('adm.all_time')}</button>)}
      </div>
      <Async state={state}>{(s) => <Card style={{ padding: 10 }}><View s={s} /></Card>}</Async>
    </>
  );
}

export function AdminStatsScreen() {
  const t = useT();
  const { me } = useSession();
  return (
    <>
      <BackLink to="/admin" />
      <h1>{t('adm.stats')}</h1>
      <Guard ok={isAdmin(me)}><Body /></Guard>
    </>
  );
}
