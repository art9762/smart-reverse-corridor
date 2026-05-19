import { useEffect, useMemo, useState } from 'react';
import { getWS, type WSStatus } from './api/ws';
import { connectMqtt, mqttWsUrl } from './api/mqtt';
import { modeLabel, useDashboard } from './store';
import { LiveRoadView } from './components/LiveRoadView';
import { RoadView } from './components/RoadView';
import { PhasePanel } from './components/PhasePanel';
import { QueueChart } from './components/QueueChart';
import { ThroughputChart } from './components/ThroughputChart';
import { DelayChart } from './components/DelayChart';
import { AlertsFeed } from './components/AlertsFeed';
import { ControlPanel } from './components/ControlPanel';
import { CameraHealth } from './components/CameraHealth';
import { apiBaseUrl } from './api/client';
import { ComparisonPanel } from './components/ComparisonPanel';

export default function App() {
  const ingest = useDashboard((s) => s.ingest);
  const setConnected = useDashboard((s) => s.setConnected);
  const mode = useDashboard((s) => s.state?.mode);
  const [wsStatus, setWsStatus] = useState<WSStatus>('idle');
  const [now, setNow] = useState<number>(Date.now() / 1000);

  useEffect(() => {
    const ws = getWS();
    const unsubMsg = ws.subscribe(ingest);
    const unsubStatus = ws.onStatus((s) => {
      setWsStatus(s);
      setConnected(s === 'open');
    });
    ws.connect();
    const mqttClient = connectMqtt(ingest);
    return () => {
      unsubMsg();
      unsubStatus();
      ws.close();
      mqttClient?.end(true);
    };
  }, [ingest, setConnected]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 250);
    return () => clearInterval(t);
  }, []);

  const wsLabel = useMemo<string>(() => {
    switch (wsStatus) {
      case 'open':
        return 'Live';
      case 'connecting':
        return 'Connecting…';
      case 'error':
        return 'Error';
      case 'closed':
        return 'Reconnecting…';
      default:
        return 'Idle';
    }
  }, [wsStatus]);

  return (
    <div className="min-h-full bg-bg-base bg-grid">
      <header className="border-b border-bg-edge/70 bg-bg-panel/60 backdrop-blur sticky top-0 z-20">
        <div className="max-w-[1920px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-accent-green animate-pulseSoft" />
            <h1 className="text-lg font-semibold tracking-tight">
              Smart Reverse Corridor
              <span className="ml-2 text-slate-400 font-normal hidden sm:inline">/ Operator</span>
            </h1>
          </div>
          <div className="ml-auto flex items-center gap-3 text-xs text-slate-400">
            {mode && (
              <span
                className={`hidden sm:inline-flex items-center gap-1.5 font-semibold px-2 py-0.5 rounded border ${
                  mode === 'adaptive'
                    ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                    : 'bg-slate-700/50 text-slate-300 border-slate-600'
                }`}
                aria-label={`Current mode: ${modeLabel(mode)}`}
              >
                {modeLabel(mode)}
              </span>
            )}
            <ConnectionDot status={wsStatus} label={wsLabel} />
            <span className="hidden md:inline">API: {apiBaseUrl}</span>
            {mqttWsUrl && (
              <span className="hidden lg:inline">MQTT: {mqttWsUrl}</span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1920px] mx-auto px-4 sm:px-6 py-4 sm:py-6 grid grid-cols-1 xl:grid-cols-12 gap-4 sm:gap-6">
        <section className="col-span-1 xl:col-span-8 space-y-4 sm:space-y-6">
          {/* Live world snapshot from corridor/sim/world is the hero panel. */}
          <LiveRoadView now={now} />
          <PhasePanel now={now} />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
            <QueueChart />
            <ThroughputChart />
            <DelayChart />
          </div>
          <ComparisonPanel />
        </section>

        <aside className="col-span-1 xl:col-span-4 space-y-4 sm:space-y-6">
          <ControlPanel />
          {/* Compact mini-map of the corridor in the sidebar. */}
          <RoadView now={now} />
          <CameraHealth />
          <AlertsFeed />
        </aside>
      </main>

      <footer className="px-6 py-4 text-center text-xs text-slate-500">
        v0.1 · dashboard streams from <span className="font-mono">/ws</span>
        {mqttWsUrl ? ' + direct MQTT WS (incl. corridor/sim/world)' : ''}
      </footer>
    </div>
  );
}

function ConnectionDot({ status, label }: { status: WSStatus; label: string }) {
  const cls =
    status === 'open'
      ? 'bg-accent-green'
      : status === 'connecting' || status === 'closed'
        ? 'bg-accent-yellow animate-pulseSoft'
        : 'bg-accent-red';
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`w-2 h-2 rounded-full ${cls}`} aria-hidden />
      <span>{label}</span>
    </span>
  );
}
