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
 * Throughput chart — vehicles per hour for each direction.
 * The MQTT contract reports `throughput_5min`; we extrapolate to vph
 * (multiply by 12) so demo numbers read naturally.
 */
export function ThroughputChart() {
  const series = useDashboard((s) => s.throughputSeries);
  const data = useMemo(
    () =>
      series.map((p) => ({
        ts: p.ts,
        time: formatClock(p.ts),
        A: Math.round(p.A * 12),
        B: Math.round(p.B * 12),
      })),
    [series],
  );

  return (
    <div className="card">
      <div className="px-5 py-3 border-b border-bg-edge flex items-center justify-between">
        <div className="text-sm uppercase tracking-wider text-slate-400">Throughput (vph)</div>
        <div className="flex items-center gap-3 text-xs">
          <Legend color="#22c55e" label="A" />
          <Legend color="#a78bfa" label="B" />
        </div>
      </div>
      <div className="h-64 p-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
            <defs>
              <linearGradient id="thrGradA" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="thrGradB" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#a78bfa" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 6" stroke="#1f2a52" />
            <XAxis
              dataKey="time"
              stroke="#475569"
              tick={{ fontSize: 11 }}
              minTickGap={32}
            />
            <YAxis stroke="#475569" tick={{ fontSize: 11 }} />
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
              fill="url(#thrGradA)"
              dot={false}
              isAnimationActive={false}
              style={{ filter: 'drop-shadow(0 0 4px rgba(34,197,94,0.4))' }}
            />
            <Area
              type="monotone"
              dataKey="B"
              stroke="#a78bfa"
              strokeWidth={2.5}
              fill="url(#thrGradB)"
              dot={false}
              isAnimationActive={false}
              style={{ filter: 'drop-shadow(0 0 4px rgba(167,139,250,0.4))' }}
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
