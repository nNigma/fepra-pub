import { useState } from 'react';
import { Link } from 'react-router-dom';
import { adminApi } from '../../api/admin';
import { useT } from '../../i18n';
import { pollJob } from '../../lib/jobs';
import { useCancelFlag } from '../../lib/runJob';
import { isAdmin } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { Card, SecTitle } from '../../components/ui';
import { BackLink, Guard, apiMessage } from '../ui5';

interface ReviewResult {
  ok: boolean;
  error?: string | null;
  users: { id: number; ok?: boolean; skipped?: unknown; errors?: unknown; summary?: string }[];
}

function Review() {
  const t = useT();
  const cancel = useCancelFlag();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [res, setRes] = useState<ReviewResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function run() {
    if (!window.confirm(t('adm.review_confirm'))) return;
    setBusy(true);
    setErr(null);
    setRes(null);
    try {
      const r = await adminApi.review();
      setNote(r.already_running ? t('adm.review_already') : null);
      const j = await pollJob(r.job_id, { intervalMs: 3000, maxTries: 400, signal: cancel });
      setRes(j.result as ReviewResult);
    } catch (e) {
      setErr(apiMessage(e, t));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <SecTitle>{t('adm.review')}</SecTitle>
      <Card>
        <div className="mut" style={{ marginBottom: 8 }}>{t('adm.review_text')}</div>
        <button type="button" className="btn block" disabled={busy} onClick={() => void run()}>{busy ? t('adm.review_running') : t('adm.review_run')}</button>
        {note && <div className="msg info" role="status">{note}</div>}
        {err && <div className="msg err" role="alert">{err}</div>}
        {res && (
          <div style={{ marginTop: 8 }}>
            {res.ok === false && <div className="msg err" role="alert">{res.error}</div>}
            {(res.users ?? []).map((u) => (
              <div key={u.id} className="kv"><span>#{u.id}</span><span style={{ textAlign: 'right' }}>{u.summary ?? (u.ok ? 'ok' : '—')}</span></div>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}

export function AdminScreen() {
  const t = useT();
  const { me } = useSession();
  const link = (to: string, icon: string, key: string) => (
    <Link className="menu-link" to={to}><span>{icon} {t(key)}</span><span className="mut">›</span></Link>
  );
  return (
    <>
      <BackLink to="/more" label={t('tab.more')} />
      <h1>{t('adm.title')}</h1>
      <Guard ok={isAdmin(me)}>
        {link('/admin/users', '👥', 'adm.users')}
        {link('/profile/invites', '✉️', 'profile.admin_invites')}
        {link('/admin/gyms', '🏟', 'adm.gyms')}
        {link('/admin/stats', '📈', 'adm.stats')}
        {link('/club/pending', '📥', 'more.club_pending')}
        <Review />
      </Guard>
    </>
  );
}
