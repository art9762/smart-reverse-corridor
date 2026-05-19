import { useDashboard } from '../store';

export function ComparisonPanel() {
  const lastTick = useDashboard((s) => s.lastTick);
  const state = useDashboard((s) => s.state);

  if (!lastTick) return null;

  const mode = state?.mode ?? 'adaptive';
  const throughputA = lastTick.throughput_5min?.A ?? 0;
  const throughputB = lastTick.throughput_5min?.B ?? 0;
  const delayA = lastTick.avg_delay_5min?.A ?? 0;
  const delayB = lastTick.avg_delay_5min?.B ?? 0;
  const maxQueueA = lastTick.max_queue_today?.A ?? 0;
  const maxQueueB = lastTick.max_queue_today?.B ?? 0;

  const totalThroughput = throughputA + throughputB;
  const avgDelay = Number.isFinite(delayA + delayB) ? (delayA + delayB) / 2 : 0;

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-400">Performance Metrics</h3>
        <span
          className={`text-xs font-semibold px-2 py-0.5 rounded border ${
            mode === 'adaptive'
              ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
              : 'bg-slate-700/50 text-slate-300 border-slate-600'
          }`}
        >
          {mode}
        </span>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
        <MetricCard label="Throughput (5min)" value={`${totalThroughput} veh`} />
        <MetricCard
          label="Avg Delay"
          value={Number.isFinite(avgDelay) ? `${avgDelay.toFixed(1)}s` : '—'}
        />
        <MetricCard label="Max Queue A" value={String(maxQueueA)} />
        <MetricCard label="Max Queue B" value={String(maxQueueB)} />
      </div>

      {/* Side-by-side breakdown */}
      <div className="border-t border-gray-700 pt-3">
        <div className="text-xs text-gray-500 uppercase tracking-widest mb-2">Side breakdown</div>
        <div className="grid grid-cols-2 gap-3">
          {(['A', 'B'] as const).map((side) => {
            const throughput = side === 'A' ? throughputA : throughputB;
            const delay = side === 'A' ? delayA : delayB;
            const maxQ = side === 'A' ? maxQueueA : maxQueueB;
            const queue = side === 'A' ? (state?.queue_A ?? 0) : (state?.queue_B ?? 0);
            return (
              <div
                key={side}
                className="bg-gray-900/60 rounded-md p-3 border border-gray-700"
              >
                <div className="text-xs font-semibold text-slate-300 mb-2">Side {side}</div>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Throughput</span>
                    <span className="font-mono text-white">{throughput} veh</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Avg delay</span>
                    <span className="font-mono text-white">
                      {Number.isFinite(delay) ? `${delay.toFixed(1)}s` : '—'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Queue now</span>
                    <span className="font-mono text-white">{queue}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Max queue today</span>
                    <span className="font-mono text-white">{maxQ}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="text-center">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-lg font-bold ${highlight ? 'text-green-400' : 'text-white'}`}>
        {value}
      </div>
    </div>
  );
}
