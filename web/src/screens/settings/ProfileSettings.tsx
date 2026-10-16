import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { profileApi, type GymList, type Profile } from '../../api/profile';
import { ApiError } from '../../api/client';
import { Async, Card, SecTitle } from '../../components/ui';
import { useI18n, useT } from '../../i18n';
import { useFetch } from '../../lib/useFetch';
import { useSession } from '../../lib/session';
import type { Lang } from '../../api/types';
import { ProfileFields, formFromProfile } from '../onboarding/Onboarding';
import { parseFieldErrors, toPatch, validateFields, type FieldKey, type FormValues } from '../onboarding/validate';
import { BackLink, apiMessage } from '../ui5';

const KEYS: FieldKey[] = ['nick', 'height_cm', 'weight_kg', 'sex', 'age', 'gym', 'goal', 'city', 'lang'];

/** Какие действия с часами показываем и куда они ведут. Правило «один источник» уже применил сервер. */
export function watchRows(actions: string[]): { action: string; provider: string; kind: 'connect' | 'sync' | 'history' | 'disconnect' }[] {
  return actions.map((a) => {
    const [provider, kind] = a.split('_');
    return { action: a, provider, kind: kind as 'connect' | 'sync' | 'history' | 'disconnect' };
  });
}

function Watch({ p }: { p: Profile }) {
  const t = useT();
  const w = p.watch;
  const on = [w.garmin && 'garmin', w.samsung && 'samsung', w.whoop && 'whoop', w.apple && 'apple'].filter(Boolean) as string[];
  const rows = watchRows(p.available_watch_actions);
  return (
    <>
      <SecTitle>{t('set.watch')}</SecTitle>
      <Card>
        {on.length === 0 ? (
          <div className="mut">{t('set.watch_none')}</div>
        ) : (
          <div>{t('set.watch_on', { names: on.map((x) => t(`set.watch.${x}`)).join(', ') })}
            {w.garmin?.status === 'expired' && <div className="msg err" role="alert">{t('set.garmin_expired')}</div>}
          </div>
        )}
        {on.length > 0 && <div className="mut" style={{ marginTop: 6, fontSize: 13 }}>{t('set.watch_one_source')}</div>}
      </Card>
      {rows.some((r) => r.provider === 'garmin') && (
        <Link className="menu-link" to="/profile/garmin"><span>⌚ {t('set.garmin_screen')}</span><span className="mut">›</span></Link>
      )}
      {rows.filter((r) => r.provider !== 'garmin' && r.kind === 'connect').length > 0 && (
        <div className="mut" style={{ fontSize: 13 }}>{t('set.other_in_bot')}</div>
      )}
    </>
  );
}

/** Дополнительные залы: программа каждого доступна при записи тренировки. Основной зал — в форме выше. */
function ExtraGyms({ profile, gyms, reload }: { profile: Profile; gyms: GymList | null; reload: () => void }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const mine = profile.extra_gyms ?? [];
  const options = (gyms?.gyms ?? []).map((g) => g.name).filter((n) => n !== profile.gym);
  if (options.length === 0) return null;
  async function toggle(name: string) {
    setBusy(true);
    setErr(null);
    try {
      await profileApi.patch({ extra_gyms: mine.includes(name) ? mine.filter((x) => x !== name) : [...mine, name] });
      reload();
    } catch (e) {
      setErr(apiMessage(e, t));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <SecTitle>{t('set.extra_gyms')}</SecTitle>
      <Card>
        <div className="mut" style={{ fontSize: 13, marginBottom: 8 }}>{t('set.extra_gyms_hint')}</div>
        <div className="rec-chips" role="group" aria-label={t('set.extra_gyms')}>
          {options.map((n) => (
            <button key={n} type="button" disabled={busy} className={`rec-chip${mine.includes(n) ? ' on' : ''}`} aria-pressed={mine.includes(n)} onClick={() => void toggle(n)}>
              {mine.includes(n) ? '✓ ' : '＋ '}{n}
            </button>
          ))}
        </div>
        {err && <div className="msg err" role="alert">{err}</div>}
      </Card>
    </>
  );
}

function Form({ profile, gyms, reload }: { profile: Profile; gyms: GymList | null; reload: () => void }) {
  const t = useT();
  const { setLang } = useI18n();
  const { refresh } = useSession();
  const initial = useMemo(() => formFromProfile(profile), [profile]);
  const [values, setValues] = useState<FormValues>(initial);
  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setValues(initial), [initial]);

  const changed = KEYS.filter((k) => values[k] !== initial[k]);
  const gymNames = gyms ? [...gyms.gyms.map((g) => g.name), ...gyms.special] : undefined;

  async function save() {
    setMsg(null);
    const ve = validateFields(changed, values, { gyms: gymNames });
    const shown: Partial<Record<FieldKey, string>> = {};
    for (const [k, e] of Object.entries(ve)) shown[k as FieldKey] = t(e.key, e.params);
    setErrors(shown);
    if (Object.keys(shown).length) return;
    setBusy(true);
    try {
      await profileApi.patch(toPatch(changed, values) as never);
      if (changed.includes('lang')) setLang(values.lang as Lang);
      await refresh();
      reload();
      setMsg({ ok: true, text: t('set.saved') });
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        const pf = parseFieldErrors(e);
        setErrors(pf.fields as Partial<Record<FieldKey, string>>);
        if (pf.general) setMsg({ ok: false, text: pf.general });
      } else setMsg({ ok: false, text: apiMessage(e, t) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); void save(); }} noValidate>
      <ProfileFields
        keys={KEYS}
        values={values}
        errors={errors}
        gyms={gyms}
        onChange={(k, v) => { setValues((s) => ({ ...s, [k]: v })); setErrors((s) => ({ ...s, [k]: undefined })); }}
      />
      <label className="kv" style={{ alignItems: 'center', minHeight: 44 }}>
        <span>{t('set.astro')}</span>
        <input
          type="checkbox" style={{ width: 24, height: 24 }} checked={profile.astro}
          onChange={(e) => { void profileApi.patch({ astro: e.target.checked }).then(reload, () => {}); }}
        />
      </label>
      {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role="status">{msg.text}</div>}
      <button type="submit" className="btn primary block" disabled={busy || changed.length === 0}>{t('set.save')}</button>
    </form>
  );
}

export function ProfileSettingsScreen() {
  const t = useT();
  const state = useFetch(async () => {
    const [profile, gyms] = await Promise.all([profileApi.profile(), profileApi.gyms().catch(() => null)]);
    return { profile, gyms };
  }, 'profile-settings');
  return (
    <>
      <BackLink to="/profile" />
      <h1>{t('set.title')}</h1>
      <Async state={state}>
        {(d) => (
          <>
            <Form profile={d.profile} gyms={d.gyms} reload={state.reload} />
            <ExtraGyms profile={d.profile} gyms={d.gyms} reload={state.reload} />
            <Watch p={d.profile} />
          </>
        )}
      </Async>
    </>
  );
}
