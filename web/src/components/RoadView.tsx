import { useDashboard, phaseColor } from '../store';
import type { Phase } from '../types';

interface RoadViewProps {
  now: number;
}

const W = 320;
const H = 90;
const ZONE_X = 90;
const ZONE_W = W - 180;

/**
 * Compact mini-map of the corridor. The hero visualization is `LiveRoadView`;
 * this component is a small at-a-glance summary intended for the sidebar or
 * narrow grids: two signals, the zone in the middle, and queue counts.
 *
 * It intentionally does NOT draw two parallel lanes through the work zone —
 * the corridor is single-lane reversible, and the mini-map reflects that.
 */
export function RoadView({ now: _now }: RoadViewProps) {
  const state = useDashboard((s) => s.state);
  const phase: Phase = state?.phase ?? 'RED_BOTH';
  const ring = phaseColor(phase);
  const queueA = state?.queue_A ?? 0;
  const queueB = state?.queue_B ?? 0;

  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-3 border-b border-bg-edge flex items-center justify-between">
        <div className="text-sm uppercase tracking-wider text-slate-400">
          Corridor mini-map
        </div>
        <div className="text-xs text-slate-500 font-mono">phase {phase}</div>
      </div>
      <div className="p-3" data-testid="road-view-container">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className={`w-full h-auto rounded-lg bg-slate-950 ring-1 ring-bg-edge ${
            ring === 'green' ? 'shadow-[0_0_30px_rgba(34,197,94,0.15)]' : ''
          }`}
          role="img"
          aria-label={`Mini corridor view, phase ${phase}`}
        >
          {/* approach A (2 lanes — drawn as a thicker block) */}
          <rect x={4} y={32} width={ZONE_X - 4} height={26} fill="#1e293b" stroke="#1f2a52" />
          {/* zone (single lane) */}
          <rect
            x={ZONE_X}
            y={38}
            width={ZONE_W}
            height={14}
            fill="#0f172a"
            stroke="#facc15"
            strokeDasharray="4 4"
          />
          {/* approach B */}
          <rect x={W - ZONE_X} y={32} width={ZONE_X - 4} height={26} fill="#1e293b" stroke="#1f2a52" />

          {/* signals */}
          <g aria-label="Signal A">
            <Lamp x={ZONE_X - 14} y={20} active={signalState(phase, 'A')} />
          </g>
          <g aria-label="Signal B">
            <Lamp x={W - ZONE_X + 14} y={20} active={signalState(phase, 'B')} />
          </g>

          <text x={6} y={20} fill="#94a3b8" fontSize={10} fontFamily="monospace">A</text>
          <text x={W - 12} y={20} fill="#94a3b8" fontSize={10} fontFamily="monospace" textAnchor="end">B</text>

          <text
            x={20}
            y={78}
            fill="#cbd5e1"
            fontSize={11}
            fontFamily="monospace"
            data-testid="mini-queue-a"
          >
            QA: {queueA}
          </text>
          <text
            x={W - 20}
            y={78}
            fill="#cbd5e1"
            fontSize={11}
            fontFamily="monospace"
            textAnchor="end"
            data-testid="mini-queue-b"
          >
            QB: {queueB}
          </text>
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

function Lamp({
  x,
  y,
  active,
}: {
  x: number;
  y: number;
  active: 'green' | 'yellow' | 'red';
}) {
  const fill =
    active === 'green' ? '#22c55e' : active === 'yellow' ? '#eab308' : '#ef4444';
  return (
    <circle
      cx={x}
      cy={y}
      r={6}
      fill={fill}
      style={{ filter: `drop-shadow(0 0 4px ${fill})` }}
    />
  );
}
