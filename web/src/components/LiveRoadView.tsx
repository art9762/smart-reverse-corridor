import { useMemo } from 'react';
import { useDashboard, phaseRemaining } from '../store';
import type { Phase, VehicleType, WorldVehicle } from '../types';

interface LiveRoadViewProps {
  now: number;
}

const W = 1200;
const H = 280;
const ZONE_X = 80;
const ZONE_W = W - 160;
const ROAD_Y = 120;
const ROAD_H = 80;
const REPAIR_X = ZONE_X + ZONE_W * 0.42;
const REPAIR_W = ZONE_W * 0.18;
const MIN_CAR_PX = 14;
const MAX_CAR_PX = 70;

const COLORS: Record<VehicleType, string> = {
  car: '#3b82f6', // blue-500
  truck: '#f97316', // orange-500
  bus: '#14b8a6', // teal-500
  motorcycle: '#06b6d4', // cyan-500
  emergency: '#ef4444', // red-500
};

/**
 * Live corridor visualization driven by `corridor/sim/world` snapshots.
 *
 * - Renders the road, repair zone, both signals (with countdown from
 *   `corridor/state`), and every vehicle from `worldSnapshot.vehicles`.
 * - Vehicle x is normalized [0..1] across the zone; length scales from
 *   `len_m` relative to `zone_length_m`.
 * - Smooth 80ms CSS transition on the transform of every car for a
 *   buttery 10–20 Hz feed without snap.
 * - Falls back to a "Waiting for simulator…" overlay while
 *   `worldSnapshot === null`.
 */
export function LiveRoadView({ now }: LiveRoadViewProps) {
  const snapshot = useDashboard((s) => s.worldSnapshot);
  const corridor = useDashboard((s) => s.state);

  const phase: Phase = snapshot?.phase ?? corridor?.phase ?? 'RED_BOTH';
  const remaining = phaseRemaining(corridor, now);

  const vehicles = snapshot?.vehicles ?? [];
  const zoneLengthM = snapshot?.zone_length_m ?? 800;

  const queueA = snapshot?.queues.A ?? corridor?.queue_A ?? 0;
  const queueB = snapshot?.queues.B ?? corridor?.queue_B ?? 0;

  // Sort by x so DOM order (and tab order) is stable left → right.
  const sortedVehicles = useMemo(
    () => [...vehicles].sort((a, b) => a.x - b.x),
    [vehicles],
  );

  return (
    <div className="card overflow-hidden relative">
      <div className="px-5 py-3 border-b border-bg-edge flex items-center justify-between">
        <div className="text-sm uppercase tracking-wider text-slate-400">
          Live corridor (sim)
        </div>
        <div className="text-xs text-slate-500 font-mono">
          {snapshot
            ? `${vehicles.length} veh · zone ${zoneLengthM}m · ${snapshot.ts.toFixed(1)}s`
            : 'no snapshot'}
        </div>
      </div>

      <div className="p-3 relative" data-testid="live-road-view">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full h-auto rounded-xl bg-gradient-to-b from-slate-950 to-slate-900 ring-1 ring-bg-edge"
          role="img"
          aria-label={`Live corridor view, phase ${phase}, ${vehicles.length} vehicles`}
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <linearGradient id="live-lane" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#1e293b" />
              <stop offset="100%" stopColor="#0f172a" />
            </linearGradient>
            <pattern
              id="repair-stripes"
              width="14"
              height="14"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <rect width="14" height="14" fill="#3f2a04" />
              <rect width="7" height="14" fill="#facc15" opacity="0.85" />
            </pattern>
          </defs>

          {/* road */}
          <rect
            x={ZONE_X}
            y={ROAD_Y}
            width={ZONE_W}
            height={ROAD_H}
            fill="url(#live-lane)"
            stroke="#1f2a52"
          />
          <line
            x1={ZONE_X}
            x2={ZONE_X + ZONE_W}
            y1={ROAD_Y + ROAD_H / 2}
            y2={ROAD_Y + ROAD_H / 2}
            stroke="#475569"
            strokeWidth={1.5}
            strokeDasharray="14 12"
          />

          {/* repair zone */}
          <g aria-label="repair zone">
            <rect
              x={REPAIR_X}
              y={ROAD_Y - 6}
              width={REPAIR_W}
              height={ROAD_H + 12}
              fill="url(#repair-stripes)"
              opacity={0.6}
            />
            <text
              x={REPAIR_X + REPAIR_W / 2}
              y={ROAD_Y - 12}
              textAnchor="middle"
              fontSize={12}
              fill="#facc15"
              fontFamily="monospace"
            >
              REPAIR
            </text>
          </g>

          {/* side labels */}
          <text
            x={ZONE_X - 8}
            y={ROAD_Y - 12}
            fill="#94a3b8"
            fontSize={14}
            textAnchor="end"
            fontFamily="monospace"
          >
            A →
          </text>
          <text
            x={ZONE_X + ZONE_W + 8}
            y={ROAD_Y - 12}
            fill="#94a3b8"
            fontSize={14}
            textAnchor="start"
            fontFamily="monospace"
          >
            ← B
          </text>

          {/* signals */}
          <Signal
            x={ZONE_X - 30}
            y={ROAD_Y + ROAD_H + 14}
            active={signalState(phase, 'A')}
            side="A"
            countdown={remaining}
          />
          <Signal
            x={ZONE_X + ZONE_W + 30}
            y={ROAD_Y + ROAD_H + 14}
            active={signalState(phase, 'B')}
            side="B"
            countdown={remaining}
          />

          {/* queue counts */}
          <QueueBadge x={ZONE_X - 30} y={ROAD_Y - 36} side="A" count={queueA} />
          <QueueBadge x={ZONE_X + ZONE_W + 30} y={ROAD_Y - 36} side="B" count={queueB} />

          {/* vehicles */}
          {sortedVehicles.map((v) => (
            <Vehicle key={v.id} v={v} zoneLengthM={zoneLengthM} />
          ))}
        </svg>

        {!snapshot && (
          <div
            className="absolute inset-3 flex items-center justify-center rounded-xl bg-slate-950/70 backdrop-blur-sm"
            data-testid="waiting-overlay"
          >
            <div className="text-center">
              <div className="text-slate-300 text-base font-medium">
                Waiting for simulator…
              </div>
              <div className="text-slate-500 text-xs font-mono mt-1">
                topic: corridor/sim/world
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Vehicle({ v, zoneLengthM }: { v: WorldVehicle; zoneLengthM: number }) {
  const fill = COLORS[v.type] ?? '#94a3b8';
  const lenPx = clamp(
    (v.len_m / Math.max(1, zoneLengthM)) * ZONE_W,
    MIN_CAR_PX,
    MAX_CAR_PX,
  );
  const heightPx = v.type === 'truck' || v.type === 'bus' ? 22 : 16;
  const px = ZONE_X + clamp(v.x, 0, 1) * ZONE_W;
  // A→B traffic stays in the upper half of the lane, B→A in the lower half.
  const lateral = v.side === 'A' ? -ROAD_H / 4 : ROAD_H / 4;
  const py = ROAD_Y + ROAD_H / 2 + lateral + (v.y ?? 0) * 6;

  // Center the rectangle on (px, py); transition transform for smooth motion.
  return (
    <g
      data-testid={`vehicle-${v.id}`}
      data-type={v.type}
      data-side={v.side}
      style={{
        transform: `translate(${px - lenPx / 2}px, ${py - heightPx / 2}px)`,
        transition: 'transform 80ms linear',
      }}
    >
      <rect
        width={lenPx}
        height={heightPx}
        rx={3}
        ry={3}
        fill={fill}
        stroke="#0f172a"
        strokeWidth={1}
      >
        {v.emergency && (
          <animate
            attributeName="opacity"
            values="1;0.3;1"
            dur="0.6s"
            repeatCount="indefinite"
          />
        )}
      </rect>
      {/* windshield hint */}
      <rect
        x={v.side === 'A' ? lenPx - lenPx * 0.28 : 2}
        y={2}
        width={lenPx * 0.26}
        height={heightPx - 4}
        rx={1}
        fill="#0f172a"
        opacity={0.45}
      />
    </g>
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
  countdown,
}: {
  x: number;
  y: number;
  active: 'green' | 'yellow' | 'red';
  side: 'A' | 'B';
  countdown: number;
}) {
  const fill =
    active === 'green' ? '#22c55e' : active === 'yellow' ? '#eab308' : '#ef4444';
  return (
    <g
      transform={`translate(${x - 20}, ${y - 10})`}
      aria-label={`Signal ${side}`}
      data-testid={`live-signal-${side}`}
    >
      <rect width={40} height={56} rx={8} fill="#0b1020" stroke="#1f2a52" />
      <circle
        cx={20}
        cy={20}
        r={11}
        fill={fill}
        style={{ filter: `drop-shadow(0 0 6px ${fill})`, transition: 'fill 200ms ease' }}
      />
      <text
        x={20}
        y={46}
        textAnchor="middle"
        fontSize={11}
        fontFamily="monospace"
        fill="#e2e8f0"
      >
        {side} {countdown}s
      </text>
    </g>
  );
}

function QueueBadge({
  x,
  y,
  side,
  count,
}: {
  x: number;
  y: number;
  side: 'A' | 'B';
  count: number;
}) {
  const color = count > 12 ? '#ef4444' : count > 6 ? '#eab308' : '#22c55e';
  return (
    <g transform={`translate(${x}, ${y})`} aria-label={`Queue ${side}`}>
      <rect
        x={-22}
        y={-12}
        width={44}
        height={20}
        rx={6}
        fill="#0b1020"
        stroke={color}
        opacity={0.9}
      />
      <text
        x={0}
        y={2}
        textAnchor="middle"
        fontSize={11}
        fontFamily="monospace"
        fill={color}
      >
        Q{side}: {count}
      </text>
    </g>
  );
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}
