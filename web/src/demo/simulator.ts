/**
 * DemoSimulator — pure-TypeScript in-browser traffic simulator.
 *
 * Mirrors the Python `services/simulator` behaviour:
 *  - spawns vehicles on both sides of the corridor
 *  - moves them through a queue zone, then through the corridor itself
 *  - respects the current phase (GREEN_A lets A-side vehicles enter, etc.)
 *  - publishes WorldSnapshot snapshots and corridor/state ticks
 *
 * The simulator is deliberately MQTT-agnostic; the orchestrator wires it to
 * the Zustand store.
 */

import type { Phase, Side, VehicleType, WorldSnapshot, WorldVehicle } from '../types';
import type { SimConfig, SimVehicle } from './types';

// ── Default configuration ──────────────────────────────────────────────────

export const DEFAULT_SIM_CONFIG: SimConfig = {
  zoneLengthM: 800,
  spawnRateA: 0.4,   // vehicles per second
  spawnRateB: 0.4,
  minGapM: 8,
  queueDepthNorm: 0.03, // how far behind zone entry vehicles queue (normalised)
  tickMs: 50,          // 20 Hz world publish
  vehicleSpecs: {
    car:         { weight: 0.70, len_m: 4.5,  speedMin: 45,  speedMax: 70 },
    truck:       { weight: 0.15, len_m: 12.0, speedMin: 30,  speedMax: 50 },
    bus:         { weight: 0.08, len_m: 10.0, speedMin: 30,  speedMax: 50 },
    motorcycle:  { weight: 0.05, len_m: 2.2,  speedMin: 50,  speedMax: 80 },
    emergency:   { weight: 0.02, len_m: 5.5,  speedMin: 60,  speedMax: 90 },
  },
};

// ── Helpers ────────────────────────────────────────────────────────────────

function pickVehicleType(specs: SimConfig['vehicleSpecs']): VehicleType {
  const r = Math.random();
  let cumulative = 0;
  for (const [type, spec] of Object.entries(specs)) {
    cumulative += spec.weight;
    if (r < cumulative) return type as VehicleType;
  }
  return 'car';
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

// ── DemoSimulator ──────────────────────────────────────────────────────────

export class DemoSimulator {
  private config: SimConfig;
  private vehicles: Map<number, SimVehicle> = new Map();
  private nextId = 1;
  private phase: Phase = 'RED_BOTH';
  private simTimeS = 0;         // simulated wall-clock seconds
  private lastSpawnA = 0;       // last spawn time for side A (sim seconds)
  private lastSpawnB = 0;
  private _insideA = 0;         // vehicles currently in the zone from side A
  private _insideB = 0;
  private _queueA = 0;          // vehicles waiting in queue on side A
  private _queueB = 0;
  private throughputA = 0;
  private throughputB = 0;
  private delayA: number[] = [];
  private delayB: number[] = [];
  private entryTimes: Map<number, { side: Side; t: number }> = new Map();
  private maxQueueA = 0;
  private maxQueueB = 0;

  constructor(config: Partial<SimConfig> = {}) {
    this.config = { ...DEFAULT_SIM_CONFIG, ...config };
  }

  // ── Public API ────────────────────────────────────────────────────────────

  /** Apply an external phase change (driven by the controller). */
  setPhase(phase: Phase): void {
    this.phase = phase;
  }

  /** Override spawn rates at runtime. */
  setSpawnRates(rateA: number, rateB: number): void {
    this.config.spawnRateA = rateA;
    this.config.spawnRateB = rateB;
  }

  /** Apply partial config overrides. */
  applyConfig(partial: Partial<SimConfig>): void {
    this.config = { ...this.config, ...partial };
  }

  /** Force-inject an emergency vehicle from the given side. */
  injectEmergency(side: Side): void {
    this._spawnVehicle(side, 'emergency');
  }

  /**
   * Inject a "stuck" vehicle — parks one truck in the zone from the given
   * side, blocking until removed.
   */
  injectStuck(side: Side): void {
    const veh = this._spawnVehicle(side, 'truck');
    veh.stuck = true;
    // Place it roughly 40 % of the way through the zone
    veh.x = side === 'A' ? 0.4 : 0.6;
    veh.inZone = true;
    veh.speed = 0;
  }

  /** Read-only queue lengths (for the controller). */
  get queueA(): number { return this._queueA; }
  get queueB(): number { return this._queueB; }

  /** Read-only inside counts (for the controller zone-empty guard). */
  get insideA(): number { return this._insideA; }
  get insideB(): number { return this._insideB; }

  /**
   * Advance simulation by `dtMs` milliseconds.
   * Returns a WorldSnapshot ready to be published.
   */
  tick(dtMs: number): WorldSnapshot {
    const dtS = dtMs / 1000;
    this.simTimeS += dtS;

    this._spawnVehicles(dtS);
    this._moveVehicles(dtS);
    this._pruneExited();
    this._recount();

    return this._buildSnapshot();
  }

  /** Build corridor/metrics/tick payload. */
  buildMetricsTick(): {
    ts: number;
    throughput_5min: { A: number; B: number };
    avg_delay_5min: { A: number; B: number };
    queue: { A: number; B: number };
    max_queue_today: { A: number; B: number };
  } {
    const avgDelay = (arr: number[]) =>
      arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;

    return {
      ts: Date.now() / 1000,
      throughput_5min: { A: this.throughputA, B: this.throughputB },
      avg_delay_5min: {
        A: Math.round(avgDelay(this.delayA) * 10) / 10,
        B: Math.round(avgDelay(this.delayB) * 10) / 10,
      },
      queue: { A: this._queueA, B: this._queueB },
      max_queue_today: { A: this.maxQueueA, B: this.maxQueueB },
    };
  }

  /** Build corridor/state payload. */
  buildCorridorState(mode: 'baseline' | 'adaptive', phaseStartedAt: number, phaseEndAt: number) {
    return {
      phase: this.phase,
      phase_started_at: phaseStartedAt,
      phase_planned_end_at: phaseEndAt,
      inside_A: this._insideA,
      inside_B: this._insideB,
      queue_A: this._queueA,
      queue_B: this._queueB,
      mode,
      camera_health: {
        A_in: true, A_out: true, B_in: true, B_out: true,
      } as Record<string, boolean>,
    };
  }

  /** Reset all sim state. */
  reset(): void {
    this.vehicles.clear();
    this.nextId = 1;
    this.phase = 'RED_BOTH';
    this.simTimeS = 0;
    this.lastSpawnA = 0;
    this.lastSpawnB = 0;
    this._insideA = 0;
    this._insideB = 0;
    this._queueA = 0;
    this._queueB = 0;
    this.throughputA = 0;
    this.throughputB = 0;
    this.delayA = [];
    this.delayB = [];
    this.entryTimes.clear();
    this.maxQueueA = 0;
    this.maxQueueB = 0;
  }

  // ── Internal simulation step ──────────────────────────────────────────────

  private _spawnVehicles(_dtS: number): void {
    const intervalA = 1 / Math.max(0.01, this.config.spawnRateA);
    const intervalB = 1 / Math.max(0.01, this.config.spawnRateB);

    if (this.simTimeS - this.lastSpawnA >= intervalA) {
      this.lastSpawnA = this.simTimeS;
      this._spawnVehicle('A');
    }
    if (this.simTimeS - this.lastSpawnB >= intervalB) {
      this.lastSpawnB = this.simTimeS;
      this._spawnVehicle('B');
    }
  }

  private _spawnVehicle(side: Side, forceType?: VehicleType): SimVehicle {
    const type = forceType ?? pickVehicleType(this.config.vehicleSpecs);
    const spec = this.config.vehicleSpecs[type] ?? this.config.vehicleSpecs.car;
    const cruise = spec.speedMin + Math.random() * (spec.speedMax - spec.speedMin);
    const lenNorm = spec.len_m / this.config.zoneLengthM;
    const gapNorm = this.config.minGapM / this.config.zoneLengthM;

    // Find the tail of the existing queue to stack behind it
    let tailX: number;
    if (side === 'A') {
      // Queue is at x < 0. Tail = lowest x among queued A vehicles
      tailX = 0;
      for (const v of this.vehicles.values()) {
        if (v.side === 'A' && v.x < 0 && v.x < tailX) {
          tailX = v.x - (v.len_m / this.config.zoneLengthM) - gapNorm;
        }
      }
      // Place new vehicle behind the tail
      const x = Math.min(tailX - lenNorm - gapNorm, -(this.config.queueDepthNorm));
      const veh: SimVehicle = {
        id: this.nextId++, side, type, x,
        y: (Math.random() - 0.5) * 0.015,
        speed: 0, cruiseSpeed: cruise, len_m: spec.len_m,
        emergency: type === 'emergency', stuck: false, inZone: false,
      };
      this.vehicles.set(veh.id, veh);
      return veh;
    } else {
      // Queue is at x > 1. Tail = highest x among queued B vehicles
      tailX = 1;
      for (const v of this.vehicles.values()) {
        if (v.side === 'B' && v.x > 1 && v.x > tailX) {
          tailX = v.x + (v.len_m / this.config.zoneLengthM) + gapNorm;
        }
      }
      const x = Math.max(tailX + lenNorm + gapNorm, 1 + this.config.queueDepthNorm);
      const veh: SimVehicle = {
        id: this.nextId++, side, type, x,
        y: (Math.random() - 0.5) * 0.015,
        speed: 0, cruiseSpeed: cruise, len_m: spec.len_m,
        emergency: type === 'emergency', stuck: false, inZone: false,
      };
      this.vehicles.set(veh.id, veh);
      return veh;
    }
  }

  private _moveVehicles(dtS: number): void {
    // Sort by x for collision detection: A-side vehicles travel 0→1, B-side 1→0
    const sortedA = [...this.vehicles.values()]
      .filter(v => v.side === 'A')
      .sort((a, b) => b.x - a.x); // descending: leading vehicle first

    const sortedB = [...this.vehicles.values()]
      .filter(v => v.side === 'B')
      .sort((a, b) => a.x - b.x); // ascending: leading vehicle first

    for (const veh of sortedA) this._moveOne(veh, sortedA, dtS);
    for (const veh of sortedB) this._moveOne(veh, sortedB, dtS);
  }

  private _moveOne(veh: SimVehicle, siblings: SimVehicle[], dtS: number): void {
    if (veh.stuck) return;

    const lenNorm = veh.len_m / this.config.zoneLengthM;
    const minGapNorm = this.config.minGapM / this.config.zoneLengthM;
    const dtClamped = Math.min(dtS, 0.1);

    // Determine if this vehicle is allowed to enter the zone
    const canEnter = this._canEnter(veh);

    // If vehicle has passed through the zone exit, just drive off at cruise
    const pastExit = (veh.side === 'A' && veh.inZone && veh.x >= 0.95) ||
                     (veh.side === 'B' && veh.inZone && veh.x <= 0.05);
    if (pastExit) {
      veh.speed = veh.cruiseSpeed;
      const deltaNorm = (veh.speed * dtClamped) / this.config.zoneLengthM;
      if (veh.side === 'A') { veh.x += deltaNorm; } else { veh.x -= deltaNorm; }
      return;
    }

    // Find the vehicle immediately ahead
    const ahead = this._findLeader(veh, siblings);

    // Compute gap to stop-line and gap to leader (in normalized units)
    let gapToStop: number;
    let gapToLeader: number;

    if (veh.side === 'A') {
      // Stop at zone entry (x=0) if red, otherwise no stop-line constraint
      const stopLine = canEnter ? Infinity : 0.0;
      gapToStop = stopLine === Infinity ? Infinity : (stopLine - veh.x);
      gapToLeader = ahead ? (ahead.x - lenNorm - minGapNorm) - veh.x : Infinity;
    } else {
      const stopLine = canEnter ? -Infinity : 1.0;
      gapToStop = stopLine === -Infinity ? Infinity : (veh.x - stopLine);
      gapToLeader = ahead ? veh.x - (ahead.x + lenNorm + minGapNorm) : Infinity;
    }

    // Effective gap is the minimum of both constraints
    const gap = Math.min(gapToStop, gapToLeader);

    // IDM-like target speed: smooth deceleration based on gap
    const comfortGap = lenNorm * 4 + minGapNorm * 3; // comfortable following distance
    let targetSpeed: number;

    if (gap <= 0) {
      targetSpeed = 0;
    } else if (gap >= comfortGap) {
      targetSpeed = veh.cruiseSpeed;
    } else {
      // Smooth quadratic ramp
      const ratio = gap / comfortGap;
      targetSpeed = veh.cruiseSpeed * ratio * ratio;
    }

    // Emergency vehicles always move at cruise
    if (veh.emergency) targetSpeed = veh.cruiseSpeed;

    // Smooth acceleration / deceleration
    const accelRate = 12.0;
    const decelRate = 20.0;
    if (targetSpeed > veh.speed) {
      veh.speed = Math.min(targetSpeed, veh.speed + accelRate * dtClamped);
    } else {
      veh.speed = Math.max(0, veh.speed - decelRate * dtClamped);
    }

    // Move (speed is in m/s, normalize by zone length)
    const deltaNorm = (veh.speed * dtClamped) / this.config.zoneLengthM;
    if (veh.side === 'A') {
      veh.x += deltaNorm;
    } else {
      veh.x -= deltaNorm;
    }

    // Track zone entry for throughput / delay
    if (!veh.inZone && veh.x >= 0 && veh.x <= 1) {
      veh.inZone = true;
      this.entryTimes.set(veh.id, { side: veh.side, t: this.simTimeS });
    }
  }

  private _canEnter(veh: SimVehicle): boolean {
    // Emergency vehicles always pass
    if (veh.emergency) return true;
    // Already inside the zone
    if (veh.inZone && veh.x >= 0 && veh.x <= 1) return true;

    if (veh.side === 'A') {
      return this.phase === 'GREEN_A';
    } else {
      return this.phase === 'GREEN_B';
    }
  }

  private _findLeader(veh: SimVehicle, siblings: SimVehicle[]): SimVehicle | null {
    // Leader: same side, closer to the destination end
    if (veh.side === 'A') {
      // Travelling left→right (x increasing). Leader is the one with higher x among vehicles
      // that are ahead of this one.
      let closest: SimVehicle | null = null;
      for (const other of siblings) {
        if (other.id === veh.id) continue;
        if (other.x > veh.x) {
          if (!closest || other.x < closest.x) closest = other;
        }
      }
      return closest;
    } else {
      // Travelling right→left (x decreasing). Leader has lower x.
      let closest: SimVehicle | null = null;
      for (const other of siblings) {
        if (other.id === veh.id) continue;
        if (other.x < veh.x) {
          if (!closest || other.x > closest.x) closest = other;
        }
      }
      return closest;
    }
  }

  private _pruneExited(): void {
    for (const [id, veh] of this.vehicles) {
      const exited = veh.side === 'A' ? veh.x > 1.15 : veh.x < -0.15;
      if (exited) {
        // Record throughput and delay
        if (veh.side === 'A') {
          this.throughputA++;
        } else {
          this.throughputB++;
        }
        const entry = this.entryTimes.get(id);
        if (entry) {
          const delay = this.simTimeS - entry.t;
          if (delay > 0) {
            if (veh.side === 'A') {
              this.delayA = [...this.delayA.slice(-500), delay];
            } else {
              this.delayB = [...this.delayB.slice(-500), delay];
            }
          }
          this.entryTimes.delete(id);
        }
        this.vehicles.delete(id);
      }
    }
  }

  private _recount(): void {
    let qA = 0, qB = 0, iA = 0, iB = 0;
    for (const veh of this.vehicles.values()) {
      if (veh.x >= 0 && veh.x <= 1) {
        // Inside zone
        if (veh.side === 'A') iA++; else iB++;
      } else {
        // In queue
        if (veh.side === 'A') qA++; else qB++;
      }
    }
    this._queueA = qA;
    this._queueB = qB;
    this._insideA = iA;
    this._insideB = iB;
    this.maxQueueA = Math.max(this.maxQueueA, qA);
    this.maxQueueB = Math.max(this.maxQueueB, qB);
  }

  private _buildSnapshot(): WorldSnapshot {
    const vehicles: WorldVehicle[] = [];
    for (const veh of this.vehicles.values()) {
      vehicles.push({
        id: veh.id,
        side: veh.side,
        type: veh.type as VehicleType,
        x: clamp(veh.x, -this.config.queueDepthNorm - 0.1, 1 + this.config.queueDepthNorm + 0.1),
        y: veh.y,
        speed: veh.speed,
        len_m: veh.len_m,
        emergency: veh.emergency,
      });
    }

    return {
      ts: Date.now() / 1000,
      zone_length_m: this.config.zoneLengthM,
      phase: this.phase,
      vehicles,
      queues: { A: this._queueA, B: this._queueB },
    };
  }
}
