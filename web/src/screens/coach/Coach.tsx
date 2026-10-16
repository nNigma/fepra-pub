import { useState } from 'react';
import { coachApi, type CoachAnswer, type CoachQA } from '../../api/coach';
import { Async, Card, SecTitle } from '../../components/ui';
import { useT } from '../../i18n';
import { runJob, useCancelFlag } from '../../lib/runJob';
import { isAdmin } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { useFetch } from '../../lib/useFetch';
import { ProGate, apiMessage, todayIso } from '../ui5';

export const COACH_DAILY_LIMIT = 3; // как в handlers/coach.py; админ без лимита

/** Сколько вопросов уже задано сегодня (по ts из /recent) и сколько осталось. */
export function coachRemaining(recent: Pick<CoachQA, 'ts'>[], admin: boolean, today = todayIso()): { used: number; left: number | null } {
  const used = recent.filter((r) => r.ts.startsWith(today)).length;
  return { used, left: admin ? null : Math.max(0, COACH_DAILY_LIMIT - used) };
}

function Ask({ recent, reload }: { recent: CoachQA[]; reload: () => void }) {
  const t = useT();
  const { me } = useSession();
  const cancel = useCancelFlag();
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [answer, setAnswer] = useState<CoachAnswer | null>(null);
  const { left } = coachRemaining(recent, isAdmin(me));
  const blocked = left === 0;

  async function ask() {
    setBusy(true);
    setErr(null);
    setAnswer(null);
    try {
      const r = await runJob<CoachAnswer>(() => coachApi.ask(q.trim()), { signal: cancel, intervalMs: 2000, maxTries: 120 });
      setAnswer(r);
      setQ('');
      reload();
    } catch (e) {
      setErr(apiMessage(e, t));
      reload(); // 429 мог случиться из-за вопросов с другого устройства: обновим счётчик
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="mut" style={{ marginBottom: 8 }} data-testid="coach-left">
        {left == null ? t('coach.unlimited') : t('coach.left', { n: left, total: COACH_DAILY_LIMIT })}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim() && !blocked) void ask(); }}>
        <label className="field">
          <span>{t('coach.q')}</span>
          <textarea rows={4} maxLength={2000} value={q} placeholder={t('coach.q_ph')} onChange={(e) => setQ(e.target.value)} disabled={busy} />
        </label>
        <button type="submit" className="btn primary block" disabled={busy || blocked || !q.trim()}>{busy ? t('coach.thinking') : t('coach.ask')}</button>
      </form>
      {blocked && <div className="msg info" role="note">{t('coach.limit_reached')}</div>}
      {err && <div className="msg err" role="alert">{err}</div>}
      {answer && (
        <Card style={{ marginTop: 12, borderLeft: '3px solid var(--btn)' }}>
          <div style={{ whiteSpace: 'pre-wrap' }}>{answer.answer}</div>
        </Card>
      )}
    </>
  );
}

export function CoachScreen() {
  const t = useT();
  const state = useFetch(() => coachApi.recent(20), 'coach-recent');
  return (
    <>
      <h1>{t('coach.title')}</h1>
      <ProGate>
        <Async state={state}>
          {(recent) => (
            <>
              <Ask recent={recent} reload={state.reload} />
              <SecTitle>{t('coach.recent')}</SecTitle>
              {recent.length === 0 ? <div className="sub">{t('coach.no_recent')}</div> : recent.slice(0, 5).map((r, i) => (
                <details key={i} className="card" style={{ marginBottom: 8 }}>
                  <summary style={{ minHeight: 44, display: 'flex', alignItems: 'center', cursor: 'pointer' }}>{r.question}</summary>
                  <div className="mut" style={{ fontSize: 12 }}>{r.ts.slice(0, 16).replace('T', ' ')}</div>
                  <div style={{ whiteSpace: 'pre-wrap', marginTop: 6 }}>{r.answer}</div>
                </details>
              ))}
            </>
          )}
        </Async>
      </ProGate>
    </>
  );
}
