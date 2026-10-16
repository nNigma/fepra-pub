import { useEffect, useRef } from 'react';
import {
  BarController, BarElement, CategoryScale, Chart, Filler, LineController, LineElement,
  LinearScale, PointElement, Tooltip, type ChartConfiguration,
} from 'chart.js';
import { useT } from '../i18n';
import { fmt } from '../lib/format';
import type { SeriesPoint } from '../api/types';

Chart.register(
  LineController, BarController, LineElement, BarElement, PointElement,
  CategoryScale, LinearScale, Tooltip, Filler,
);

/** Chart.js в canvas: пересоздаётся при смене конфига, уничтожается при размонтировании. */
export function ChartCanvas({ config, height }: { config: ChartConfiguration; height: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let chart: Chart | null = null;
    try {
      const mut = getComputedStyle(document.documentElement).getPropertyValue('--mut').trim();
      if (mut) Chart.defaults.color = mut;
      chart = new Chart(el, config);
    } catch {
      /* canvas недоступен (тесты) */
    }
    return () => chart?.destroy();
  }, [config]);
  return (
    <div style={{ position: 'relative', height }}>
      <canvas ref={ref} />
    </div>
  );
}

/** Линия места по стартам/раундам (ось Y перевёрнута: 1 — сверху). */
export function placeChartConfig(labels: string[], places: (number | null)[]): ChartConfiguration {
  return {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: places, borderColor: '#1D9E75', backgroundColor: 'rgba(29,158,117,.15)',
        tension: 0.3, pointRadius: 5, pointBackgroundColor: '#1D9E75',
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { y: { reverse: true, min: 1, ticks: { stepSize: 1, font: { size: 10 } } }, x: { ticks: { font: { size: 11 } } } },
    },
  };
}

/** Готовность (линия) + нагрузка (столбцы) за 30 дней. */
export function readinessChartConfig(rows: [string, number, number, number, number][]): ChartConfiguration {
  return {
    type: 'bar',
    data: {
      labels: rows.map((r) => r[0].slice(5)),
      datasets: [
        { type: 'bar', data: rows.map((r) => r[3]), backgroundColor: '#888780', yAxisID: 'y1', order: 2 },
        {
          type: 'line', data: rows.map((r) => r[1]), borderColor: '#1D9E75', backgroundColor: '#1D9E75',
          tension: 0.3, pointRadius: 1.5, yAxisID: 'y', order: 1,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: {
        y: { position: 'left', min: 0, max: 100, ticks: { font: { size: 10 } } },
        y1: { position: 'right', min: 0, grid: { drawOnChartArea: false }, ticks: { font: { size: 10 } } },
        x: { ticks: { font: { size: 9 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 9 } },
      },
    },
  } as unknown as ChartConfiguration;
}

/** SVG-график метрики с закраской «плохой» зоны относительно базы (порт старого metricChartSvg). */
export function MetricChart({ series, base, dir, sparse }: { series: SeriesPoint[]; base?: number | null; dir?: string; sparse?: boolean }) {
  const t = useT();
  const n = series?.length ?? 0;
  if (!series || n < (sparse ? 1 : 2))
    return <div className="mut" style={{ fontSize: 12, padding: '6px 0' }}>{t('chart.no_data')}</div>;
  const w = 320, h = 112, x1 = w - 6, y1 = h - 16;
  const x0 = sparse ? 14 : 24, y0 = sparse ? 20 : 8;
  const vals = series.map((p) => p[1]);
  const rawLo = Math.min(...vals), rawHi = Math.max(...vals);
  let lo = rawLo, hi = rawHi;
  if (base != null) { lo = Math.min(lo, base); hi = Math.max(hi, base); }
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.12;
  lo -= pad; hi += pad;
  let X: (i: number) => number;
  if (sparse) {
    const t0 = Date.parse(series[0][0]);
    const span = Date.parse(series[n - 1][0]) - t0 || 1;
    X = (i) => x0 + 10 + ((Date.parse(series[i][0]) - t0) / span) * (x1 - x0 - 20);
  } else {
    X = (i) => x0 + (i / (n - 1)) * (x1 - x0);
  }
  const Y = (v: number) => y1 - ((v - lo) / (hi - lo)) * (y1 - y0);
  const yb = base != null ? Y(base) : null;
  let area = '';
  if (yb != null) {
    const yBad = (v: number) => (dir === 'high_bad' ? Math.min(Y(v), yb) : Math.max(Y(v), yb));
    let d = `M ${X(0).toFixed(1)} ${yb.toFixed(1)}`;
    for (let i = 0; i < n; i++) d += ` L ${X(i).toFixed(1)} ${yBad(series[i][1]).toFixed(1)}`;
    d += ` L ${X(n - 1).toFixed(1)} ${yb.toFixed(1)} Z`;
    area = d;
  }
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%' }} role="img">
      {area && <path d={area} fill="var(--red)" opacity=".2" />}
      {yb != null && (
        <>
          <line x1={x0} y1={yb} x2={x1} y2={yb} stroke="var(--mut)" strokeWidth="1" strokeDasharray="4 3" />
          <text x={x1} y={yb - 3} fontSize="9" fill="var(--mut)" textAnchor="end">{t('chart.bench', { base: base })}</text>
        </>
      )}
      {series.slice(0, -1).map((p, i) => (
        <line key={i} x1={X(i)} y1={Y(p[1])} x2={X(i + 1)} y2={Y(series[i + 1][1])} stroke="var(--tx)" strokeWidth="1.6" opacity=".82" />
      ))}
      {sparse && n <= 12
        ? series.map((p, i) => (
            <g key={i}>
              <circle cx={X(i)} cy={Y(p[1])} r="3" fill="var(--tx)" />
              <text x={X(i)} y={Y(p[1]) - 8} fontSize="10.5" fontWeight="600" fill="var(--tx)" textAnchor="middle">{fmt(p[1])}</text>
              <text x={X(i)} y={h - 3} fontSize="9" fill="var(--mut)" textAnchor="middle">{p[0].slice(5)}</text>
            </g>
          ))
        : (
          <>
            <text x="2" y={Y(rawHi) + 3} fontSize="9" fill="var(--mut)">{fmt(rawHi)}</text>
            <text x="2" y={Y(rawLo) + 3} fontSize="9" fill="var(--mut)">{fmt(rawLo)}</text>
            <text x={x0} y={h - 3} fontSize="9" fill="var(--mut)">{series[0][0].slice(5)}</text>
            <text x={x1} y={h - 3} fontSize="9" fill="var(--mut)" textAnchor="end">{series[n - 1][0].slice(5)}</text>
          </>
        )}
    </svg>
  );
}

/** Два ряда на одном графике (глубокий сон и REM). */
export function OverlayChart({ a, b, labA, labB, baseA, baseB }: {
  a: SeriesPoint[]; b: SeriesPoint[]; labA: string; labB: string; baseA?: number | null; baseB?: number | null;
}) {
  const t = useT();
  const ca = a.filter((p) => p[1] != null), cb = b.filter((p) => p[1] != null);
  if (ca.length < 2 && cb.length < 2)
    return <div className="mut" style={{ fontSize: 12, padding: '6px 0' }}>{t('chart.no_data')}</div>;
  const w = 320, h = 112, x1 = w - 6, y1 = h - 16, x0 = 24, y0 = 8;
  const all = ca.concat(cb).map((p) => p[1]).concat([baseA, baseB].filter((v): v is number => v != null));
  let lo = Math.min(...all), hi = Math.max(...all);
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.12;
  lo -= pad; hi += pad;
  const ds = [...new Set(ca.concat(cb).map((p) => p[0]))].sort();
  const t0 = Date.parse(ds[0]);
  const span = Date.parse(ds[ds.length - 1]) - t0 || 1;
  const X = (d: string) => x0 + ((Date.parse(d) - t0) / span) * (x1 - x0);
  const Y = (v: number) => y1 - ((v - lo) / (hi - lo)) * (y1 - y0);
  const cA = '#378ADD', cB = '#4aaa99';
  const line = (s: SeriesPoint[], col: string) =>
    s.slice(0, -1).map((p, i) => <line key={i} x1={X(p[0])} y1={Y(p[1])} x2={X(s[i + 1][0])} y2={Y(s[i + 1][1])} stroke={col} strokeWidth="1.8" />);
  const baseLine = (base: number | null | undefined, col: string) =>
    base == null ? null : <line x1={x0} y1={Y(base)} x2={x1} y2={Y(base)} stroke={col} strokeWidth="1" strokeDasharray="4 3" opacity=".6" />;
  return (
    <>
      <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%' }} role="img">
        {baseLine(baseA, cA)}{baseLine(baseB, cB)}{line(ca, cA)}{line(cb, cB)}
        <text x="2" y={Y(hi - pad) + 3} fontSize="9" fill="var(--mut)">{fmt(hi - pad)}</text>
        <text x="2" y={Y(lo + pad) + 3} fontSize="9" fill="var(--mut)">{fmt(lo + pad)}</text>
      </svg>
      <div style={{ display: 'flex', gap: 14, justifyContent: 'center', fontSize: 11, marginTop: 2 }}>
        <span><span style={{ display: 'inline-block', width: 10, height: 3, background: cA, verticalAlign: 'middle' }} /> {labA}</span>
        <span><span style={{ display: 'inline-block', width: 10, height: 3, background: cB, verticalAlign: 'middle' }} /> {labB}</span>
      </div>
    </>
  );
}
