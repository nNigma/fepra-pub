import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { pushApi, type Notice } from '../../api/programs';
import { useI18n } from '../../i18n';
import './programs.css';

/** Баннеры непрочитанных уведомлений (GET /api/notices). «Garmin просит войти заново» ведёт на экран Garmin. */
export function NoticeBanners() {
  const { t } = useI18n();
  const [list, setList] = useState<Notice[]>([]);
  useEffect(() => {
    let alive = true;
    pushApi.notices().then((n) => alive && setList(Array.isArray(n) ? n : []), () => {});
    return () => { alive = false; };
  }, []);
  if (!list.length) return null;
  const read = (id: string) => {
    setList((l) => l.filter((n) => n.id !== id));
    pushApi.readNotice(id).catch(() => {});
  };
  return (
    <>
      {list.map((n) => (
        <div key={n.id} className="notice-banner" role="status" data-kind={n.kind}>
          <span>{n.text}</span>
          {n.kind.startsWith('garmin') && (
            <Link className="btn" to="/profile/garmin" onClick={() => read(n.id)}>
              {n.kind === 'garmin_expired' ? t('notice.garmin_login') : t('notice.garmin_open')}
            </Link>
          )}
          <button type="button" className="btn" onClick={() => read(n.id)}>{t('notice.dismiss')}</button>
        </div>
      ))}
    </>
  );
}
