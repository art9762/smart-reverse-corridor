import { useEffect, useMemo, useState } from 'react';
import { getWS, type WSStatus } from './api/ws';
import { connectMqtt, mqttWsUrl } from './api/mqtt';
import { useDashboard } from './store';
import { RoadView } from './components/RoadView';
import { PhasePanel } from './components/PhasePanel';
import { QueueChart } from './components/QueueChart';
import { ThroughputChart } from './components/ThroughputChart';
import { AlertsFeed } from './components/AlertsFeed';
import { ControlPanel } from './components/ControlPanel';
import { CameraHealth } from './components/CameraHealth';
import { apiBaseUrl } from './api/client';

export default function App() {
  const ingest = useDashboard((s) => s.ingest);
  const setConnected = useDashboard((s) => s.setConnected);
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
              <span className="ml-2 text-slate-400 font-normal">/ Operator</span>
            </h1>
          </div>
          <div className="ml-auto flex items-center gap-3 text-xs text-slate-400">
            <ConnectionDot status={wsStatus} label={wsLabel} />
            <span className="hidden md:inline">API: {apiBaseUrl}</span>
            {mqttWsUrl && (
              <span className="hidden lg:inline">MQTT: {mqttWsUrl}</span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1920px] mx-auto px-6 py-6 grid grid-cols-12 gap-6">
        <section className="col-span-12 xl:col-span-8 space-y-6">
          <PhasePanel now={now} />
          <RoadView now={now} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <QueueChart />
            <ThroughputChart />
          </div>
        </section>

        <aside className="col-span-12 xl:col-span-4 space-y-6">
          <ControlPanel />
          <CameraHealth />
          <AlertsFeed />
        </aside>
      </main>

      <footer className="px-6 py-4 text-center text-xs text-slate-500">
        v0.1 · dashboard streams from <span className="font-mono">/ws</span>
        {mqttWsUrl ? ' + direct MQTT WS' : ''}
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
