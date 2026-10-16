import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { programsApi, type Enrollment, type TodayView } from '../../api/programs';
import { ApiError } from '../../api/client';
import { ChartCanvas } from '../../components/charts';
import { Async, Card, SecTitle } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useFetch } from '../../lib/useFetch';
import { FocusChips } from './describe';
import { Crumbs, ReferenceRow, liftLabel, type LiftNames } from './parts';
import { fmtDay, fmtKg, loc } from './tree';
import { trendChartConfig } from './trend';
import './programs.css';

function TrendBlock({ lift, names }: { lift: string; names: LiftNames }) {
  const { t, lang } = useI18n();
  const st = useFetch(() => programsApi.trend(lift), `pg-trend-${lift}`);
  return (
    <Async state={st}>
      {(d) => {
        const cfg = trendChartConfig(d);
        return d.points.length < 2 ? (
          <div className="mut" style={{ padding: '10px 0' }}>{t('pg.trend_none', { lift: liftLabel(lift, names, lang) })}</div>
        ) : (
          <>
            <div style={{ margin: '4px 0 6px' }}>
              <b>{t(`pg.trend.${d.trend}`)}</b>{' '}
              {d.delta_kg != null && <span className="mut">{d.delta_kg > 0 ? '+' : ''}{fmtKg(d.delta_kg)} {t('pg.kg')}</span>}
              {d.best != null && <span className="mut"> · {t('pg.best')}: {fmtKg(d.best)} {t('pg.kg')}</span>}
            </div>
            <ChartCanvas config={cfg} height={170} />
          </>
        );
      }}
    </Async>
  );
}

function TodayCard({ today }: { today: TodayView }) {
  const { t, lang } = useI18n();
  const s = today.session;
  if (!s) return <div className="msg info">{t(`pg.today.${today.state}`)}</div>;
  return (
    <Card>
      <div className="mut" style={{ fontSize: 12.5 }}>{t(`pg.today.${today.state}`)} · {fmtDay(s.planned_day)}</div>
      <div style={{ fontSize: 17, fontWeight: 700, margin: '2px 0' }}>{loc(s.title, lang)}</div>
      <div className="mut" style={{ fontSize: 13 }}>
        {loc(s.week_title, lang)} · {t('pg.minutes', { n: s.minutes })}
        {s.kind === 'test' && <span className="pg-badge bad" style={{ marginLeft: 8 }}>{t('pg.test_badge')}</span>}
      </div>
      {s.purpose && <div style={{ fontSize: 13.5, margin: '8px 0 2px' }}>{loc(s.purpose, lang)}</div>}
      <FocusChips focus={s.focus} />
      <Link className="btn primary block" style={{ minHeight: 56, marginTop: 10 }} to={`/programs/session/${s.id}`}>
        {s.status === 'in_progress' ? t('pg.continue') : t('pg.to_bench')}
      </Link>
    </Card>
  );
}

function Weeks({ e, weeks }: { e: Enrollment; weeks: { week: number; type: string; title: { ru: string; en: string } }[] }) {
  const { t } = useI18n();
  const cur = e.next_session?.week ?? Number.POSITIVE_INFINITY; // 0 = тест «день 0»
  return (
    <div className="pg-weeks">
      {weeks.map((w) => (
        <div key={w.week} className={`pg-week${w.week === cur ? ' cur' : ''}${w.week < cur ? ' past' : ''}`} title={loc(w.title, 'ru')}>
          {t('pg.week_short', { n: w.week })}
          <small>{t(`pg.week.${w.type}`)}</small>
        </div>
      ))}
    </div>
  );
}

export function EnrollmentScreen() {
  const { id = '' } = useParams();
  const { t, lang } = useI18n();
  const nav = useNavigate();
  const enr = useFetch(() => programsApi.enrollment(id), `pg-enr-${id}`);
  const today = useFetch(() => programsApi.today(id), `pg-today-${id}`);
  const slug = enr.data?.program_slug;
  const card = useFetch(slug ? () => programsApi.program(slug) : null, `pg-enr-card-${slug ?? ''}`);
  const [trendLift, setTrendLift] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const names = useMemo<LiftNames>(() => {
    const m: LiftNames = {};
    for (const l of card.data?.requirements?.lifts ?? []) m[l.lift] = l.name;
    return m;
  }, [card.data]);

  async function act(action: 'pause' | 'resume' | 'cancel') {
    if (action === 'cancel' && !window.confirm(t('pg.cancel_confirm'))) return;
    setBusy(true);
    setMsg(null);
    try {
      await programsApi.setStatus(id, action);
      enr.reload();
      today.reload();
      if (action === 'cancel') nav('/programs');
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.detail : String(e) });
    } finally {
      setBusy(false);
    }
  }
  async function refreshBase() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await programsApi.refreshBase(id);
      enr.reload();
      today.reload();
      const list = (r.refreshed ?? []).map((l) => liftLabel(l, names, lang)).join(', ');
      setMsg({ ok: true, text: list ? t('pg.refreshed', { lifts: list }) : t('pg.refresh_nothing') });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.detail : String(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Async state={enr}>
      {(e) => {
        const done = e.sessions.done ?? 0;
        const total = e.sessions.total || 1;
        const lifts = Object.keys(e.base_maxes);
        const tl = trendLift ?? lifts[0] ?? null;
        return (
          <>
            <Crumbs items={[{ to: '/programs', label: t('pg.title') }, { label: lang === 'en' ? e.title_en ?? '' : e.title_ru ?? '' }]} />
            <h1>{lang === 'en' ? e.title_en || e.title_ru : e.title_ru || e.title_en}</h1>
            <div className="sub">
              <span className={`pg-badge ${e.status === 'active' ? 'ok' : 'warn'}`}>{t(`pg.status.${e.status}`)}</span>{' '}
              {t('pg.since', { day: fmtDay(e.start_day) })}
            </div>
            <div>{t('pg.progress', { done, total: e.sessions.total })}</div>
            <div className="pg-bar" role="progressbar" aria-valuenow={done} aria-valuemax={e.sessions.total}>
              <i style={{ width: `${Math.round((done / total) * 100)}%` }} />
            </div>

            <SecTitle>{t('pg.today_title')}</SecTitle>
            <Async state={today}>{(td) => <TodayCard today={td} />}</Async>

            {card.data?.template && (
              <>
                <SecTitle>{t('pg.calendar')}</SecTitle>
                <Weeks e={e} weeks={card.data.template.weeks} />
              </>
            )}

            <SecTitle>{t('pg.base_title')}</SecTitle>
            <Card>
              {lifts.map((l) => <ReferenceRow key={l} ref_={e.base_maxes[l]} name={liftLabel(l, names, lang)} names={names} />)}
            </Card>
            <button type="button" className="btn block" style={{ minHeight: 52 }} disabled={busy} onClick={() => void refreshBase()}>{t('pg.refresh_base')}</button>
            {msg && <div className={`msg ${msg.ok ? 'ok' : 'err'}`} role="status">{msg.text}</div>}

            {tl && (
              <>
                <SecTitle>{t('pg.trend_title')}</SecTitle>
                <div className="pg-tabs">
                  {lifts.map((l) => (
                    <button key={l} type="button" className={l === tl ? 'on' : ''} onClick={() => setTrendLift(l)}>{liftLabel(l, names, lang)}</button>
                  ))}
                </div>
                <Card><TrendBlock key={tl} lift={tl} names={names} /></Card>
              </>
            )}

            <div className="pg-actions">
              {e.status === 'active' && <button type="button" className="btn" disabled={busy} onClick={() => void act('pause')}>{t('pg.pause')}</button>}
              {e.status === 'paused' && <button type="button" className="btn primary" disabled={busy} onClick={() => void act('resume')}>{t('pg.resume')}</button>}
              {(e.status === 'active' || e.status === 'paused') && (
                <button type="button" className="btn danger" disabled={busy} onClick={() => void act('cancel')}>{t('pg.cancel')}</button>
              )}
            </div>
          </>
        );
      }}
    </Async>
  );
}
