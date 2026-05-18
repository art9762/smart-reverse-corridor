import { useMemo, useState } from 'react';
import { useDashboard } from '../store';
import type { AlertLevel } from '../types';
import { formatClock } from '../lib/format';

const LEVELS: AlertLevel[] = ['emergency', 'warning', 'info'];

export function AlertsFeed() {
  const alerts = useDashboard((s) => s.alerts);
  const ack = useDashboard((s) => s.acknowledgeAlert);
  const [filter, setFilter] = useState<AlertLevel | 'all'>('all');

  const filtered = useMemo(
    () => (filter === 'all' ? alerts : alerts.filter((a) => a.level === filter)),
    [alerts, filter],
  );

  return (
    <div className="card">
      <div className="px-5 py-3 border-b border-bg-edge flex items-center justify-between">
        <div className="text-sm uppercase tracking-wider text-slate-400">Alerts</div>
        <div className="flex items-center gap-1 text-xs">
          <button
            type="button"
            onClick={() => setFilter('all')}
            aria-pressed={filter === 'all'}
            className={`px-2 py-1 rounded ${filter === 'all' ? 'bg-bg-edge text-slate-100' : 'text-slate-400 hover:text-slate-200'}`}
          >
            all
          </button>
          {LEVELS.map((l) => (
            <button
              key={l}
              type="button"
              aria-pressed={filter === l}
              onClick={() => setFilter(l)}
              className={`px-2 py-1 rounded capitalize ${
                filter === l
                  ? l === 'emergency'
                    ? 'bg-accent-red/30 text-red-200'
                    : l === 'warning'
                      ? 'bg-accent-yellow/30 text-yellow-200'
                      : 'bg-accent-blue/30 text-blue-200'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
      <ul className="max-h-80 overflow-y-auto divide-y divide-bg-edge">
        {filtered.length === 0 && (
          <li className="px-5 py-8 text-center text-slate-500 text-sm">
            No active alerts.
          </li>
        )}
        {filtered.map((a) => (
          <li key={a.id} className="px-5 py-3 flex items-start gap-3 group">
            <span className={`mt-1 w-2 h-2 rounded-full ${dotClass(a.level)}`} aria-hidden />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-slate-500">
                  {formatClock(a.ts)}
                </span>
                <span className={`tag ${tagClass(a.level)}`}>{a.code}</span>
              </div>
              <p className="text-sm text-slate-200 mt-1 break-words">{a.detail}</p>
            </div>
            <button
              type="button"
              onClick={() => a.id && ack(a.id)}
              className="opacity-0 group-hover:opacity-100 text-xs text-slate-400 hover:text-slate-100 transition-opacity"
              aria-label="Dismiss alert"
            >
              dismiss
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function dotClass(level: AlertLevel): string {
  if (level === 'emergency') return 'bg-accent-red animate-pulseSoft';
  if (level === 'warning') return 'bg-accent-yellow';
  return 'bg-accent-blue';
}

function tagClass(level: AlertLevel): string {
  if (level === 'emergency') return 'bg-accent-red/15 border-accent-red/40 text-red-200';
  if (level === 'warning') return 'bg-accent-yellow/15 border-accent-yellow/40 text-yellow-200';
  return 'bg-accent-blue/15 border-accent-blue/40 text-blue-200';
}
