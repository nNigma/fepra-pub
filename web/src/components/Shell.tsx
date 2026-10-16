import { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { endpoints } from '../api/endpoints';
import { useT } from '../i18n';
import { useSession } from '../lib/session';
import { NoticeBanners } from '../screens/programs/Notices';

export function Offline() {
  const t = useT();
  const { retry } = useSession();
  return (
    <div className="wrap">
      <div className="center" role="alert">
        <div style={{ fontSize: 44 }}>📡</div>
        <h1>{t('net.offline_title')}</h1>
        <div className="mut" style={{ maxWidth: 320 }}>{t('net.offline_text')}</div>
        <button type="button" className="btn primary" onClick={retry}>{t('net.retry')}</button>
      </div>
    </div>
  );
}

const A2HS_KEY = 'fepra.a2hs.seen';

export function isIosSafariBrowser(ua = navigator.userAgent, standalone = false): boolean {
  const ios = /iPad|iPhone|iPod/.test(ua);
  return ios && !standalone;
}

/** Подсказка «Добавь на экран Домой» на iPhone: один раз, запоминается в localStorage. */
export function A2hsBanner() {
  const t = useT();
  const [show, setShow] = useState(false);
  useEffect(() => {
    const standalone =
      (navigator as unknown as { standalone?: boolean }).standalone === true ||
      window.matchMedia?.('(display-mode: standalone)').matches === true;
    let seen = false;
    try {
      seen = localStorage.getItem(A2HS_KEY) === '1';
    } catch {
      /* ignore */
    }
    setShow(isIosSafariBrowser(navigator.userAgent, standalone) && !seen);
  }, []);
  if (!show) return null;
  const close = () => {
    try {
      localStorage.setItem(A2HS_KEY, '1');
    } catch {
      /* ignore */
    }
    setShow(false);
  };
  return (
    <div className="banner" role="note">
      <div style={{ flex: 1 }}>
        <b>{t('a2hs.title')}</b>
        {t('a2hs.text')}
      </div>
      <button type="button" className="btn" onClick={close}>{t('a2hs.close')}</button>
    </div>
  );
}

function AsSwitcher() {
  const t = useT();
  const { me, asUser, setAs } = useSession();
  const [users, setUsers] = useState<{ id: string; nick: string }[]>([]);
  const isAdmin = !!me?.roles.admin;
  useEffect(() => {
    if (!isAdmin) return;
    endpoints.users().then(
      (us) => setUsers(us.map((u) => ({ id: String(u.tg_id ?? u.id), nick: u.nick || String(u.tg_id ?? u.id) }))),
      () => {},
    );
  }, [isAdmin]);
  if (!isAdmin) return null;
  return (
    <div className="switcher">
      <label htmlFor="asSel">{t('as.label')}</label>
      <select id="asSel" value={asUser ?? ''} onChange={(e) => setAs(e.target.value || null)}>
        <option value="">{t('as.self')}</option>
        {users.map((u) => <option key={u.id} value={u.id}>{u.nick}</option>)}
      </select>
    </div>
  );
}

const TABS: { to: string; icon: string; key: string; end?: boolean; pro?: boolean }[] = [
  { to: '/', icon: '📊', key: 'tab.summary', end: true },
  { to: '/workouts', icon: '🏋️', key: 'tab.workouts' },
  { to: '/nutrition', icon: '🍽', key: 'tab.nutrition', pro: true },
  { to: '/programs', icon: '📋', key: 'tab.programs' },
  { to: '/goals', icon: '🎯', key: 'tab.goals' },
  { to: '/more', icon: '☰', key: 'tab.more' },
];

export function TabBar() {
  const t = useT();
  const { me } = useSession();
  const pro = !!(me?.roles.pro || me?.roles.admin);
  return (
    <nav className="tabbar" aria-label={t('nav.main')}>
      {TABS.filter((x) => !x.pro || pro).map((x) => (
        <NavLink key={x.to} to={x.to} end={x.end} className={({ isActive }) => (isActive ? 'active' : '')}>
          <span className="ti" aria-hidden="true">{x.icon}</span>
          {t(x.key)}
        </NavLink>
      ))}
    </nav>
  );
}

export function Layout() {
  const { epoch } = useSession();
  return (
    <>
      <div className="wrap">
        <A2hsBanner />
        <NoticeBanners />
        <AsSwitcher />
        <div key={epoch}><Outlet /></div>
      </div>
      <TabBar />
    </>
  );
}
