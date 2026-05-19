import { useMemo } from 'react';
import { useDashboard, phaseRemaining } from '../store';
import type { Phase, VehicleType, WorldVehicle } from '../types';

interface LiveRoadViewProps {
  now: number;
}

// SVG geometry --------------------------------------------------------------
// Horizontal layout: approach A (2 lanes) → funnel → ZONE (1 lane, reversible)
// → funnel → approach B (2 lanes). Signals sit at the zone entry on each side.
// This makes the bottleneck instantly readable: you SEE two-into-one.

const W = 1200;
const H = 320;
const Y_CENTER = 170;
const LANE_H_2 = 80; // approach two-lane height
const LANE_H_1 = 48; // single shared lane in the repair zone

const APPROACH_A_X1 = 30;   // queue tail on side A
const APPROACH_A_X2 = 320;  // last x where the approach is still 2 lanes
const FUNNEL_A_X2 = 380;    // x where the funnel is finished (start of zone)
const ZONE_X = FUNNEL_A_X2;
const ZONE_W = 440;
const ZONE_X2 = ZONE_X + ZONE_W; // 820
const FUNNEL_B_X1 = ZONE_X2;
const FUNNEL_B_X2 = 880;    // x where 2 lanes resume
const APPROACH_B_X1 = FUNNEL_B_X2;
const APPROACH_B_X2 = 1170; // queue tail on side B

const MIN_CAR_PX = 12;
const MAX_CAR_PX = 56;

const COLORS: Record<VehicleType, string> = {
  car: '#3b82f6',
  truck: '#f97316',
  bus: '#14b8a6',
  motorcycle: '#06b6d4',
  emergency: '#ef4444',
};

type ZoneClass = 'queue_a' | 'zone' | 'queue_b';

function classifyZone(x: number): ZoneClass {
  if (x < 0) return 'queue_a';
  if (x > 1) return 'queue_b';
  return 'zone';
}

/**
 * Live corridor visualization driven by `corridor/sim/world` snapshots.
 *
 * The corridor is a REVERSIBLE single-lane work zone in the middle. Approaches
 * on each side are 2-lane and merge into the shared lane. Vehicles inside the
 * zone are drawn on the SAME lane regardless of direction; the only thing that
 * changes is which way they point (controlled by `side`). The active phase
 * decides which queue is allowed to feed the zone.
 *
 * Vehicle placement rules:
 *   - `0 <= x <= 1` → inside the zone, on the single shared lane.
 *   - `x < 0`       → queued on side A approach (top sub-lane).
 *   - `x > 1`       → queued on side B approach (bottom sub-lane).
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
  const insideA = corridor?.inside_A ?? 0;
  const insideB = corridor?.inside_B ?? 0;

  // Sort by x so DOM order is left → right (matches a real-world camera feed).
  const sortedVehicles = useMemo(
    () => [...vehicles].sort((a, b) => a.x - b.x),
    [vehicles],
  );

  // Pre-bucket and assign an in-queue index so queue cars line up properly.
  const placed = useMemo(() => {
    const queueACars: WorldVehicle[] = [...vehicles]
      .filter((v) => classifyZone(v.x) === 'queue_a')
      // Front of the queue (closest to the zone) is the highest x (closest to 0).
      .sort((a, b) => b.x - a.x);
    const queueBCars: WorldVehicle[] = [...vehicles]
      .filter((v) => classifyZone(v.x) === 'queue_b')
      // Front of the queue (closest to the zone) is the lowest x (closest to 1).
      .sort((a, b) => a.x - b.x);

    const indexA = new Map(queueACars.map((v, i) => [v.id, i]));
    const indexB = new Map(queueBCars.map((v, i) => [v.id, i]));

    return sortedVehicles.map((v) => ({
      v,
      zone: classifyZone(v.x),
      queueIndex:
        classifyZone(v.x) === 'queue_a'
          ? indexA.get(v.id) ?? 0
          : classifyZone(v.x) === 'queue_b'
            ? indexB.get(v.id) ?? 0
            : 0,
    }));
  }, [sortedVehicles, vehicles]);

  return (
    <div className="card overflow-hidden relative">
      <div className="px-5 py-3 border-b border-bg-edge flex items-center justify-between">
        <div className="text-sm uppercase tracking-wider text-slate-400">
          Live corridor (sim) · single-lane reverse zone
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
            <marker
              id="arrow-r"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
            </marker>
          </defs>

          {/* approach A: 2 lanes */}
          <Approach2Lane
            x1={APPROACH_A_X1}
            x2={APPROACH_A_X2}
            yCenter={Y_CENTER}
            label="Side A"
            align="left"
          />

          {/* funnel A→zone */}
          <Funnel
            x1={APPROACH_A_X2}
            x2={FUNNEL_A_X2}
            yCenter={Y_CENTER}
            wide={LANE_H_2}
            narrow={LANE_H_1}
            direction="narrowing-right"
          />

          {/* shared single lane (the repair zone) */}
          <SingleLaneZone
            yCenter={Y_CENTER}
            x1={ZONE_X}
            x2={ZONE_X2}
            phase={phase}
            zoneOccupied={(insideA + insideB) > 0 && phase !== 'GREEN_A' && phase !== 'GREEN_B'}
          />

          {/* funnel zone→B */}
          <Funnel
            x1={FUNNEL_B_X1}
            x2={FUNNEL_B_X2}
            yCenter={Y_CENTER}
            wide={LANE_H_2}
            narrow={LANE_H_1}
            direction="narrowing-left"
          />

          {/* approach B: 2 lanes */}
          <Approach2Lane
            x1={APPROACH_B_X1}
            x2={APPROACH_B_X2}
            yCenter={Y_CENTER}
            label="Side B"
            align="right"
          />

          {/* signals: A on the left at zone entry, B on the right at zone entry */}
          <Signal
            x={ZONE_X - 22}
            y={Y_CENTER - LANE_H_1 / 2 - 56}
            active={signalState(phase, 'A')}
            side="A"
            countdown={remaining}
          />
          <Signal
            x={ZONE_X2 + 22}
            y={Y_CENTER - LANE_H_1 / 2 - 56}
            active={signalState(phase, 'B')}
            side="B"
            countdown={remaining}
          />

          {/* queue counters */}
          <QueueBadge x={APPROACH_A_X1 + 28} y={Y_CENTER - LANE_H_2 / 2 - 18} side="A" count={queueA} />
          <QueueBadge x={APPROACH_B_X2 - 28} y={Y_CENTER - LANE_H_2 / 2 - 18} side="B" count={queueB} />

          {/* vehicles */}
          {placed.map(({ v, zone, queueIndex }) => (
            <Vehicle
              key={v.id}
              v={v}
              zone={zone}
              queueIndex={queueIndex}
              zoneLengthM={zoneLengthM}
            />
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

// --- sub-components --------------------------------------------------------

function Approach2Lane({
  x1,
  x2,
  yCenter,
  label,
  align,
}: {
  x1: number;
  x2: number;
  yCenter: number;
  label: string;
  align: 'left' | 'right';
}) {
  const top = yCenter - LANE_H_2 / 2;
  return (
    <g aria-label={`approach ${label}`}>
      <rect
        x={x1}
        y={top}
        width={x2 - x1}
        height={LANE_H_2}
        fill="url(#live-lane)"
        stroke="#1f2a52"
      />
      {/* lane divider */}
      <line
        x1={x1}
        x2={x2}
        y1={yCenter}
        y2={yCenter}
        stroke="#475569"
        strokeWidth={1.5}
        strokeDasharray="14 12"
      />
      <text
        x={align === 'left' ? x1 + 6 : x2 - 6}
        y={top - 8}
        fontSize={13}
        fontFamily="monospace"
        fill="#94a3b8"
        textAnchor={align === 'left' ? 'start' : 'end'}
      >
        {label}
      </text>
    </g>
  );
}

function Funnel({
  x1,
  x2,
  yCenter,
  wide,
  narrow,
  direction,
}: {
  x1: number;
  x2: number;
  yCenter: number;
  wide: number;
  narrow: number;
  direction: 'narrowing-right' | 'narrowing-left';
}) {
  // Trapezoid that visually merges 2 lanes into 1 (or reverse).
  const wideTop = yCenter - wide / 2;
  const wideBot = yCenter + wide / 2;
  const narrowTop = yCenter - narrow / 2;
  const narrowBot = yCenter + narrow / 2;
  const path =
    direction === 'narrowing-right'
      ? `M ${x1} ${wideTop} L ${x2} ${narrowTop} L ${x2} ${narrowBot} L ${x1} ${wideBot} Z`
      : `M ${x1} ${narrowTop} L ${x2} ${wideTop} L ${x2} ${wideBot} L ${x1} ${narrowBot} Z`;
  return (
    <g aria-label="merge funnel">
      <path d={path} fill="url(#live-lane)" stroke="#1f2a52" />
      {/* hint that 2 lanes merged into 1 */}
      <line
        x1={x1}
        x2={x2}
        y1={direction === 'narrowing-right' ? wideTop : narrowTop}
        y2={direction === 'narrowing-right' ? narrowTop : wideTop}
        stroke="#facc15"
        strokeWidth={1.5}
        strokeDasharray="6 8"
        opacity={0.65}
      />
      <line
        x1={x1}
        x2={x2}
        y1={direction === 'narrowing-right' ? wideBot : narrowBot}
        y2={direction === 'narrowing-right' ? narrowBot : wideBot}
        stroke="#facc15"
        strokeWidth={1.5}
        strokeDasharray="6 8"
        opacity={0.65}
      />
    </g>
  );
}

function SingleLaneZone({
  yCenter,
  x1,
  x2,
  phase,
  zoneOccupied,
}: {
  yCenter: number;
  x1: number;
  x2: number;
  phase: Phase;
  zoneOccupied: boolean;
}) {
  const top = yCenter - LANE_H_1 / 2;
  const bot = yCenter + LANE_H_1 / 2;
  return (
    <g aria-label="repair zone">
      <rect
        x={x1}
        y={top}
        width={x2 - x1}
        height={LANE_H_1}
        fill="url(#live-lane)"
        stroke="#1f2a52"
      />
      {/* zone-not-empty warning overlay: pulses red when vehicles remain during non-green */}
      {zoneOccupied && (
        <rect
          x={x1}
          y={top}
          width={x2 - x1}
          height={LANE_H_1}
          fill="#ef4444"
          stroke="#ef4444"
          strokeWidth={3}
          rx={2}
          opacity={0}
          aria-label="zone-occupied-warning"
        >
          <animate
            attributeName="opacity"
            values="0;0.25;0"
            dur="1s"
            repeatCount="indefinite"
          />
        </rect>
      )}
      {/* yellow-black hazard stripes along both edges */}
      <rect x={x1} y={top - 8} width={x2 - x1} height={6} fill="url(#repair-stripes)" />
      <rect x={x1} y={bot + 2} width={x2 - x1} height={6} fill="url(#repair-stripes)" />

      {/* repair sign */}
      <g transform={`translate(${(x1 + x2) / 2 - 18}, ${top - 38})`} aria-label="repair-sign">
        <polygon points="18,0 36,28 0,28" fill="#facc15" stroke="#0f172a" strokeWidth={1.5} />
        <text
          x={18}
          y={22}
          textAnchor="middle"
          fontSize={14}
          fontFamily="monospace"
          fontWeight={700}
          fill="#0f172a"
        >
          ⚠
        </text>
      </g>
      <text
        x={(x1 + x2) / 2}
        y={top - 8}
        textAnchor="middle"
        fontSize={11}
        fontFamily="monospace"
        fill="#facc15"
      >
        REPAIR · ONE LANE · REVERSIBLE
      </text>

      {/* directional arrow showing current phase direction */}
      <ZoneFlowArrow x1={x1} x2={x2} y={yCenter} phase={phase} />
    </g>
  );
}

function ZoneFlowArrow({
  x1,
  x2,
  y,
  phase,
}: {
  x1: number;
  x2: number;
  y: number;
  phase: Phase;
}) {
  const flowing = phase === 'GREEN_A' || phase === 'GREEN_B';
  if (!flowing) {
    return (
      <text
        x={(x1 + x2) / 2}
        y={y + 5}
        textAnchor="middle"
        fontSize={12}
        fontFamily="monospace"
        fill="#94a3b8"
        opacity={0.7}
      >
        — paused —
      </text>
    );
  }
  const right = phase === 'GREEN_A';
  const ax1 = right ? x1 + 30 : x2 - 30;
  const ax2 = right ? x2 - 30 : x1 + 30;
  return (
    <line
      x1={ax1}
      x2={ax2}
      y1={y}
      y2={y}
      stroke="#22c55e"
      strokeWidth={2.5}
      strokeOpacity={0.55}
      markerEnd="url(#arrow-r)"
    />
  );
}

function Vehicle({
  v,
  zone,
  queueIndex,
  zoneLengthM,
}: {
  v: WorldVehicle;
  zone: ZoneClass;
  queueIndex: number;
  zoneLengthM: number;
}) {
  const fill = COLORS[v.type] ?? '#94a3b8';

  // Length scales from len_m relative to corridor length, projected onto zone width.
  const lenPx = clamp(
    (v.len_m / Math.max(1, zoneLengthM)) * ZONE_W,
    MIN_CAR_PX,
    MAX_CAR_PX,
  );
  const heightPx = v.type === 'truck' || v.type === 'bus' ? 20 : 14;

  let cx = 0;
  let cy = Y_CENTER;
  let lateral = 0;

  if (zone === 'zone') {
    cx = ZONE_X + clamp(v.x, 0, 1) * ZONE_W;
    // Tiny y offset so opposite directions don't perfectly overlap if two
    // crossings happen to coincide (rare; the zone is single-lane in reality).
    lateral = v.side === 'A' ? -4 : 4;
    cy = Y_CENTER + lateral + (v.y ?? 0) * 4;
  } else if (zone === 'queue_a') {
    // Front of queue sits next to the zone entry; queue extends back to x1.
    const slot = queueIndex;
    const spacing = 30;
    cx = APPROACH_A_X2 - 30 - slot * spacing;
    cx = Math.max(APPROACH_A_X1 + lenPx / 2, cx);
    // top sub-lane = side A (heading into zone), bottom sub-lane = anything else.
    lateral = v.side === 'A' ? -LANE_H_2 / 4 : LANE_H_2 / 4;
    cy = Y_CENTER + lateral;
  } else {
    // queue_b
    const slot = queueIndex;
    const spacing = 30;
    cx = APPROACH_B_X1 + 30 + slot * spacing;
    cx = Math.min(APPROACH_B_X2 - lenPx / 2, cx);
    // bottom sub-lane = side B (heading into zone), top sub-lane = others.
    lateral = v.side === 'B' ? LANE_H_2 / 4 : -LANE_H_2 / 4;
    cy = Y_CENTER + lateral;
  }

  // side === 'A' → moving rightward (no rotation). side === 'B' → flipped.
  const rotate = v.side === 'A' ? 0 : 180;

  return (
    <g
      data-testid={`vehicle-${v.id}`}
      data-type={v.type}
      data-side={v.side}
      data-zone={zone}
      style={{
        transform: `translate(${cx}px, ${cy}px) rotate(${rotate}deg)`,
        transition: 'transform 80ms linear',
      }}
    >
      <g transform={`translate(${-lenPx / 2}, ${-heightPx / 2})`}>
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
        {/* windshield hint pointing in the direction of travel (right after rotate) */}
        <rect
          x={lenPx - lenPx * 0.28}
          y={2}
          width={lenPx * 0.26}
          height={heightPx - 4}
          rx={1}
          fill="#0f172a"
          opacity={0.45}
        />
      </g>
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
      transform={`translate(${x - 20}, ${y})`}
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
        x={-26}
        y={-12}
        width={52}
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
