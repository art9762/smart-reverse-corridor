import { useMemo } from 'react';
import { useDashboard, phaseColor } from '../store';
import type { Phase } from '../types';

interface RoadViewProps {
  now: number;
}

const W = 1200;
const H = 320;
const ZONE_X = 220;
const ZONE_W = W - 440;
const ROAD_Y = 140;
const ROAD_H = 80;

/**
 * SVG visualization of the corridor.
 *
 * - Two traffic signals at the entry/exit (A on the left, B on the right).
 * - Cars represented as dots inside the zone, animated based on the active
 *   green phase.
 * - Queue stacks shown as small bars at each side.
 */
export function RoadView({ now }: RoadViewProps) {
  const state = useDashboard((s) => s.state);
  const events = useDashboard((s) => s.recentEvents);
  const phase = state?.phase ?? 'RED_BOTH';
  const phaseRing = phaseColor(phase);

  const cars = useMemo(() => {
    const insideA = state?.inside_A ?? Math.min(events.filter((e) => e.side === 'A' && e.dir === 'in').length, 4);
    const insideB = state?.inside_B ?? 0;
    const total = Math.max(0, insideA + insideB);
    const limited = Math.min(total, 14);
    const movingFromA = phase === 'GREEN_A';
    const movingFromB = phase === 'GREEN_B';
    return Array.from({ length: limited }).map((_, i) => {
      const fromA = i < insideA;
      const baseX = fromA ? ZONE_X + 30 + (i % 7) * 70 : ZONE_X + ZONE_W - 60 - (i % 7) * 70;
      const drift = ((now * 30) % 70) * (movingFromA && fromA ? 1 : movingFromB && !fromA ? -1 : 0);
      const lane = (i % 2 === 0 ? -1 : 1) * 14;
      return {
        x: baseX + drift,
        y: ROAD_Y + ROAD_H / 2 + lane,
        kind: events.find((e) => e.track_id === i)?.class ?? 'car',
      };
    });
  }, [events, now, phase, state]);

  const queueA = state?.queue_A ?? 0;
  const queueB = state?.queue_B ?? 0;

  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-3 border-b border-bg-edge flex items-center justify-between">
        <div className="text-sm uppercase tracking-wider text-slate-400">Corridor live view</div>
        <div className="text-xs text-slate-500 font-mono">
          A inside {state?.inside_A ?? 0} · B inside {state?.inside_B ?? 0}
        </div>
      </div>
      <div className="p-3" data-testid="road-view-container">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className={`w-full h-auto phase-transition rounded-xl bg-gradient-to-b from-slate-950 to-slate-900 ring-1 ring-bg-edge ${
            phaseRing === 'green' ? 'shadow-[0_0_60px_rgba(34,197,94,0.15)]' : ''
          }`}
          role="img"
          aria-label={`Corridor view, phase ${phase}`}
        >
          <defs>
            <linearGradient id="lane" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#1e293b" />
              <stop offset="100%" stopColor="#0f172a" />
            </linearGradient>
          </defs>

          {/* zone shading */}
          <rect
            x={ZONE_X}
            y={ROAD_Y - 10}
            width={ZONE_W}
            height={ROAD_H + 20}
            fill="url(#lane)"
            stroke="#1f2a52"
          />
          {/* dashed center line */}
          <line
            x1={ZONE_X}
            x2={ZONE_X + ZONE_W}
            y1={ROAD_Y + ROAD_H / 2}
            y2={ROAD_Y + ROAD_H / 2}
            stroke="#475569"
            strokeWidth={1.5}
            strokeDasharray="14 12"
          />

          {/* side labels */}
          <SideMarker x={60} label="Side A" sub="ENTRY" align="left" />
          <SideMarker x={W - 60} label="Side B" sub="EXIT" align="right" />

          {/* signals */}
          <Signal x={ZONE_X - 50} y={ROAD_Y - 50} active={signalState(phase, 'A')} side="A" />
          <Signal x={ZONE_X + ZONE_W + 50} y={ROAD_Y - 50} active={signalState(phase, 'B')} side="B" />

          {/* queue stacks */}
          <QueueStack x={ZONE_X - 200} y={ROAD_Y + 30} count={queueA} side="A" />
          <QueueStack x={ZONE_X + ZONE_W + 80} y={ROAD_Y + 30} count={queueB} side="B" />

          {/* cars */}
          {cars.map((c, i) => (
            <Car key={i} x={c.x} y={c.y} kind={c.kind} />
          ))}
        </svg>
      </div>
    </div>
  );
}

function signalState(phase: Phase, side: 'A' | 'B'): 'green' | 'yellow' | 'red' {
  if (phase === 'GREEN_A') return side === 'A' ? 'green' : 'red';
  if (phase === 'GREEN_B') return side === 'B' ? 'green' : 'red';
  if (phase === 'YELLOW_A') return side === 'A' ? 'yellow' : 'red';
  if (phase === 'YELLOW_B') return side === 'B' ? 'yellow' : 'red';
  return 'red';
}

function Signal({
  x,
  y,
  active,
  side,
}: {
  x: number;
  y: number;
  active: 'green' | 'yellow' | 'red';
  side: 'A' | 'B';
}) {
  const lights: Array<'red' | 'yellow' | 'green'> = ['red', 'yellow', 'green'];
  return (
    <g transform={`translate(${x - 20}, ${y})`} aria-label={`Signal ${side}`}>
      <rect width={40} height={120} rx={10} fill="#0b1020" stroke="#1f2a52" />
      {lights.map((l, i) => {
        const on = l === active;
        const fill =
          l === 'green' ? '#22c55e' : l === 'yellow' ? '#eab308' : '#ef4444';
        return (
          <circle
            key={l}
            cx={20}
            cy={20 + i * 40}
            r={13}
            fill={on ? fill : '#1f2937'}
            opacity={on ? 1 : 0.35}
            className={on ? 'phase-transition' : ''}
            style={on ? { filter: `drop-shadow(0 0 8px ${fill})` } : undefined}
          />
        );
      })}
      <text x={20} y={140} textAnchor="middle" fontSize={14} fill="#cbd5e1" fontFamily="monospace">
        {side}
      </text>
    </g>
  );
}

function QueueStack({
  x,
  y,
  count,
  side,
}: {
  x: number;
  y: number;
  count: number;
  side: 'A' | 'B';
}) {
  const items = Math.min(Math.max(count, 0), 18);
  return (
    <g transform={`translate(${x}, ${y})`} aria-label={`Queue ${side}`}>
      {Array.from({ length: items }).map((_, i) => (
        <rect
          key={i}
          x={(side === 'A' ? items - 1 - i : i) * 9}
          y={-Math.abs((i % 3) * 1)}
          width={6}
          height={20}
          rx={1.5}
          fill={count > 12 ? '#ef4444' : count > 6 ? '#eab308' : '#22c55e'}
          opacity={0.85}
        />
      ))}
      <text
        x={side === 'A' ? items * 9 + 6 : -6}
        y={36}
        textAnchor={side === 'A' ? 'start' : 'end'}
        fontSize={14}
        fill="#cbd5e1"
        fontFamily="monospace"
      >
        Q{side}: {count}
      </text>
    </g>
  );
}

function Car({ x, y, kind }: { x: number; y: number; kind: string }) {
  const fill =
    kind === 'emergency'
      ? '#ef4444'
      : kind === 'truck' || kind === 'bus'
        ? '#fbbf24'
        : '#60a5fa';
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect x={-10} y={-6} width={20} height={12} rx={3} fill={fill} stroke="#0f172a" />
      <rect x={-6} y={-3} width={12} height={6} rx={1.5} fill="#0f172a" opacity={0.4} />
    </g>
  );
}

function SideMarker({
  x,
  label,
  sub,
  align,
}: {
  x: number;
  label: string;
  sub: string;
  align: 'left' | 'right';
}) {
  return (
    <g>
      <text
        x={x}
        y={ROAD_Y - 10}
        fill="#94a3b8"
        fontSize={16}
        textAnchor={align === 'left' ? 'start' : 'end'}
        fontFamily="monospace"
      >
        {label}
      </text>
      <text
        x={x}
        y={ROAD_Y + 12}
        fill="#475569"
        fontSize={11}
        textAnchor={align === 'left' ? 'start' : 'end'}
      >
        {sub}
      </text>
    </g>
  );
}
