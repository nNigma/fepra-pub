import { useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  NeedsInputError, localToday, newId, programsApi, type ProgramCardData, type Reference, type StartLevel,
} from '../../api/programs';
import { ApiError } from '../../api/client';
import { Async, Card, SecTitle } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useFetch } from '../../lib/useFetch';
import { availableLevels, buildEnrollBody, isEnrollReady, LEVELS, parseKg } from './enrollForm';
import { Crumbs, ReferenceRow, liftLabel, type LiftNames } from './parts';
import { AboutBlocks, DayInfo } from './describe';
import { fmtKg, loc, nodeTitle, pathTo } from './tree';
import './programs.css';

const WEEK_BADGE: Record<string, string> = { volume: '', medium: '', high: 'warn', deload: 'ok', test: 'bad' };

function EnrollBox({ card, names }: { card: ProgramCardData; names: LiftNames }) {
  const { t, lang } = useI18n();
  const nav = useNavigate();
  const req = card.requirements;
  const idRef = useRef(newId());
  const [serverItems, setServerItems] = useState<Record<string, Reference> | null>(null);
  const [startDay, setStartDay] = useState(localToday());
  const [level, setLevel] = useState<StartLevel | null>(null);
  const [manual, setManual] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refByLift = useMemo(() => {
    const m: Record<string, Reference> = {};
    for (const l of req?.lifts ?? []) m[l.lift] = l.reference;
    return { ...m, ...(serverItems ?? {}) };
  }, [req, serverItems]);
  const ask = serverItems ? Object.keys(serverItems) : req?.needs_input ?? [];
  const levels = availableLevels(ask.map((l) => refByLift[l]).filter(Boolean));
  const state = { startDay, level, manual, id: idRef.current };
  const ready = isEnrollReady(ask, state);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const e = await programsApi.enroll(card.slug, buildEnrollBody(state));
      nav(`/programs/my/${e.id}`);
    } catch (err) {
      if (err instanceof NeedsInputError) setServerItems(err.items); // 422: показываем вопросы из items
      else if (err instanceof ApiError && err.status === 409) setError(err.code === 'unavailable' ? t('pg.err_soon') : t('pg.err_already'));
      else setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      {ask.length > 0 && (
        <>
          <b>{t('pg.need_title')}</b>
          <div className="mut" style={{ fontSize: 13, margin: '2px 0 8px' }}>{t('pg.need_hint')}</div>
          {serverItems && <div className="msg info" role="status">{t('pg.need_server')}</div>}
          {levels.length > 0 && (
            <div className="pg-levels" role="radiogroup" aria-label={t('pg.level_title')}>
              {LEVELS.filter((lv) => levels.includes(lv)).map((lv) => (
                <button key={lv} type="button" role="radio" aria-checked={level === lv} className={`pg-level${level === lv ? ' on' : ''}`}
                  onClick={() => setLevel(level === lv ? null : lv)}>
                  <b>{t(`pg.level.${lv}`)}</b>
                  {ask.map((l) => (refByLift[l]?.options?.[lv] != null
                    ? <small key={l}>{liftLabel(l, names, lang)}: {fmtKg(refByLift[l]?.options?.[lv])} {t('pg.kg')}</small> : null))}
                </button>
              ))}
            </div>
          )}
          <div className="mut" style={{ fontSize: 13 }}>{levels.length > 0 ? t('pg.or_manual') : t('pg.no_profile')}</div>
          {ask.map((l) => (
            <label key={l} className="field" style={{ marginTop: 8 }}>
              <span>{refByLift[l]?.question ? loc(refByLift[l]?.question, lang) : t('pg.max_of', { lift: liftLabel(l, names, lang) })}</span>
              <input inputMode="decimal" placeholder={t('pg.kg')} value={manual[l] ?? ''}
                aria-invalid={manual[l] ? parseKg(manual[l]) == null : undefined}
                onChange={(e) => setManual({ ...manual, [l]: e.target.value })} />
            </label>
          ))}
          <div className="mut" style={{ fontSize: 12.5, marginBottom: 10 }}>{t('pg.estimate_hint')}</div>
        </>
      )}
      {req && req.needs_test.length > 0 && (
        <div className="msg info" role="note">
          {t('pg.first_is_test', { lifts: req.needs_test.map((l) => liftLabel(l, names, lang)).join(', ') })}
        </div>
      )}
      <label className="field">
        <span>{t('pg.start_day')}</span>
        <input type="date" value={startDay} onChange={(e) => setStartDay(e.target.value)} />
      </label>
      {error && <div className="msg err" role="alert">{error}</div>}
      <button type="button" className="btn primary block" style={{ minHeight: 56 }} disabled={busy || !ready} onClick={() => void submit()}>
        {busy ? t('common.loading') : t('pg.start')}
      </button>
    </Card>
  );
}

export function ProgramCardScreen() {
  const { slug = '' } = useParams();
  const { t, lang } = useI18n();
  const card = useFetch(() => programsApi.program(slug), `pg-card-${slug}`);
  const tree = useFetch(() => programsApi.tree(), 'pg-tree');
  return (
    <Async state={card}>
      {(c) => {
        const tpl = c.template;
        const names: LiftNames = {};
        for (const l of c.requirements?.lifts ?? []) names[l.lift] = l.name;
        const crumbs: { to?: string; label: string }[] = [
          { to: '/programs', label: t('pg.title') },
          ...pathTo(tree.data ?? [], slug).map((n, i, a) => ({ to: i < a.length - 1 ? `/programs/node/${n.slug}` : undefined, label: nodeTitle(n, lang) })),
        ];
        if (crumbs.length === 1) crumbs.push({ label: lang === 'en' ? c.title_en : c.title_ru });
        return (
          <>
            <Crumbs items={crumbs} />
            <h1>{tpl ? loc(tpl.title, lang) : lang === 'en' ? c.title_en : c.title_ru}</h1>
            {tpl && <div className="sub">{loc(tpl.summary, lang)}</div>}
            {c.soon && <div className="pg-stub">{t('pg.filling_text')}</div>}
            {tpl && (
              <div style={{ marginBottom: 8 }}>
                <span className="sp">{t('pg.weeks_n', { n: tpl.params.weeks })}</span>
                {tpl.params.days_per_week && <span className="sp">{t('pg.days_per_week', { n: tpl.params.days_per_week.join('–') })}</span>}
                {tpl.params.session_minutes && <span className="sp">{t('pg.minutes', { n: tpl.params.session_minutes.join('–') })}</span>}
              </div>
            )}
            {tpl?.about && tpl.about.length > 0 && (
              <>
                <SecTitle>{t('pg.about')}</SecTitle>
                <AboutBlocks blocks={tpl.about} />
              </>
            )}
            {c.enrollment_id && (
              <Link className="btn primary block" style={{ minHeight: 56, marginBottom: 10 }} to={`/programs/my/${c.enrollment_id}`}>{t('pg.open_enrollment')}</Link>
            )}
            {c.requirements && (
              <>
                <SecTitle>{t('pg.lifts_title')}</SecTitle>
                <Card>
                  {c.requirements.lifts.map((l) => (
                    <ReferenceRow key={l.lift} ref_={l.reference} name={`${loc(l.name, lang)}${l.required ? '' : ` (${t('pg.optional')})`}`} names={names} />
                  ))}
                </Card>
              </>
            )}
            {tpl && (
              <>
                <SecTitle>{t('pg.structure')}</SecTitle>
                <div className="mut" style={{ fontSize: 13, marginBottom: 6 }}>{t('pg.structure_hint')}</div>
                <div className="pg-about">
                  {tpl.weeks.map((w) => {
                    const wt = tpl.week_types?.[w.type];
                    return (
                      <details key={w.week} className="pg-det">
                        <summary>
                          <span>{loc(w.title, lang)}</span>
                          <span><span className={`pg-badge ${WEEK_BADGE[w.type] ?? ''}`}>{t(`pg.week.${w.type}`)}</span> · {t('pg.sessions_n', { n: w.sessions })}</span>
                        </summary>
                        {w.note && <p>{loc(w.note, lang)}</p>}
                        {wt && <p className="mut"><b>{loc(wt.title, lang)}.</b> {loc(wt.text, lang)}</p>}
                        {(w.days ?? []).map((d) => <DayInfo key={d.idx} d={d} />)}
                      </details>
                    );
                  })}
                </div>
              </>
            )}
            {!c.soon && !c.enrollment_id && c.requirements && <EnrollBox card={c} names={names} />}
          </>
        );
      }}
    </Async>
  );
}
