// Выбор зала для админа и тренера: их может быть несколько. Зал держится в адресе (?gym=) и
// запоминается на устройстве; по умолчанию — зал из профиля.
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { adminApi } from '../../api/admin';
import { clubApi, type ClubGym, type ClubGyms } from '../../api/club';
import { useT } from '../../i18n';

const LS_KEY = 'fepra.club.gym';

function readStored(): string | null {
  try { return localStorage.getItem(LS_KEY); } catch { return null; }
}
function writeStored(v: string): void {
  try { localStorage.setItem(LS_KEY, v); } catch { /* localStorage недоступен */ }
}

/** Выбранный зал среди доступных. only: показывать только залы, где можно менять программу. */
export function pickGym(gyms: ClubGym[], fromUrl: string | null, stored: string | null, current: string | undefined): string | undefined {
  const names = gyms.map((g) => g.name);
  if (fromUrl && names.includes(fromUrl)) return fromUrl;
  if (stored && names.includes(stored)) return stored;
  if (current && names.includes(current)) return current;
  return names[0];
}

export function useClubGym(only: 'all' | 'manage' = 'all') {
  const [sp, setSp] = useSearchParams();
  const [info, setInfo] = useState<ClubGyms | null>(null);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    clubApi.gyms().then((g) => alive && setInfo(g), () => alive && setFailed(true));
    return () => { alive = false; };
  }, [tick]);
  const gyms = useMemo(() => (info?.gyms ?? []).filter((g) => only === 'all' || g.can_manage), [info, only]);
  const gym = useMemo(
    () => (info ? pickGym(gyms, sp.get('gym'), readStored(), info.current) : undefined),
    [info, gyms, sp],
  );
  const pick = (g: string) => {
    writeStored(g);
    setSp((prev) => { const n = new URLSearchParams(prev); n.set('gym', g); return n; }, { replace: true });
  };
  /** админ создаёт зал и сразу выбирает его */
  const add = async (name: string) => {
    const made = await adminApi.addGym(name);
    setTick((n) => n + 1);
    pick(made.name);
  };
  // failed: список залов не загрузился; экраны работают без выбора, зал подставит сервер
  return { gym, gyms, pick, ready: info != null || failed, failed, canAdd: !!info?.can_add, add };
}

/** Переключатель зала: виден, если залов больше одного или админ может добавить зал. */
export function GymPicker({ gym, gyms, onPick, canAdd, onAdd }: {
  gym: string | undefined; gyms: ClubGym[]; onPick: (g: string) => void;
  canAdd?: boolean; onAdd?: (name: string) => Promise<void>;
}) {
  const t = useT();
  const [err, setErr] = useState('');
  if (gyms.length < 2 && !(canAdd && onAdd)) return null;
  const create = async () => {
    const name = (window.prompt(t('club.gym_add_prompt')) || '').trim();
    if (!name || !onAdd) return;
    setErr('');
    try { await onAdd(name); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  };
  return (
    <div className="gym-pick" role="group" aria-label={t('club.gym_pick')}>
      <span className="mut" style={{ fontSize: 13 }}>{t('club.gym_pick')}</span>
      <div className="rec-chips">
        {gyms.map((g) => (
          <button key={g.name} type="button" className={`rec-chip${g.name === gym ? ' on' : ''}`} aria-pressed={g.name === gym} onClick={() => onPick(g.name)}>
            {g.name}
          </button>
        ))}
        {canAdd && onAdd && (
          <button type="button" className="rec-chip" onClick={create}>{t('club.gym_add')}</button>
        )}
      </div>
      {err && <div className="mut" role="alert" style={{ fontSize: 13, color: 'var(--danger, #c33)' }}>{err}</div>}
    </div>
  );
}
