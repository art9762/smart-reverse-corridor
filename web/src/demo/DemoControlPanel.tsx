import { useState } from 'react';
import { modeLabel, useDashboard } from '../store';
import { demoOrchestrator } from './orchestrator';
import type { Mode, Phase, Side } from '../types';

const DEFAULT_WEIGHTS = { prioWQueue: 1.0, prioWWait: 0.05, prioWTruck: 0.5 };

function Slider({
  label,
  value,
  onChange,
  min,
  max,
  step,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
}) {
  return (
    <label className="block text-sm">
      <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
        <span className="uppercase tracking-widest">{label}</span>
        <span className="font-mono text-slate-200">{value.toFixed(3)}</span>
      </div>
      <input
        type="range"
        className="w-full accent-blue-500"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={`weight ${label}`}
      />
    </label>
  );
}

export function DemoControlPanel() {
  const state = useDashboard((s) => s.state);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);
  const [stopped, setStopped] = useState(false);
  const [spawnA, setSpawnA] = useState(0.5);
  const [spawnB, setSpawnB] = useState(0.5);

  const flash = (msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(null), 3000);
  };

  const switchMode = (mode: Mode) => {
    demoOrchestrator.switchMode(mode);
    flash(`✓ mode → ${modeLabel(mode)}`);
  };

  const ambulance = (side: Side) => {
    demoOrchestrator.triggerAmbulance(side);
    flash(`✓ 🚑 ambulance from ${side}`);
  };

  const forcePhase = (phase: Phase) => {
    demoOrchestrator.forcePhase(phase);
    flash(`✓ forced ${phase}`);
  };

  const handleStop = () => {
    demoOrchestrator.emergencyStop();
    setStopped(true);
    flash('✓ emergency stop');
  };

  const handleResume = () => {
    demoOrchestrator.resume();
    setStopped(false);
    flash('✓ resumed');
  };

  const applySpawnRates = (a: number, b: number) => {
    demoOrchestrator.setSpawnRates(a, b);
  };

  const applyWeights = () => {
    demoOrchestrator.setWeights(weights);
    flash('✓ weights applied');
  };

  const injectStuck = () => {
    demoOrchestrator.triggerStuck('A');
    flash('✓ stuck vehicle injected');
  };

  const currentMode = state?.mode;

  return (
    <div className="card">
      <div className="px-5 py-3 border-b border-bg-edge">
        <div className="text-sm uppercase tracking-wider text-slate-400">Demo Controls</div>
      </div>
      <div className="p-5 space-y-5">

        {/* Mode */}
        <section>
          <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">Mode</div>
          <div className="grid grid-cols-2 gap-2">
            {(['baseline', 'adaptive'] as Mode[]).map((m) => {
              const active = currentMode === m;
              return (
                <button
                  key={m}
                  type="button"
                  className={active ? 'btn-primary' : 'btn'}
                  disabled={active}
                  onClick={() => switchMode(m)}
                  aria-pressed={active}
                  aria-label={`Switch to ${modeLabel(m)} mode`}
                >
                  {active && <span className="mr-1">✓</span>}
                  {modeLabel(m)}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Baseline: fixed timers. Adaptive: queue · wait · truck weights.
          </p>
        </section>

        {/* Ambulance */}
        <section>
          <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">
            Priority override
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className="btn-warn"
              onClick={() => ambulance('A')}
              aria-label="Ambulance from side A"
            >
              🚑 from A
            </button>
            <button
              type="button"
              className="btn-warn"
              onClick={() => ambulance('B')}
              aria-label="Ambulance from side B"
            >
              🚑 from B
            </button>
          </div>
        </section>

        {/* Force phase */}
        <section>
          <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">
            Force phase
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className="btn-success"
              onClick={() => forcePhase('GREEN_A')}
            >
              GREEN A
            </button>
            <button
              type="button"
              className="btn-success"
              onClick={() => forcePhase('GREEN_B')}
            >
              GREEN B
            </button>
          </div>
        </section>

        {/* Emergency stop / resume */}
        <section>
          <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">System</div>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className="btn-danger"
              disabled={stopped}
              onClick={handleStop}
            >
              ⏸ Stop
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!stopped}
              onClick={handleResume}
            >
              ▶ Resume
            </button>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Stop forces ALL_RED and freezes the FSM until Resume.
          </p>
        </section>

        {/* Spawn rates */}
        <section>
          <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">
            Spawn rates
          </div>
          <div className="space-y-3">
            <Slider
              label="Side A (veh/s)"
              value={spawnA}
              onChange={(v) => {
                setSpawnA(v);
                applySpawnRates(v, spawnB);
              }}
              min={0}
              max={3}
              step={0.1}
            />
            <Slider
              label="Side B (veh/s)"
              value={spawnB}
              onChange={(v) => {
                setSpawnB(v);
                applySpawnRates(spawnA, v);
              }}
              min={0}
              max={3}
              step={0.1}
            />
          </div>
        </section>

        {/* Adaptive weights */}
        <section>
          <div className="flex items-center justify-between">
            <div className="text-xs text-slate-500 uppercase tracking-widest">
              Adaptive weights
            </div>
            <span className="text-[10px] text-slate-500">
              mode: {currentMode ?? '—'}
            </span>
          </div>
          <div className="space-y-3 mt-2">
            <Slider
              label="queue"
              value={weights.prioWQueue}
              onChange={(v) => setWeights((w) => ({ ...w, prioWQueue: v }))}
              min={0}
              max={3}
              step={0.05}
            />
            <Slider
              label="wait"
              value={weights.prioWWait}
              onChange={(v) => setWeights((w) => ({ ...w, prioWWait: v }))}
              min={0}
              max={0.5}
              step={0.005}
            />
            <Slider
              label="truck"
              value={weights.prioWTruck}
              onChange={(v) => setWeights((w) => ({ ...w, prioWTruck: v }))}
              min={0}
              max={3}
              step={0.05}
            />
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button
              type="button"
              className="btn-primary"
              onClick={applyWeights}
            >
              Apply
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setWeights(DEFAULT_WEIGHTS)}
            >
              Reset
            </button>
          </div>
        </section>

        {/* Inject stuck vehicle */}
        <section>
          <button
            type="button"
            className="btn w-full justify-center border-dashed border-slate-600 hover:border-accent-yellow/50 hover:text-yellow-200"
            onClick={injectStuck}
            aria-label="Inject a stuck vehicle into the zone"
          >
            🚧 Inject stuck vehicle
          </button>
        </section>

        {/* Feedback */}
        {feedback && (
          <div className="text-xs font-mono text-slate-300" aria-live="polite">
            {feedback}
          </div>
        )}
      </div>
    </div>
  );
}
