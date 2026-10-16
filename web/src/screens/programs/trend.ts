import type { ChartConfiguration } from 'chart.js';
import type { TrendData } from '../../api/programs';

export function trendChartConfig(data: TrendData): ChartConfiguration {
  return {
    type: 'line',
    data: {
      labels: data.points.map((p) => `${p.day.slice(8, 10)}.${p.day.slice(5, 7)}`),
      datasets: [{
        data: data.points.map((p) => p.kg),
        borderColor: '#1D9E75', backgroundColor: 'rgba(29,158,117,.15)', fill: true,
        tension: 0.25, pointRadius: 5, pointBackgroundColor: '#1D9E75',
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { y: { ticks: { font: { size: 11 } } }, x: { ticks: { font: { size: 11 } } } },
    },
  };
}
