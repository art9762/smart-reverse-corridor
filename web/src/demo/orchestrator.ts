/**
 * DemoOrchestrator — ties DemoSimulator + DemoController together and feeds
 * the Zustand dashboard store.
 *
 * Architecture:
 *
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │  DemoOrchestrator                                            │
 *   │                                                              │
 *   │  rAF game loop (≈60 fps)                                     │
 *   │    ├─ simulator.tick(dt)  → WorldSnapshot                    │
 *   │    ├─ controller.feedCounts(queue, inside)                   │
 *   │    ├─ controller.tick(now) → Phase                           │
 *   │    ├─ simulator.setPhase(phase)                              │
 *   │    └─ store.ingest(...)  ← publishes to Zustand              │
 *   │                                                              │
 *   │  Scenario runner                                             │
 *   │    └─ fires timed events against the orchestrator API        │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * The orchestrator is exported as a singleton (`demoOrchestrator`) so any
 * component can call its methods without prop-drilling.
 */

import { useDashboard } from '../store';
import type { Phase, Side } from '../types';
import { DemoController } from './controller';
import { DemoSimulator } from './simulator';
import { SCENARIOS, getScenarioInfo } from './scenarios';
import type { ScenarioInfo } from './scenarios';
import type { ScenarioConfig, ScenarioEvent as LegacyScenarioEvent } from './types';

// ── Types ──────────────────────────────────────────────────────────────────

export interface OrchestratorWeights {
  prioWQueue?: number;
  prioWWait?: number;
  prioWOtherEmpty?: number;
  prioWTruck?: number;
  /** Legacy key names used by DemoControlPanel */
  PRIO_W_QUEUE?: number;
  PRIO_W_WAIT?: number;
  PRIO_W_TRUCK?: number;
}

// ── DemoOrchestrator ───────────────────────────────────────────────────────

export class DemoOrchestrator {
  private simulator: DemoSimulator;
  private controller: DemoController;

  private _running = false;
  private _rafHandle: number | null = null;
  private _lastFrameTime: number | null = null;

  // Metrics publish cadence (1 Hz)
  private _lastMetricsPublishMs = 0;
  private readonly METRICS_INTERVAL_MS = 1000;

  // State publish cadence (2 Hz)
  private _lastStatePublishMs = 0;
  private readonly STATE_INTERVAL_MS = 500;

  // Current mode
  private _mode: 'baseline' | 'adaptive' = 'adaptive';

  // Active scenario tracking (named scenarios from scenarios.ts)
  private _activeScenario: string | null = null;
  private _scenarioStartMs: number | null = null;
  private _scenarioEventIdx = 0;
  private _scenarioDurationMs: number | null = null;

  // Active legacy scenario (ScenarioConfig from types.ts, used by DemoApp)
  private _legacyEventHandles: ReturnType<typeof setTimeout>[] = [];

  constructor() {
    this.simulator = new DemoSimulator();
    this.controller = new DemoController();
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  /** Start the game loop. Idempotent. */
  start(): void {
    if (this._running) return;
    this._running = true;

    const nowS = Date.now() / 1000;
    this.controller.boot(nowS);

    // Mark store as connected
    useDashboard.getState().setConnected(true);

    this._scheduleFrame();
  }

  /** Stop the game loop. */
  stop(): void {
    this._running = false;
    if (this._rafHandle !== null) {
      cancelAnimationFrame(this._rafHandle);
      this._rafHandle = null;
    }
    this._lastFrameTime = null;
    useDashboard.getState().setConnected(false);
  }

  /** Reset simulator, controller, and store state. */
  reset(): void {
    const wasRunning = this._running;
    this.stop();

    const nowS = Date.now() / 1000;
    this.simulator.reset();
    this.controller.reset(nowS);
    this._activeScenario = null;
    this._scenarioStartMs = null;
    this._scenarioEventIdx = 0;
    this._scenarioDurationMs = null;
    this._lastMetricsPublishMs = 0;
    this._lastStatePublishMs = 0;

    useDashboard.getState().reset();

    if (wasRunning) this.start();
  }

  isRunning(): boolean {
    return this._running;
  }

  // ── Mode & rates ──────────────────────────────────────────────────────────

  switchMode(mode: 'baseline' | 'adaptive'): void {
    this._mode = mode;
    this.controller.setMode(mode);
    this._emitAlert('info', 'MODE_SWITCH', `Switched to ${mode} mode`);
  }

  setSpawnRates(rateA: number, rateB: number): void {
    this.simulator.setSpawnRates(rateA, rateB);
  }

  setWeights(weights: OrchestratorWeights): void {
    // Support both camelCase and UPPER_SNAKE_CASE key names
    this.controller.setWeights({
      prioWQueue:      weights.prioWQueue      ?? weights.PRIO_W_QUEUE,
      prioWWait:       weights.prioWWait       ?? weights.PRIO_W_WAIT,
      prioWOtherEmpty: weights.prioWOtherEmpty,
      prioWTruck:      weights.prioWTruck      ?? weights.PRIO_W_TRUCK,
    });
  }

  // ── Operator overrides ────────────────────────────────────────────────────

  forcePhase(phase: Phase): void {
    const nowS = Date.now() / 1000;
    this.controller.forcePhase(phase, nowS);
    this.simulator.setPhase(phase);
    this._publishState(nowS);
    this._emitAlert('info', 'FORCE_PHASE', `Phase forced to ${phase}`);
  }

  emergencyStop(): void {
    const nowS = Date.now() / 1000;
    this.controller.emergencyStop(nowS);
    this.simulator.setPhase('ALL_RED');
    this._publishState(nowS);
    this._emitAlert('emergency', 'EMERGENCY_STOP', 'Emergency stop activated');
  }

  resume(): void {
    const nowS = Date.now() / 1000;
    this.controller.resume(nowS);
    this._publishState(nowS);
    this._emitAlert('info', 'RESUME', 'Resumed from emergency stop');
  }

  // ── Scenario injection ────────────────────────────────────────────────────

  /** Inject an emergency vehicle from the given side. */
  triggerAmbulance(side: 'A' | 'B'): void {
    this.simulator.injectEmergency(side);
    this._emitAlert('warning', 'AMBULANCE', `Emergency vehicle entering from side ${side}`);
  }

  /** Inject a stuck vehicle from the given side (defaults to 'A'). */
  triggerStuck(side: Side = 'A'): void {
    this.simulator.injectStuck(side);
    this._emitAlert('warning', 'STUCK_VEHICLE', `Stuck vehicle injected in zone from side ${side}`);
  }

  /** Alias used by DemoControlPanel (no side argument). */
  injectStuck(): void {
    this.triggerStuck('A');
  }

  // ── Scenario runner ───────────────────────────────────────────────────────

  /**
   * Start a predefined scenario.
   *
   * Accepts either:
   *  - a string name (looks up in SCENARIOS registry)
   *  - a ScenarioConfig object (legacy format used by DemoApp)
   */
  runScenario(nameOrConfig: string | ScenarioConfig): void {
    if (typeof nameOrConfig === 'string') {
      this._runNamedScenario(nameOrConfig);
    } else {
      this._runLegacyScenario(nameOrConfig);
    }
  }

  /** Stop the currently running scenario (named or legacy). */
  stopScenario(): void {
    // Cancel legacy scenario timers
    for (const h of this._legacyEventHandles) clearTimeout(h);
    this._legacyEventHandles = [];

    // Cancel named scenario
    if (this._activeScenario) {
      this._emitAlert('info', 'SCENARIO_STOP', `Scenario "${this._activeScenario}" stopped`);
    }
    this._activeScenario = null;
    this._scenarioStartMs = null;
    this._scenarioDurationMs = null;
  }

  private _runNamedScenario(name: string): void {
    const scenario = SCENARIOS[name];
    if (!scenario) {
      console.warn(`[DemoOrchestrator] Unknown scenario: ${name}`);
      return;
    }

    // Reset and apply initial config
    this.reset();
    this.switchMode(scenario.initialMode);
    this.setSpawnRates(scenario.initialRates.A, scenario.initialRates.B);

    // Record scenario start
    this._activeScenario = name;
    this._scenarioStartMs = Date.now();
    this._scenarioEventIdx = 0;
    this._scenarioDurationMs = scenario.duration * 1000;

    this._emitAlert('info', 'SCENARIO_START', `Scenario "${scenario.label}" started`);

    // Start the loop if not already running
    if (!this._running) this.start();
  }

  /**
   * Run a legacy ScenarioConfig (from types.ts / DemoApp).
   * Events are scheduled via setTimeout using their `delayMs` field.
   */
  private _runLegacyScenario(sc: ScenarioConfig): void {
    // Cancel any previous legacy scenario
    for (const h of this._legacyEventHandles) clearTimeout(h);
    this._legacyEventHandles = [];

    // Apply initial config
    if (sc.config.spawnRateA !== undefined || sc.config.spawnRateB !== undefined) {
      this.setSpawnRates(
        sc.config.spawnRateA ?? 0.5,
        sc.config.spawnRateB ?? 0.5,
      );
    }

    // Schedule all events
    for (const ev of sc.events ?? []) {
      const handle = setTimeout(() => this._executeLegacyEvent(ev), ev.delayMs);
      this._legacyEventHandles.push(handle);
    }

    this._emitAlert('info', 'SCENARIO_START', `Scenario "${sc.name}" started`);

    if (!this._running) this.start();
  }

  private _executeLegacyEvent(ev: LegacyScenarioEvent): void {
    switch (ev.type) {
      case 'set_phase':
        if (ev.payload?.phase) this.forcePhase(ev.payload.phase);
        break;
      case 'inject_emergency':
        this.triggerAmbulance((ev.payload?.side ?? 'A') as Side);
        break;
      case 'inject_stuck':
        this.triggerStuck((ev.payload?.side ?? 'A') as Side);
        break;
      case 'set_spawn_rates':
        if (ev.payload?.rateA !== undefined && ev.payload?.rateB !== undefined) {
          this.setSpawnRates(ev.payload.rateA, ev.payload.rateB);
        }
        break;
    }
  }

  getScenarios(): ScenarioInfo[] {
    return getScenarioInfo();
  }

  // ── Game loop ─────────────────────────────────────────────────────────────

  private _scheduleFrame(): void {
    if (!this._running) return;
    this._rafHandle = requestAnimationFrame((ts) => this._frame(ts));
  }

  private _frame(timestampMs: number): void {
    if (!this._running) return;

    // Compute delta time, capped at 100 ms to avoid spiral-of-death on tab focus
    const dtMs = this._lastFrameTime !== null
      ? Math.min(timestampMs - this._lastFrameTime, 100)
      : 16;
    this._lastFrameTime = timestampMs;

    const nowS = Date.now() / 1000;

    // 1. Advance simulator
    const snapshot = this.simulator.tick(dtMs);

    // 2. Feed counts to controller
    this.controller.feedCounts(
      this.simulator.queueA,
      this.simulator.queueB,
      this.simulator.insideA,
      this.simulator.insideB,
    );

    // 3. Controller decides phase
    const phase = this.controller.tick(nowS);

    // 4. Feed phase back to simulator
    this.simulator.setPhase(phase);

    // 5. Publish world snapshot (every frame — high frequency for smooth animation)
    useDashboard.getState().ingest({
      topic: 'corridor/sim/world',
      payload: { ...snapshot, phase },
    });

    // 6. Publish corridor/state at 2 Hz
    if (timestampMs - this._lastStatePublishMs >= this.STATE_INTERVAL_MS) {
      this._lastStatePublishMs = timestampMs;
      this._publishState(nowS);
    }

    // 7. Publish metrics at 1 Hz
    if (timestampMs - this._lastMetricsPublishMs >= this.METRICS_INTERVAL_MS) {
      this._lastMetricsPublishMs = timestampMs;
      this._publishMetrics();
    }

    // 8. Advance scenario events
    this._tickScenario(timestampMs);

    // Schedule next frame
    this._scheduleFrame();
  }

  // ── Scenario tick ─────────────────────────────────────────────────────────

  private _tickScenario(nowMs: number): void {
    if (this._activeScenario === null || this._scenarioStartMs === null) return;

    const scenario = SCENARIOS[this._activeScenario];
    if (!scenario) return;

    const elapsedS = (nowMs - this._scenarioStartMs) / 1000;

    // Fire pending events
    while (
      this._scenarioEventIdx < scenario.events.length &&
      elapsedS >= scenario.events[this._scenarioEventIdx].at
    ) {
      const event = scenario.events[this._scenarioEventIdx];
      try {
        event.action(this);
      } catch (err) {
        console.error(`[DemoOrchestrator] Scenario event error at t=${event.at}s:`, err);
      }
      this._scenarioEventIdx++;
    }

    // Check if scenario has ended
    if (
      this._scenarioDurationMs !== null &&
      nowMs - this._scenarioStartMs >= this._scenarioDurationMs
    ) {
      this._emitAlert('info', 'SCENARIO_END', `Scenario "${scenario.label}" completed`);
      this._activeScenario = null;
      this._scenarioStartMs = null;
      this._scenarioDurationMs = null;
    }
  }

  // ── Store publish helpers ─────────────────────────────────────────────────

  private _publishState(_nowS?: number): void {
    const payload = this.simulator.buildCorridorState(
      this._mode,
      this.controller.phaseStartAt,
      this.controller.phaseEndAt,
    );
    useDashboard.getState().ingest({
      topic: 'corridor/state',
      payload,
    });
  }

  private _publishMetrics(): void {
    const tick = this.simulator.buildMetricsTick();
    useDashboard.getState().ingest({
      topic: 'corridor/metrics/tick',
      payload: tick,
    });
  }

  private _emitAlert(
    level: 'emergency' | 'warning' | 'info',
    code: string,
    detail: string,
  ): void {
    useDashboard.getState().ingest({
      topic: 'corridor/alerts',
      payload: {
        ts: Date.now() / 1000,
        level,
        code,
        detail,
      },
    });
  }
}

// ── Singleton export ───────────────────────────────────────────────────────

export const demoOrchestrator = new DemoOrchestrator();
