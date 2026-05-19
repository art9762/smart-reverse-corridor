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
        <div className="text-sm uppercase tracking-wider text-slate-400">Active phase</div>
        <div className="flex items-center gap-3">
          {zoneOccupied && (
            <span
              className="inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-1 rounded-md bg-red-500/20 text-red-300 border border-red-500/40 animate-pulse"
              role="status"
              aria-label="Vehicles inside zone"
            >
              <span className="w-2 h-2 rounded-full bg-red-400" />
              Zone not empty
            </span>
          )}
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-md border ${
              state?.mode === 'adaptive'
                ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                : 'bg-slate-700/50 text-slate-300 border-slate-600'
            }`}
            aria-label={`Current mode: ${modeLabel(state?.mode)}`}
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
          <div className="text-xs uppercase tracking-widest opacity-80">Phase</div>
          <div className="text-3xl md:text-4xl font-bold mt-1 font-mono">{phaseLabel(phase)}</div>
          <div className="text-sm mt-2 opacity-80">
            since {formatClock(state?.phase_started_at ?? 0)}
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-widest text-slate-500">Countdown</div>
          <div className="text-5xl md:text-6xl font-bold font-mono mt-1 phase-transition">
            {formatSeconds(remaining)}
          </div>
          <div className="mt-3 h-2 bg-bg-raised rounded-full overflow-hidden">
            <div
              className={`h-full transition-[width] duration-700 ease-out ${
                color === 'green'
                  ? 'bg-accent-green'
                  : color === 'yellow'
                    ? 'bg-accent-yellow'
                    : 'bg-accent-red'
              }`}
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
          <div className="text-xs text-slate-500 mt-1 font-mono">
            {safeInt(elapsed)}s / {safeInt(total)}s
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-widest text-slate-500">Mode</div>
          <div role="group" aria-label="Mode toggle" className="mt-2 inline-flex rounded-lg overflow-hidden border border-bg-edge">
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
            Baseline holds fixed timers. Adaptive uses queue · wait · truck weights.
          </p>
        </div>
      </div>
    </div>
  );
}
