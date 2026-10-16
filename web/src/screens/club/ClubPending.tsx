import { useState } from 'react';
import { clubApi, type ClubProgram } from '../../api/club';
import { Async, Card } from '../../components/ui';
import { useT } from '../../i18n';
import { canManageClub } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { useFetch } from '../../lib/useFetch';
import { BackLink, Guard, apiMessage } from '../ui5';
import { GymPicker, useClubGym } from './clubGym';

function Item({ p, reload }: { p: ClubProgram; reload: () => void }) {
  const t = useT();
  const [text, setText] = useState(p.raw_text);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      reload();
    } catch (e) {
      setErr(apiMessage(e, t));
      setBusy(false);
    }
  }
  return (
    <Card>
      <div className="mut" style={{ fontSize: 12, marginBottom: 6 }}>{p.gym} · {p.day} · {p.source ?? ''}</div>
      <textarea aria-label={t('club.program_text')} rows={6} value={text} onChange={(e) => setText(e.target.value)}
        style={{ width: '100%', borderRadius: 10, border: '1px solid var(--bd)', padding: 8, background: 'var(--bg)' }} />
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button type="button" className="btn primary" style={{ flex: 1 }} disabled={busy} onClick={() => void act(() => clubApi.confirm(p.id, text !== p.raw_text ? text : undefined))}>{t('club.confirm')}</button>
        <button type="button" className="btn danger" style={{ flex: 1 }} disabled={busy} onClick={() => { if (window.confirm(t('club.reject_confirm'))) void act(() => clubApi.reject(p.id)); }}>{t('club.reject')}</button>
      </div>
      {err && <div className="msg err" role="alert">{err}</div>}
    </Card>
  );
}

export function ClubPendingScreen() {
  const t = useT();
  const { me } = useSession();
  const ok = canManageClub(me);
  const { gym, gyms, pick, ready, canAdd, add } = useClubGym('manage');
  const state = useFetch(ok && ready ? () => clubApi.pending(gym) : null, `club-pending:${ready ? 'r' : 'w'}:${gym ?? ''}`);
  return (
    <>
      <BackLink to="/club" />
      <h1>{t('club.pending')}</h1>
      <Guard ok={ok}>
        <GymPicker gym={gym} gyms={gyms} onPick={pick} canAdd={canAdd} onAdd={add} />
        <Async state={state}>
          {(list) => list.length === 0 ? <div className="sub">{t('club.pending_none')}</div> : <>{list.map((p) => <Item key={p.id} p={p} reload={state.reload} />)}</>}
        </Async>
      </Guard>
    </>
  );
}
