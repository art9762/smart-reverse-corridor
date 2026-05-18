import { ALL_CAMERAS } from '../types';
import { useDashboard } from '../store';
import { formatHz, formatClock } from '../lib/format';

export function CameraHealth() {
  const cameras = useDashboard((s) => s.cameras);

  return (
    <div className="card">
      <div className="px-5 py-3 border-b border-bg-edge flex items-center justify-between">
        <div className="text-sm uppercase tracking-wider text-slate-400">Camera health</div>
        <div className="text-[10px] text-slate-500 font-mono">heartbeat ≤ 1 s</div>
      </div>
      <div className="p-4 grid grid-cols-2 gap-3">
        {ALL_CAMERAS.map((id) => {
          const c = cameras[id];
          const dotClass = c?.healthy
            ? 'bg-accent-green shadow-[0_0_12px_rgba(34,197,94,0.7)]'
            : 'bg-accent-red shadow-[0_0_12px_rgba(239,68,68,0.6)] animate-pulseSoft';
          return (
            <div
              key={id}
              className="card-tight p-3 flex items-center gap-3"
              data-testid={`camera-${id}`}
            >
              <span className={`w-3 h-3 rounded-full ${dotClass}`} aria-hidden />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-mono text-slate-100">{id}</div>
                <div className="text-xs text-slate-500">
                  {c?.healthy ? 'online' : 'lost'}
                  {c?.fps ? ` · ${formatHz(c.fps)}` : ''}
                </div>
              </div>
              {c?.ts ? (
                <div className="text-[10px] font-mono text-slate-500">
                  {formatClock(c.ts)}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
