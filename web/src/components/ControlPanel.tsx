import { useState } from 'react';
import { postConfig, postOverride } from '../api/client';
import { modeLabel, useDashboard } from '../store';
import type { Mode, Phase, Side } from '../types';

const DEFAULT_WEIGHTS = { PRIO_W_QUEUE: 1.0, PRIO_W_WAIT: 0.05, PRIO_W_TRUCK: 0.5 };

export function ControlPanel() {
  const state = useDashboard((s) => s.state);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);
  const [stopped, setStopped] = useState(false);

  const runWithLock = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setFeedback(null);
    try {
      await fn();
      setFeedback(`✓ ${key} sent`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'request failed';
      setFeedback(`✗ ${key}: ${msg}`);
    } finally {
      setBusy(null);
      setTimeout(() => setFeedback(null), 3500);
    }
  };

  const switchMode = (mode: Mode) =>
    runWithLock(`mode ${mode}`, () =>
      postOverride({ action: 'mode_switch', mode, by: 'operator' }),
    );

  const ambulance = (side: Side) =>
    runWithLock(`ambulance ${side}`, () =>
      postOverride({
        action: 'priority',
        side,
        reason: 'ambulance',
        by: 'operator',
      }),
    );

  const forcePhase = (phase: Phase) =>
    runWithLock(`force ${phase}`, () =>
      postOverride({ action: 'force_phase', phase, by: 'operator' }),
    );

  const emergency = (action: 'emergency_stop' | 'resume') =>
    runWithLock(action, async () => {
      await postOverride({ action, by: 'operator' });
      setStopped(action === 'emergency_stop');
    });

  const applyWeights = () => runWithLock('weights', () => postConfig(weights));

  return (
    <div className="card">
      <div className="px-5 py-3 border-b border-bg-edge">
        <div className="text-sm uppercase tracking-wider text-slate-400">Панель управления</div>
      </div>
      <div className="p-5 space-y-5">
        <section>
          <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">
            Режим
          </div>
          <div className="grid grid-cols-2 gap-2">
            {(['baseline', 'adaptive'] as Mode[]).map((m) => {
              const active = state?.mode === m;
              return (
                <button
                  key={m}
                  type="button"
                  className={active ? 'btn-primary' : 'btn'}
                  disabled={!!busy || active}
                  onClick={() => switchMode(m)}
                  aria-pressed={active}
                  aria-label={`Переключить на режим: ${modeLabel(m)}`}
                >
                  {active && <span className="mr-1">✓</span>}
                  {modeLabel(m)}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Фиксированный: статичные таймеры. Адаптивный: веса очередь · ожидание · фура.
          </p>
        </section>

        <section>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className="btn-warn"
              disabled={!!busy}
              onClick={() => ambulance('A')}
              aria-label="Скорая со стороны A"
            >
              🚑 со стороны A
            </button>
            <button
              type="button"
              className="btn-warn"
              disabled={!!busy}
              onClick={() => ambulance('B')}
              aria-label="Скорая со стороны B"
            >
              🚑 со стороны B
            </button>
          </div>
        </section>

        <section>
          <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">
            Принудительная фаза
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className="btn-success"
              disabled={!!busy}
              onClick={() => forcePhase('GREEN_A')}
            >
              ЗЕЛЁНЫЙ A
            </button>
            <button
              type="button"
              className="btn-success"
              disabled={!!busy}
              onClick={() => forcePhase('GREEN_B')}
            >
              ЗЕЛЁНЫЙ B
            </button>
          </div>
        </section>

        <section>
          <div className="text-xs text-slate-500 uppercase tracking-widest mb-2">
            Система
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className="btn-danger"
              disabled={!!busy || stopped}
              onClick={() => emergency('emergency_stop')}
            >
              ⏸ Аварийная остановка
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!!busy || !stopped}
              onClick={() => emergency('resume')}
            >
              ▶ Возобновить
            </button>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Остановка включает ALL_RED и замораживает автомат до нажатия «Возобновить».
          </p>
        </section>

        <section>
          <div className="flex items-center justify-between">
            <div className="text-xs text-slate-500 uppercase tracking-widest">
              Веса адаптивного алгоритма
            </div>
            <span className="text-[10px] text-slate-500">
              режим: {state?.mode ?? '—'}
            </span>
          </div>
          <div className="space-y-3 mt-2">
            <Slider
              label="очередь"
              value={weights.PRIO_W_QUEUE}
              onChange={(v) => setWeights((w) => ({ ...w, PRIO_W_QUEUE: v }))}
              min={0}
              max={3}
              step={0.05}
            />
            <Slider
              label="ожидание"
              value={weights.PRIO_W_WAIT}
              onChange={(v) => setWeights((w) => ({ ...w, PRIO_W_WAIT: v }))}
              min={0}
              max={0.5}
              step={0.005}
            />
            <Slider
              label="фура"
              value={weights.PRIO_W_TRUCK}
              onChange={(v) => setWeights((w) => ({ ...w, PRIO_W_TRUCK: v }))}
              min={0}
              max={3}
              step={0.05}
            />
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button type="button" className="btn-primary" disabled={!!busy} onClick={applyWeights}>
              Применить
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setWeights(DEFAULT_WEIGHTS)}
              disabled={!!busy}
            >
              Сброс
            </button>
          </div>
        </section>

        {feedback && (
          <div className="text-xs font-mono text-slate-300" aria-live="polite">
            {feedback}
          </div>
        )}
      </div>
    </div>
  );
}

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
        aria-label={`вес ${label}`}
      />
    </label>
  );
}
