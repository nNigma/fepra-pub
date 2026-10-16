import { useEffect, useReducer, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ApiError } from '../../api/client';
import { mealsApi, type Meal, type MealParseResult } from '../../api/meals';
import { Async } from '../../components/ui';
import { useT } from '../../i18n';
import { runJob, useCancelFlag } from '../../lib/runJob';
import { useFetch } from '../../lib/useFetch';
import { BackLink, ProGate, apiMessage, todayIso } from '../ui5';
import { DraftEditor } from './DraftEditor';
import { draftReducer, initialDraft, totalsOf } from './draft';

function Editor({ meal, day }: { meal: Meal; day: string }) {
  const t = useT();
  const nav = useNavigate();
  const cancel = useCancelFlag();
  const [s, dispatch] = useReducer(draftReducer, undefined, () => initialDraft(meal.uuid ?? undefined));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    dispatch({
      type: 'load',
      draft: { foods: meal.foods, totals: totalsOf(meal.foods), quality: meal.quality, quality_note: meal.quality_note },
      source: { kind: meal.photo_url ? 'photo' : 'text', text: meal.note, url: meal.photo_url, meal_id: meal.id },
    });
  }, [meal]);
  const back = () => nav(`/meals${day === todayIso() ? '' : `?day=${day}`}`);

  async function reparse(correction: string) {
    setBusy(true);
    setErr(null);
    try {
      const res = await runJob<MealParseResult>(() => mealsApi.reparse(meal.id, { correction, notes: s.notes }), { signal: cancel });
      dispatch({ type: 'parsed', result: res, correction });
      if (!res.recognized) setErr(t(`meal.reason.${res.reason ?? 'not_recognized'}`));
    } catch (e) {
      setErr(apiMessage(e, t));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setErr(null);
    try {
      await mealsApi.update(meal.id, { draft: s.draft!, day });
      back();
    } catch (e) {
      setErr(apiMessage(e, t));
      setBusy(false);
    }
  }
  async function remove() {
    if (!window.confirm(t('meal.delete_confirm'))) return;
    setBusy(true);
    try {
      await mealsApi.remove(meal.id);
      back();
    } catch (e) {
      setErr(apiMessage(e, t));
      setBusy(false);
    }
  }
  return (
    <>
      <div className="sub">{meal.day} · {meal.ts.slice(11, 16)}</div>
      {meal.photo_url && <img src={meal.photo_url} alt="" style={{ width: '100%', maxHeight: 240, objectFit: 'cover', borderRadius: 12, marginBottom: 12 }} />}
      <DraftEditor state={s} dispatch={dispatch} busy={busy} onCorrect={(c) => void reparse(c)} onSave={() => void save()} saveLabel={t('meal.save_changes')} />
      {err && <div className="msg err" role="alert">{err}</div>}
      <button type="button" className="btn danger block" style={{ marginTop: 12 }} disabled={busy} onClick={() => void remove()}>{t('meal.delete')}</button>
    </>
  );
}

export function MealEditScreen() {
  const t = useT();
  const { id = '' } = useParams();
  const [sp] = useSearchParams();
  const day = sp.get('day') || todayIso();
  const state = useFetch(async () => {
    const d = await mealsApi.day(day);
    const m = d.meals.find((x) => String(x.id) === id);
    if (!m) throw new ApiError(404, '');
    return m;
  }, `meal:${id}:${day}`);
  return (
    <>
      <BackLink to={`/meals?day=${day}`} />
      <h1>{t('meal.edit')}</h1>
      <ProGate>
        <Async state={state}>{(m) => <Editor meal={m} day={day} />}</Async>
      </ProGate>
    </>
  );
}
