import { AXES_KEYS, AXES_T_KEYS } from '../lib/format';
import { useT } from '../i18n';
import type { MusclesInfo, RadarSet } from '../api/types';
import body from '../data/body.json';

interface BodyData {
  viewFront: string;
  viewBack: string;
  front: { s: string; p: string[] }[];
  back: { s: string; p: string[] }[];
}
const BODY = body as BodyData;

const MUSCLE_SLUGS: Record<string, string> = {
  deltoids: 'shoulders', trapezius: 'traps', chest: 'chest', biceps: 'biceps', triceps: 'triceps',
  forearm: 'forearms', abs: 'abs', obliques: 'obliques', 'upper-back': 'upper_back', 'lower-back': 'lower_back',
  gluteal: 'glutes', quadriceps: 'quads', hamstring: 'hamstrings', adductors: 'adductors', calves: 'calves',
};
const MUSCLE_SEC = '#f5b83d';

function BodySvg({ parts, view, m }: { parts: BodyData['front']; view: string; m: MusclesInfo }) {
  const prim = new Set(m.primary ?? []), sec = new Set(m.secondary ?? []), inten = m.intensity ?? {};
  return (
    <svg viewBox={view} style={{ height: 195 }} role="img" aria-hidden="true">
      {parts.map((pt, i) => {
        const g = MUSCLE_SLUGS[pt.s];
        let fill = 'var(--bd)', op: number | string = 1;
        if (g && (prim.has(g) || sec.has(g))) {
          fill = prim.has(g) ? 'var(--red)' : MUSCLE_SEC;
          op = (0.35 + 0.65 * (inten[g] ?? 0)).toFixed(2);
        }
        return pt.p.map((d, j) => <path key={`${i}-${j}`} d={d} fill={fill} opacity={op} />);
      })}
    </svg>
  );
}

export function MuscleMap({ m }: { m: MusclesInfo }) {
  const t = useT();
  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 22 }}>
        <BodySvg parts={BODY.front} view={BODY.viewFront} m={m} />
        <BodySvg parts={BODY.back} view={BODY.viewBack} m={m} />
      </div>
      <div className="leg" style={{ justifyContent: 'center', margin: '8px 0 0' }}>
        <span><span className="sw" style={{ background: 'var(--red)' }} />{t('muscles.legend_primary')}</span>
        <span><span className="sw" style={{ background: MUSCLE_SEC }} />{t('muscles.legend_secondary')}</span>
        <span><span className="sw" style={{ background: 'var(--bd)' }} />{t('muscles.legend_idle')}</span>
      </div>
    </>
  );
}

const PALETTE = [
  { stroke: '#1D9E75', fill: 'rgba(29,158,117,.18)', dash: '', width: 2.2 },
  { stroke: '#EF9F27', fill: 'rgba(239,159,39,.12)', dash: '4 3', width: 1.8 },
  { stroke: '#378ADD', fill: 'rgba(55,138,221,.12)', dash: '2 3', width: 1.8 },
];

/** Радар по 6 осям; один или несколько наборов (сравнение стартов). */
export function Radar({ sets }: { sets: RadarSet[] }) {
  const t = useT();
  const axes = AXES_KEYS;
  const cx = 110, cy = 110, R = 80, n = axes.length;
  const ang = (i: number) => ((-90 + i * (360 / n)) * Math.PI) / 180;
  const pt = (i: number, r: number): [number, number] => [cx + r * Math.cos(ang(i)), cy + r * Math.sin(ang(i))];
  const poly = (pts: [number, number][]) => pts.map((p) => p.join(',')).join(' ');
  const grid = axes.map((_, i) => pt(i, R));
  const inner = axes.map((_, i) => pt(i, R * 0.5));
  const labels = axes.map((_, i) => pt(i, R + 18));
  const anchor = (i: number) => (labels[i][0] < cx - 4 ? 'end' : labels[i][0] > cx + 4 ? 'start' : 'middle');
  return (
    <div style={{ background: 'var(--card)', border: '1px solid var(--bd)', borderRadius: 12, padding: '14px 8px 10px' }}>
      <svg viewBox="-40 0 300 220" style={{ width: '100%', maxWidth: 300, display: 'block', margin: '0 auto' }} role="img">
        <polygon points={poly(grid)} fill="none" stroke="var(--bd)" />
        <polygon points={poly(inner)} fill="none" stroke="var(--bd)" />
        {axes.map((_, i) => <line key={i} x1={cx} y1={cy} x2={grid[i][0]} y2={grid[i][1]} stroke="var(--bd)" />)}
        {sets.map((r, ri) => {
          const c = PALETTE[Math.min(ri, PALETTE.length - 1)];
          const pts = axes.map((a, i) => pt(i, ((r.grades[a] ?? 0) / 9) * R));
          return <polygon key={ri} points={poly(pts)} fill={c.fill} stroke={c.stroke} strokeWidth={c.width} strokeDasharray={c.dash || undefined} />;
        })}
        {axes.map((_, i) => (
          <text key={i} x={labels[i][0]} y={labels[i][1] + 4} fontSize="9.5" fill="var(--mut)" textAnchor={anchor(i)}>{t(AXES_T_KEYS[i])}</text>
        ))}
      </svg>
      {sets.length > 1 || sets[0]?.name ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px 16px', justifyContent: 'center', marginTop: 8 }}>
          {sets.map((r, ri) => {
            const c = PALETTE[Math.min(ri, PALETTE.length - 1)];
            return (
              <div key={ri} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 16, height: 0, borderTop: `2px ${c.dash ? 'dashed' : 'solid'} ${c.stroke}` }} />
                <span style={{ fontSize: 11, opacity: 0.8 }}>{r.name}{r.date ? ` · ${r.date.slice(5)}` : ''}</span>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

/** Пульс по времени, цвет по зоне. */
export function HrLine({ series, hrMax }: { series: [number, number][]; hrMax: number }) {
  const t = useT();
  if (!series || series.length < 2) return null;
  const hm = hrMax || 184, x0 = 30, x1 = 336, y0 = 18, y1 = 128;
  const maxT = series[series.length - 1][0] || 1;
  const lo = 50, hi = Math.max(hm, ...series.map((p) => p[1])) + 5;
  const X = (s: number) => x0 + (s / maxT) * (x1 - x0);
  const Y = (hr: number) => y1 - ((hr - lo) / (hi - lo)) * (y1 - y0);
  const zc = ['var(--mut)', '#378ADD', '#4aaa99', 'var(--amber)', 'var(--red)'];
  const zn = (hr: number) => (hr < 0.6 * hm ? 0 : hr < 0.7 * hm ? 1 : hr < 0.8 * hm ? 2 : hr < 0.9 * hm ? 3 : 4);
  const y120 = Y(120);
  const mn = Math.round(maxT / 60);
  const tlab = mn >= 60 ? `${Math.floor(mn / 60)}:${String(mn % 60).padStart(2, '0')}` : `${mn} ${t('common.min')}`;
  return (
    <svg viewBox="0 0 360 150" style={{ width: '100%' }} role="img">
      <line x1={x0} y1={y120} x2={x1} y2={y120} stroke="var(--tx)" opacity=".35" />
      <text x={x1} y={y120 - 3} fontSize="9" fill="var(--mut)" textAnchor="end">120</text>
      {series.slice(0, -1).map((a, i) => (
        <line key={i} x1={X(a[0])} y1={Y(a[1])} x2={X(series[i + 1][0])} y2={Y(series[i + 1][1])} stroke={zc[zn(a[1])]} strokeWidth="1.8" />
      ))}
      <text x={x0} y="146" fontSize="9" fill="var(--mut)">0:00</text>
      <text x={x1} y="146" fontSize="9" fill="var(--mut)" textAnchor="end">{tlab}</text>
    </svg>
  );
}
