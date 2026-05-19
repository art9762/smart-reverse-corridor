import { useEffect, useState } from 'react';
import type { ScenarioInfo } from './scenarios';

interface ScenarioBarProps {
  scenarios: ScenarioInfo[];
  activeScenarioName: string | null;
  onStart: (name: string) => void;
  onStop: () => void;
}

function useElapsedTimer(active: boolean) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active) {
      setElapsed(0);
      return;
    }
    setElapsed(0);
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [active]);

  return elapsed;
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function ScenarioBar({
  scenarios,
  activeScenarioName,
  onStart,
  onStop,
}: ScenarioBarProps) {
  const isRunning = activeScenarioName !== null;
  const elapsed = useElapsedTimer(isRunning);

  return (
    <div
      className="
        mx-4 sm:mx-6 mb-4
        bg-bg-panel/70 border border-bg-edge
        backdrop-blur rounded-2xl
        px-4 py-3
        flex flex-wrap items-center gap-3
      "
      role="region"
      aria-label="Demo scenarios"
    >
      {/* Label */}
      <span className="text-xs uppercase tracking-widest text-slate-500 shrink-0">
        Scenarios
      </span>

      {/* Scenario cards */}
      <div className="flex flex-wrap gap-2 flex-1 min-w-0">
        {scenarios.map((sc) => {
          const isActive = activeScenarioName === sc.name;
          return (
            <button
              key={sc.name}
              type="button"
              onClick={() => onStart(sc.name)}
              disabled={isActive}
              aria-pressed={isActive}
              className={`
                group relative flex flex-col items-start
                px-3 py-2 rounded-xl border transition-all text-left
                text-xs shrink-0
                ${
                  isActive
                    ? 'bg-accent-blue/20 border-accent-blue/50 text-blue-100 shadow-[0_0_12px_rgba(59,130,246,0.3)]'
                    : 'bg-bg-raised border-bg-edge hover:border-accent-blue/40 hover:bg-bg-edge text-slate-300 hover:text-slate-100'
                }
                disabled:cursor-default
              `}
            >
              <span className="font-semibold leading-tight">{sc.label}</span>
              <span className="text-[10px] opacity-60 mt-0.5 leading-snug max-w-[160px]">
                {sc.description}
              </span>
              <span className="mt-1 text-[9px] uppercase tracking-widest opacity-40">
                {sc.duration}s
              </span>
              {isActive && (
                <span
                  className="absolute top-1 right-1.5 w-1.5 h-1.5 rounded-full bg-accent-blue animate-pulseSoft"
                  aria-hidden
                />
              )}
            </button>
          );
        })}
      </div>

      {/* Timer + stop */}
      <div className="flex items-center gap-3 shrink-0 ml-auto">
        {isRunning && (
          <div className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full bg-accent-green animate-pulseSoft"
              aria-hidden
            />
            <span className="font-mono text-sm text-slate-200 tabular-nums">
              {formatElapsed(elapsed)}
            </span>
            <span className="text-xs text-slate-500">{activeScenarioName}</span>
          </div>
        )}
        {!isRunning && (
          <span className="text-xs text-slate-600 italic">no scenario running</span>
        )}
        <button
          type="button"
          onClick={onStop}
          disabled={!isRunning}
          className="btn-danger text-xs px-3 py-1.5 disabled:opacity-30"
          aria-label="Stop current scenario"
        >
          ⏹ Stop
        </button>
      </div>
    </div>
  );
}
