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

export function QueueChart() {
  const series = useDashboard((s) => s.queueSeries);
  const data = useMemo(
    () =>
      series.map((p) => ({
        ts: p.ts,
        time: formatClock(p.ts),
        A: p.A,
        B: p.B,
      })),
    [series],
  );

  return (
    <div className="card">
      <div className="px-5 py-3 border-b border-bg-edge flex items-center justify-between">
        <div className="text-sm uppercase tracking-wider text-slate-400">Queue length</div>
        <div className="flex items-center gap-3 text-xs">
          <Legend color="#22c55e" label="A" />
          <Legend color="#60a5fa" label="B" />
        </div>
      </div>
      <div className="h-64 p-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
            <defs>
              <linearGradient id="queueGradA" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="queueGradB" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#60a5fa" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 6" stroke="#1f2a52" />
            <XAxis
              dataKey="time"
              stroke="#475569"
              tick={{ fontSize: 11 }}
              minTickGap={32}
            />
            <YAxis stroke="#475569" tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip
              contentStyle={{
                background: '#0f172a',
                border: '1px solid #1f2a52',
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: '#94a3b8' }}
            />
            <Area
              type="monotone"
              dataKey="A"
              stroke="#22c55e"
              strokeWidth={2.5}
              fill="url(#queueGradA)"
              dot={false}
              isAnimationActive={false}
              style={{ filter: 'drop-shadow(0 0 4px rgba(34,197,94,0.5))' }}
            />
            <Area
              type="monotone"
              dataKey="B"
              stroke="#60a5fa"
              strokeWidth={2.5}
              fill="url(#queueGradB)"
              dot={false}
              isAnimationActive={false}
              style={{ filter: 'drop-shadow(0 0 4px rgba(96,165,250,0.5))' }}
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
