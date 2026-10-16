import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { profileApi, type GymList, type OnboardingStatus, type Profile } from '../../api/profile';
import { ApiError } from '../../api/client';
import { useI18n, useT } from '../../i18n';
import { Loading } from '../../components/ui';
import { useSession } from '../../lib/session';
import { Field, apiMessage } from '../ui5';
import {
  GOALS, LANGS, STEPS, parseFieldErrors, stepsFor, toPatch, validateFields,
  type FieldKey, type FormValues,
} from './validate';
import type { Lang } from '../../api/types';

export function formFromProfile(p: Profile | null): FormValues {
  return {
    nick: p?.nick ?? '',
    height_cm: p?.height_cm != null ? String(p.height_cm) : '',
    weight_kg: p?.weight_kg != null ? String(p.weight_kg) : '',
    sex: p?.sex ?? '',
    age: p?.age != null ? String(p.age) : '',
    gym: p?.gym ?? '',
    goal: p?.goal ?? 'maintain',
    city: p?.city ?? '',
    lang: p?.lang ?? 'ru',
  };
}

export interface ProfileFormProps {
  keys: FieldKey[];
  values: FormValues;
  onChange: (k: FieldKey, v: string) => void;
  errors: Partial<Record<FieldKey, string>>;
  gyms: GymList | null;
}

/** Поля профиля по списку ключей — общие для мастера и экрана «Настройки профиля». */
export function ProfileFields({ keys, values, onChange, errors, gyms }: ProfileFormProps) {
  const t = useT();
  const set = (k: FieldKey) => (e: { target: { value: string } }) => onChange(k, e.target.value);
  const out: ReactNode[] = [];
  for (const k of keys) {
    const err = errors[k];
    switch (k) {
      case 'nick':
        out.push(<Field key={k} label={t('ob.nick')} error={err}><input value={values.nick} maxLength={40} autoComplete="nickname" onChange={set(k)} /></Field>);
        break;
      case 'height_cm':
        out.push(<Field key={k} label={t('ob.height')} error={err}><input inputMode="numeric" value={values.height_cm} onChange={set(k)} /></Field>);
        break;
      case 'weight_kg':
        out.push(<Field key={k} label={t('ob.weight')} error={err}><input inputMode="decimal" value={values.weight_kg} onChange={set(k)} /></Field>);
        break;
      case 'age':
        out.push(<Field key={k} label={t('ob.age')} error={err}><input inputMode="numeric" value={values.age} onChange={set(k)} /></Field>);
        break;
      case 'sex':
        out.push(
          <Field key={k} label={t('ob.sex')} error={err}>
            <select value={values.sex} onChange={set(k)}>
              <option value="">—</option>
              <option value="m">{t('ob.sex.m')}</option>
              <option value="f">{t('ob.sex.f')}</option>
            </select>
          </Field>,
        );
        break;
      case 'gym':
        out.push(
          <Field key={k} label={t('ob.gym')} error={err}>
            <select value={values.gym} onChange={set(k)}>
              <option value="">—</option>
              {(gyms?.gyms ?? []).map((g) => <option key={g.name} value={g.name}>{g.name}</option>)}
              {(gyms?.special ?? ['solo', 'other']).map((s) => <option key={s} value={s}>{t(`ob.gym.${s}`)}</option>)}
            </select>
          </Field>,
        );
        break;
      case 'goal':
        out.push(
          <Field key={k} label={t('ob.goal')} error={err}>
            <select value={values.goal} onChange={set(k)}>
              {GOALS.map((g) => <option key={g} value={g}>{t(`goal.${g}`)}</option>)}
            </select>
          </Field>,
        );
        break;
      case 'city':
        out.push(<Field key={k} label={t('ob.city')} error={err} hint={t('ob.city_hint')}><input value={values.city} maxLength={60} autoComplete="address-level2" onChange={set(k)} /></Field>);
        break;
      case 'lang':
        out.push(
          <Field key={k} label={t('ob.lang')} error={err}>
            <select value={values.lang} onChange={set(k)}>
              {LANGS.map((l) => <option key={l} value={l}>{t(`lang.${l}`)}</option>)}
            </select>
          </Field>,
        );
        break;
    }
  }
  return <>{out}</>;
}

/** Мастер первого входа: показывает только шаги, где чего-то не хватает (+ необязательный последний). */
export function OnboardingWizard({ status, onDone }: { status: OnboardingStatus; onDone: () => void }) {
  const t = useT();
  const { setLang } = useI18n();
  const steps = useMemo(() => stepsFor(status.missing), [status.missing]);
  const [profile, setProfile] = useState<Profile | null | undefined>(undefined);
  const [gyms, setGyms] = useState<GymList | null>(null);
  const [values, setValues] = useState<FormValues>(formFromProfile(null));
  const [step, setStep] = useState(0);
  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    profileApi.profile().then(
      (p) => { if (alive) { setProfile(p); setValues(formFromProfile(p)); } },
      () => { if (alive) setProfile(null); }, // строки users ещё нет
    );
    profileApi.gyms().then((g) => alive && setGyms(g), () => {});
    return () => { alive = false; };
  }, []);

  if (profile === undefined) return <div className="wrap"><Loading /></div>;
  const cur = steps[step] ?? STEPS[STEPS.length - 1];
  const last = step >= steps.length - 1;
  const gymNames = gyms ? [...gyms.gyms.map((g) => g.name), ...gyms.special] : undefined;
  const ranges = { height: status.ranges.height_cm, age: status.ranges.age, weight: status.ranges.weight_kg };

  async function next() {
    // необязательный шаг: пустой город не шлём (сервер требует непустой)
    const keys = cur.optional ? cur.fields.filter((k) => k !== 'city' || values.city.trim() !== '') : cur.fields;
    const ve = validateFields(keys, values, { gyms: gymNames, ranges });
    const shown: Partial<Record<FieldKey, string>> = {};
    for (const [k, e] of Object.entries(ve)) shown[k as FieldKey] = t(e.key, e.params);
    setErrors(shown);
    setGeneral(null);
    if (Object.keys(shown).length) return;
    setBusy(true);
    try {
      await profileApi.patch(toPatch(keys, values) as never);
      if (keys.includes('lang')) setLang(values.lang as Lang);
      if (last) onDone();
      else setStep(step + 1);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        const pf = parseFieldErrors(e);
        setErrors(pf.fields as Partial<Record<FieldKey, string>>);
        setGeneral(pf.general);
      } else setGeneral(apiMessage(e, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="wrap">
      <h1>{t('ob.title')}</h1>
      <div className="sub">{t('ob.step', { n: step + 1, total: steps.length })} · {t(`ob.step.${cur.id}`)}</div>
      <form onSubmit={(e) => { e.preventDefault(); void next(); }} noValidate>
        <ProfileFields
          keys={cur.fields}
          values={values}
          errors={errors}
          gyms={gyms}
          onChange={(k, v) => { setValues((s) => ({ ...s, [k]: v })); setErrors((s) => ({ ...s, [k]: undefined })); }}
        />
        {general && <div className="msg err" role="alert">{general}</div>}
        <div style={{ display: 'flex', gap: 8 }}>
          {step > 0 && <button type="button" className="btn" disabled={busy} onClick={() => setStep(step - 1)}>{t('common.back')}</button>}
          <button type="submit" className="btn primary" style={{ flex: 1 }} disabled={busy}>{last ? t('ob.finish') : t('ob.next')}</button>
        </div>
      </form>
    </div>
  );
}

/** Проверяет `GET /api/onboarding` после входа; если чего-то не хватает — мастер вместо приложения. */
export function OnboardingGate({ children }: { children: ReactNode }) {
  const { refresh } = useSession();
  const [st, setSt] = useState<{ state: 'loading' | 'ok' | 'need'; status?: OnboardingStatus }>({ state: 'loading' });
  useEffect(() => {
    let alive = true;
    profileApi.onboarding().then(
      (s) => alive && setSt(s.complete ? { state: 'ok' } : { state: 'need', status: s }),
      () => alive && setSt({ state: 'ok' }), // не смогли проверить — не блокируем приложение
    );
    return () => { alive = false; };
  }, []);
  if (st.state === 'loading') return <div className="wrap"><Loading /></div>;
  if (st.state === 'need' && st.status) {
    return <OnboardingWizard status={st.status} onDone={() => { void refresh(); setSt({ state: 'ok' }); }} />;
  }
  return <>{children}</>;
}
