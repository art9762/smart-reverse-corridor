/**
 * Predefined demo scenarios.
 *
 * Each scenario is a timed sequence of actions that the orchestrator executes
 * against itself. Actions are plain functions that receive the orchestrator
 * instance so they can call any public method.
 *
 * The `events` array is sorted by `at` (seconds from scenario start) and
 * executed once the elapsed scenario time crosses each threshold.
 */

import type { DemoOrchestrator } from './orchestrator';
import { useDashboard } from '../store';

// ── Scenario types ─────────────────────────────────────────────────────────

export interface ScenarioEvent {
  /** Seconds from scenario start when this action fires. */
  at: number;
  /** Human-readable label shown in the UI. */
  label: string;
  action: (orch: DemoOrchestrator) => void;
}

export interface Scenario {
  name: string;
  /** Short human-readable title for the UI. */
  label: string;
  description: string;
  /** Total scenario duration in seconds (orchestrator stops after this). */
  duration: number;
  initialMode: 'baseline' | 'adaptive';
  initialRates: { A: number; B: number };
  events: ScenarioEvent[];
}

export interface ScenarioInfo {
  name: string;
  label: string;
  description: string;
  duration: number;
  initialMode: 'baseline' | 'adaptive';
}

// ── Scenario definitions ───────────────────────────────────────────────────

/**
 * 1. symmetric — equal flow both sides, 60 s.
 *    Good for showing adaptive vs baseline with balanced demand.
 */
const symmetric: Scenario = {
  name: 'symmetric',
  label: 'Symmetric Flow',
  description: 'Equal traffic on both sides (1.0 veh/s each). Shows adaptive vs baseline with balanced demand.',
  duration: 60,
  initialMode: 'adaptive',
  initialRates: { A: 1.0, B: 1.0 },
  events: [
    {
      at: 30,
      label: 'Switch to baseline',
      action: (o) => o.switchMode('baseline'),
    },
  ],
};

/**
 * 2. asymmetric_peak — heavy A side, light B side, 90 s.
 *    Demonstrates adaptive scheduler giving more green time to the busy side.
 */
const asymmetric_peak: Scenario = {
  name: 'asymmetric_peak',
  label: 'Asymmetric Peak',
  description: 'Heavy A-side traffic (2.0 veh/s) vs light B-side (0.3 veh/s). Adaptive scheduler extends GREEN_A.',
  duration: 90,
  initialMode: 'adaptive',
  initialRates: { A: 2.0, B: 0.3 },
  events: [
    {
      at: 45,
      label: 'Equalise flow',
      action: (o) => o.setSpawnRates(1.0, 1.0),
    },
  ],
};

/**
 * 3. truck_jam — normal flow, stuck truck injected at t=20 s from side A.
 */
const truck_jam: Scenario = {
  name: 'truck_jam',
  label: 'Truck Jam',
  description: 'Normal flow. At t=20 s a truck gets stuck in the zone from side A, blocking the corridor.',
  duration: 90,
  initialMode: 'adaptive',
  initialRates: { A: 0.6, B: 0.6 },
  events: [
    {
      at: 20,
      label: 'Inject stuck truck (A)',
      action: (o) => o.triggerStuck('A'),
    },
    {
      at: 55,
      label: 'Emergency stop',
      action: (o) => o.emergencyStop(),
    },
    {
      at: 65,
      label: 'Resume',
      action: (o) => o.resume(),
    },
  ],
};

/**
 * 4. ambulance — normal flow, ambulance triggered from side B at t=15 s.
 */
const ambulance: Scenario = {
  name: 'ambulance',
  label: 'Ambulance Priority',
  description: 'Normal flow. At t=15 s an ambulance enters from side B — it bypasses the red light.',
  duration: 60,
  initialMode: 'adaptive',
  initialRates: { A: 0.5, B: 0.5 },
  events: [
    {
      at: 15,
      label: 'Ambulance from B',
      action: (o) => o.triggerAmbulance('B'),
    },
    {
      at: 35,
      label: 'Ambulance from A',
      action: (o) => o.triggerAmbulance('A'),
    },
  ],
};

/**
 * 5. camera_lost — normal flow, camera failure alert at t=25 s.
 *    (Visual alert only — the demo simulator doesn't have real cameras.)
 */
const camera_lost: Scenario = {
  name: 'camera_lost',
  label: 'Camera Failure',
  description: 'Normal flow. At t=25 s a camera failure alert is raised (visual only in demo mode).',
  duration: 60,
  initialMode: 'adaptive',
  initialRates: { A: 0.5, B: 0.5 },
  events: [
    {
      at: 25,
      label: 'Camera A_in lost',
      action: () => {
        useDashboard.getState().ingest({
          topic: 'corridor/alerts',
          payload: {
            ts: Date.now() / 1000,
            level: 'warning',
            code: 'CAMERA_LOST',
            detail: 'camera=A_in (simulated failure)',
          },
        });
      },
    },
    {
      at: 45,
      label: 'Camera A_in recovered',
      action: () => {
        useDashboard.getState().ingest({
          topic: 'corridor/alerts',
          payload: {
            ts: Date.now() / 1000,
            level: 'info',
            code: 'CAMERA_RECOVERED',
            detail: 'camera=A_in (simulated recovery)',
          },
        });
      },
    },
  ],
};

/**
 * 6. full_demo — chains multiple phases for a complete showcase.
 *    20 s symmetric → 30 s asymmetric → stuck at 55 s → ambulance at 70 s → 20 s recovery
 */
const full_demo: Scenario = {
  name: 'full_demo',
  label: 'Full Demo',
  description: 'Complete showcase: symmetric → asymmetric peak → stuck truck → ambulance → recovery.',
  duration: 120,
  initialMode: 'adaptive',
  initialRates: { A: 1.0, B: 1.0 },
  events: [
    // 0–20 s: symmetric (initial rates already set)
    {
      at: 20,
      label: 'Asymmetric peak begins',
      action: (o) => o.setSpawnRates(2.0, 0.3),
    },
    {
      at: 50,
      label: 'Equalise flow',
      action: (o) => o.setSpawnRates(0.8, 0.8),
    },
    {
      at: 55,
      label: 'Stuck truck (A)',
      action: (o) => o.triggerStuck('A'),
    },
    {
      at: 70,
      label: 'Ambulance (B)',
      action: (o) => o.triggerAmbulance('B'),
    },
    {
      at: 80,
      label: 'Emergency stop',
      action: (o) => o.emergencyStop(),
    },
    {
      at: 85,
      label: 'Resume',
      action: (o) => o.resume(),
    },
    {
      at: 90,
      label: 'Recovery flow',
      action: (o) => o.setSpawnRates(0.6, 0.6),
    },
  ],
};

// ── Registry ───────────────────────────────────────────────────────────────

export const SCENARIOS: Record<string, Scenario> = {
  symmetric,
  asymmetric_peak,
  truck_jam,
  ambulance,
  camera_lost,
  full_demo,
};

export function getScenarioInfo(): ScenarioInfo[] {
  return Object.values(SCENARIOS).map(({ name, label, description, duration, initialMode }) => ({
    name,
    label,
    description,
    duration,
    initialMode,
  }));
}
