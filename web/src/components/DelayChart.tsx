import { useMemo } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useDashboard } from '../store';
import { formatClock } from '../lib/format';

/**
 * Average delay chart — 5-minute rolling average delay in seconds per vehicle,
 * for each side (A and B).
 */
export function DelayChart() {
  const series = useDashboard((s) => s.delaySeries);
  const data = useMemo(
    () =>
      series.map((p) => ({
        ts: p.ts,
        time: formatClock(p.ts),
        A: Number.isFinite(p.A) ? Math.round(p.A * 10) / 10 : null,
        B: Number.isFinite(p.B) ? Math.round(p.B * 10) / 10 : null,
      })),
    [series],
  );

  return (
    <div className="card">
      <div className="px-5 py-3 border-b border-bg-edge flex items-center justify-between">
        <div className="text-sm uppercase tracking-wider text-slate-400">Avg delay (s)</div>
        <div className="flex items-center gap-3 text-xs">
          <Legend color="#f97316" label="A" />
          <Legend color="#e879f9" label="B" />
        </div>
      </div>
      <div className="h-64 p-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 6" stroke="#1f2a52" />
            <XAxis
              dataKey="time"
              stroke="#475569"
              tick={{ fontSize: 11 }}
              minTickGap={32}
            />
            <YAxis stroke="#475569" tick={{ fontSize: 11 }} unit="s" />
            <Tooltip
              contentStyle={{
                background: '#0f172a',
                border: '1px solid #1f2a52',
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: '#94a3b8' }}
              formatter={(value: unknown) => {
                const n = typeof value === 'number' ? value : null;
                return n === null ? ['—', ''] : [`${n}s`, ''];
              }}
            />
            <Line
              type="monotone"
              dataKey="A"
              stroke="#f97316"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
            <Line
              type="monotone"
              dataKey="B"
              stroke="#e879f9"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-slate-400">
      <span className="w-2 h-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}
