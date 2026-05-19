import { useMemo } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
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
          <AreaChart data={data} margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
            <defs>
              <linearGradient id="delayGradA" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#f97316" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="delayGradB" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#e879f9" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#e879f9" stopOpacity={0.02} />
              </linearGradient>
            </defs>
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
            <Area
              type="monotone"
              dataKey="A"
              stroke="#f97316"
              strokeWidth={2.5}
              fill="url(#delayGradA)"
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
              style={{ filter: 'drop-shadow(0 0 4px rgba(249,115,22,0.4))' }}
            />
            <Area
              type="monotone"
              dataKey="B"
              stroke="#e879f9"
              strokeWidth={2.5}
              fill="url(#delayGradB)"
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
              style={{ filter: 'drop-shadow(0 0 4px rgba(232,121,249,0.4))' }}
            />
          </AreaChart>
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
