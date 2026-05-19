import { useMemo } from 'react';
import {
  modeLabel,
  phaseColor,
  phaseElapsed,
  phaseRemaining,
  phaseTotal,
  useDashboard,
} from '../store';
import { phaseLabel, formatSeconds, formatClock } from '../lib/format';
import { postOverride } from '../api/client';
import type { Mode } from '../types';

/** Safe integer display — returns '—' when value is not a finite number. */
function safeInt(n: number): string {
  return Number.isFinite(n) ? String(Math.max(0, Math.round(n))) : '—';
}

/** Circular SVG countdown ring */
function CircularCountdown({
  progress,
  remaining,
  color,
}: {
  progress: number;
  remaining: number;
  color: string;
}) {
  const R = 52;
  const CIRC = 2 * Math.PI * R;
  const strokeColor =
    color === 'green' ? '#22c55e' : color === 'yellow' ? '#eab308' : '#ef4444';
  const glowColor =
    color === 'green'
      ? 'rgba(34,197,94,0.5)'
      : color === 'yellow'
        ? 'rgba(234,179,8,0.5)'
        : 'rgba(239,68,68,0.5)';
  // dashoffset: 0 = full ring, CIRC = empty ring
  const dashOffset = CIRC * (1 - progress);

  return (
    <div className="relative flex items-center justify-center" style={{ width: 128, height: 128 }}>
      <svg width={128} height={128} viewBox="0 0 128 128" style={{ position: 'absolute', top: 0, left: 0 }}>
        {/* track */}
        <circle
          cx={64}
          cy={64}
          r={R}
          fill="none"
          stroke="#1e293b"
          strokeWidth={8}
        />
        {/* progress ring */}
        <circle
          cx={64}
          cy={64}
          r={R}
          fill="none"
          stroke={strokeColor}
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={CIRC}
          strokeDashoffset={dashOffset}
          transform="rotate(-90 64 64)"
          style={{
            transition: 'stroke-dashoffset 700ms ease-out, stroke 600ms ease',
            filter: `drop-shadow(0 0 6px ${glowColor})`,
          }}
        />
      </svg>
      <div className="flex flex-col items-center z-10">
        <span
          className="text-4xl font-bold font-mono phase-transition"
          style={{ color: strokeColor }}
        >
          {formatSeconds(remaining)}
        </span>
        <span className="text-xs text-slate-500 uppercase tracking-wider mt-0.5">осталось</span>
      </div>
    </div>
  );
}

export function PhasePanel({ now }: { now: number }) {
  const state = useDashboard((s) => s.state);
  const phase = state?.phase ?? 'RED_BOTH';
  const color = phaseColor(phase);
  const remaining = phaseRemaining(state, now);
  const elapsed = phaseElapsed(state, now);
  const total = phaseTotal(state);
  const progress = useMemo(
    () => Math.max(0, Math.min(1, total === 0 ? 0 : elapsed / total)),
    [elapsed, total],
  );

  const zoneOccupied = (state?.inside_A ?? 0) + (state?.inside_B ?? 0) > 0;

  const setMode = async (mode: Mode) => {
    if (state?.mode === mode) return;
    try {
      await postOverride({ action: 'mode_switch', mode: mode, by: 'dashboard' });
    } catch {
      // The PhasePanel does not own toast UI — controller emits an alert on failure.
    }
  };

  const colorClass: Record<string, string> = {
    green: 'border-accent-green/60 text-emerald-200 bg-accent-green/10 signal-glow-green',
    yellow: 'border-accent-yellow/60 text-yellow-200 bg-accent-yellow/10 signal-glow-yellow',
    red: 'border-accent-red/60 text-red-200 bg-accent-red/10 signal-glow-red',
    slate: 'border-bg-edge text-slate-300 bg-bg-raised',
  };

  return (
    <div className="card phase-transition">
      <div className="px-5 py-3 border-b border-bg-edge flex items-center justify-between gap-3 flex-wrap">
        <div className="text-sm uppercase tracking-wider text-slate-400">Активная фаза</div>
        <div className="flex items-center gap-3">
          {zoneOccupied && (
            <span
              className="inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-1 rounded-md bg-red-500/20 text-red-300 border border-red-500/40 animate-pulse"
              role="status"
              aria-label="ТС в зоне"
            >
              <span className="w-2 h-2 rounded-full bg-red-400" />
              Зона не пуста
            </span>
          )}
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-md border ${
              state?.mode === 'adaptive'
                ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                : 'bg-slate-700/50 text-slate-300 border-slate-600'
            }`}
            aria-label={`Текущий режим: ${modeLabel(state?.mode)}`}
          >
            {modeLabel(state?.mode)}
          </span>
        </div>
      </div>
      <div className="p-5 grid grid-cols-1 md:grid-cols-3 gap-5 items-center">
        <div
          className={`rounded-2xl border-2 p-5 phase-transition ${colorClass[color]}`}
          aria-live="polite"
        >
          <div className="text-xs uppercase tracking-widest opacity-80">Фаза</div>
          <div className="text-3xl md:text-4xl font-bold mt-1 font-mono">{phaseLabel(phase)}</div>
          <div className="text-sm mt-2 opacity-80">
            с {formatClock(state?.phase_started_at ?? 0)}
          </div>
        </div>

        <div className="flex flex-col items-center gap-3">
          <div className="text-xs uppercase tracking-widest text-slate-500 self-start">Обратный отсчёт</div>
          <CircularCountdown
            progress={progress}
            remaining={remaining}
            color={color}
          />
          <div className="text-xs text-slate-500 font-mono">
            {safeInt(elapsed)}s / {safeInt(total)}s
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-widest text-slate-500">Режим</div>
          <div role="group" aria-label="Переключение режима" className="mt-2 inline-flex rounded-lg overflow-hidden border border-bg-edge">
            {(['baseline', 'adaptive'] as Mode[]).map((m) => {
              const active = state?.mode === m;
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={`px-4 py-2 text-sm transition-colors ${
                    active
                      ? 'bg-accent-blue/30 text-blue-100'
                      : 'bg-bg-raised hover:bg-bg-edge text-slate-300'
                  }`}
                  aria-pressed={active}
                >
                  {modeLabel(m)}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-slate-500 mt-3 leading-relaxed">
            Фиксированный: статичные таймеры. Адаптивный: веса очередь · ожидание · фура.
          </p>
        </div>
      </div>
    </div>
  );
}
