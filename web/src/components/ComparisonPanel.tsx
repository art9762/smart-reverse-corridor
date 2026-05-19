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
  const totalThroughput = throughputA + throughputB;
  const avgDelay = (delayA + delayB) / 2;

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <h3 className="text-sm font-medium text-gray-400 mb-3">Performance Metrics</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Mode" value={mode} highlight />
        <MetricCard label="Throughput (5min)" value={`${totalThroughput} veh`} />
        <MetricCard label="Avg Delay" value={`${avgDelay.toFixed(1)}s`} />
        <MetricCard
          label="Max Queue"
          value={`A:${lastTick.max_queue_today?.A ?? 0} B:${lastTick.max_queue_today?.B ?? 0}`}
        />
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
