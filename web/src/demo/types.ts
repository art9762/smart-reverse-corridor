/**
 * Demo-specific types for the standalone traffic simulator.
 * These supplement the core types defined in `../types`.
 */

import type { Phase } from '../types';

/** Per-vehicle-type spawn distribution and physics constants. */
export interface VehicleSpec {
  /** Fraction of total spawns (0..1), must sum to 1.0 across all types. */
  weight: number;
  /** Vehicle body length in meters. */
  len_m: number;
  /** Min travel speed inside the zone, m/s. */
  speedMin: number;
  /** Max travel speed inside the zone, m/s. */
  speedMax: number;
}

/** Full configuration for one simulator instance. */
export interface SimConfig {
  /** Length of the single-lane corridor, in meters. Default 800. */
  zoneLengthM: number;
  /** Vehicle spawn rate for side A, vehicles per second. */
  spawnRateA: number;
  /** Vehicle spawn rate for side B, vehicles per second. */
  spawnRateB: number;
  /** Minimum gap between vehicles in queue (bumper-to-bumper), meters. */
  minGapM: number;
  /** How far behind the zone entry vehicles queue (negative x for A, x>1 for B). */
  queueDepthNorm: number;
  /** Snapshot publish interval in ms. Default 50 (20 Hz). */
  tickMs: number;
  /** Per-type physical specs. Keys are VehicleType strings. */
  vehicleSpecs: Record<string, VehicleSpec>;
}

/** Pre-built scenario recipe applied on top of default SimConfig. */
export interface ScenarioConfig {
  name: string;
  description: string;
  /** Overrides applied to default SimConfig. */
  config: Partial<SimConfig>;
  /** Optional sequence of timed events (ms after start). */
  events?: ScenarioEvent[];
}

export type ScenarioEventType =
  | 'set_phase'
  | 'inject_emergency'
  | 'inject_stuck'
  | 'set_spawn_rates';

export interface ScenarioEvent {
  /** Delay in ms from scenario start. */
  delayMs: number;
  type: ScenarioEventType;
  payload?: {
    phase?: Phase;
    side?: 'A' | 'B';
    rateA?: number;
    rateB?: number;
  };
}

/** Internal mutable state for a single simulated vehicle. */
export interface SimVehicle {
  id: number;
  side: 'A' | 'B';
  type: string; // VehicleType string
  /** Normalized position: 0 = A-entry, 1 = B-entry. Queue: <0 for A side, >1 for B side. */
  x: number;
  /** Lateral jitter (cosmetic). */
  y: number;
  /** Current speed in m/s. */
  speed: number;
  /** Assigned cruising speed in m/s. */
  cruiseSpeed: number;
  len_m: number;
  emergency: boolean;
  /** True if artificially stuck via injectStuck. */
  stuck: boolean;
  /** True once the vehicle is inside the zone [0..1]. */
  inZone: boolean;
}
