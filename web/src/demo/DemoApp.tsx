import { useEffect, useMemo, useState } from 'react';
import { modeLabel, useDashboard } from '../store';
import { LiveRoadView } from '../components/LiveRoadView';
import { RoadView } from '../components/RoadView';
import { PhasePanel } from '../components/PhasePanel';
import { QueueChart } from '../components/QueueChart';
import { ThroughputChart } from '../components/ThroughputChart';
import { DelayChart } from '../components/DelayChart';
import { AlertsFeed } from '../components/AlertsFeed';
import { CameraHealth } from '../components/CameraHealth';
import { ComparisonPanel } from '../components/ComparisonPanel';
import { DemoControlPanel } from './DemoControlPanel';
import { ScenarioBar } from './ScenarioBar';
import { demoOrchestrator } from './orchestrator';

export default function DemoApp() {
  const mode = useDashboard((s) => s.state?.mode);
  const [now, setNow] = useState<number>(Date.now() / 1000);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);

  // Clock tick for phase countdown
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 250);
    return () => clearInterval(t);
  }, []);

  // Start / stop orchestrator on mount / unmount
  useEffect(() => {
    demoOrchestrator.start();
    return () => {
      demoOrchestrator.stop();
    };
  }, []);

  const handleStartScenario = (name: string) => {
    demoOrchestrator.runScenario(name);
    setActiveScenario(name);
  };

  const handleStopScenario = () => {
    // Reset sim + stop scenario events, then restart the idle loop
    demoOrchestrator.reset();
    demoOrchestrator.start();
    setActiveScenario(null);
  };

  const modeBadge = useMemo(() => {
    if (!mode) return null;
    return (
      <span
        className={`hidden sm:inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded border ${
          mode === 'adaptive'
            ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
            : 'bg-slate-700/50 text-slate-300 border-slate-600'
        }`}
        aria-label={`Current mode: ${modeLabel(mode)}`}
      >
        {modeLabel(mode)}
      </span>
    );
  }, [mode]);

  return (
    <div className="min-h-full bg-bg-base bg-grid">
      {/* Header */}
      <header className="border-b border-bg-edge/70 bg-bg-panel/60 backdrop-blur sticky top-0 z-20 header-glow">
        <div className="max-w-[1920px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <span
              className="w-2.5 h-2.5 rounded-full bg-accent-green animate-pulseSoft"
              aria-hidden
            />
            <h1 className="text-lg font-semibold tracking-tight">
              Smart Reverse Corridor
              <span className="ml-2 text-slate-400 font-normal hidden sm:inline">
                · Demo Mode
              </span>
            </h1>
          </div>
          <div className="ml-auto flex items-center gap-3 text-xs text-slate-400">
            {modeBadge}
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border bg-accent-violet/20 text-violet-300 border-accent-violet/40 text-xs font-semibold">
              <span
                className="w-1.5 h-1.5 rounded-full bg-accent-violet animate-pulseSoft"
                aria-hidden
              />
              Standalone
            </span>
          </div>
        </div>
      </header>

      {/* Scenario bar */}
      <div className="max-w-[1920px] mx-auto pt-4">
        <ScenarioBar
          scenarios={demoOrchestrator.getScenarios()}
          activeScenarioName={activeScenario}
          onStart={handleStartScenario}
          onStop={handleStopScenario}
        />
      </div>

      {/* Main grid */}
      <main className="max-w-[1920px] mx-auto px-4 sm:px-6 py-4 sm:py-6 grid grid-cols-1 xl:grid-cols-12 gap-4 sm:gap-6">
        {/* Left column — 8 cols */}
        <section
          className="col-span-1 xl:col-span-8 space-y-4 sm:space-y-6 fade-in-up"
          style={{ animationDelay: '0.1s' }}
        >
          <LiveRoadView now={now} />
          <PhasePanel now={now} />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
            <QueueChart />
            <ThroughputChart />
            <DelayChart />
          </div>
          <ComparisonPanel />
        </section>

        {/* Right sidebar — 4 cols */}
        <aside
          className="col-span-1 xl:col-span-4 space-y-4 sm:space-y-6 fade-in-up"
          style={{ animationDelay: '0.25s' }}
        >
          <DemoControlPanel />
          <RoadView now={now} />
          <CameraHealth />
          <AlertsFeed />
        </aside>
      </main>

      {/* Footer */}
      <footer className="px-6 py-4 text-center text-xs text-slate-500">
        Standalone demo · no backend required
      </footer>
    </div>
  );
}
