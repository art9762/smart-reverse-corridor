// Type contracts mirror docs/MQTT.md and docs/ARCHITECTURE.md.

export type Side = 'A' | 'B';
export type Direction = 'in' | 'out';
export type CameraId = 'A_in' | 'A_out' | 'B_in' | 'B_out';

export type Phase =
  | 'RED_BOTH'
  | 'GREEN_A'
  | 'YELLOW_A'
  | 'GREEN_B'
  | 'YELLOW_B'
  | 'ALL_RED';

export type Mode = 'baseline' | 'adaptive';

export type AlertLevel = 'emergency' | 'warning' | 'info';

export type VehicleType = 'car' | 'truck' | 'bus' | 'motorcycle' | 'emergency';

export interface CorridorState {
  phase: Phase;
  phase_started_at: number;
  phase_planned_end_at: number;
  inside_A: number;
  inside_B: number;
  queue_A: number;
  queue_B: number;
  mode: Mode;
  camera_health: Record<CameraId, boolean>;
}

export interface MetricsTick {
  ts: number;
  throughput_5min: { A: number; B: number };
  avg_delay_5min: { A: number; B: number };
  queue: { A: number; B: number };
  max_queue_today: { A: number; B: number };
}

export interface CorridorAlert {
  ts: number;
  level: AlertLevel;
  code: string;
  detail: string;
  id?: string;
}

export interface CamEvent {
  ts: number;
  track_id: number;
  class: 'car' | 'truck' | 'bus' | 'motorcycle' | 'emergency';
  side: Side;
  dir: Direction;
  confidence: number;
  plate: string | null;
}

export interface CamHeartbeat {
  ts: number;
  camera_id: CameraId;
  fps: number;
  healthy: boolean;
}

export interface OverrideCommand {
  action: 'force_phase' | 'emergency_stop' | 'resume' | 'priority' | 'mode_switch';
  phase?: Phase;
  side?: Side;
  mode?: Mode;
  reason?: string;
  by?: string;
}

export interface PriorityWeights {
  PRIO_W_QUEUE: number;
  PRIO_W_WAIT: number;
  PRIO_W_TRUCK: number;
}

/**
 * Single vehicle frame from the simulator (or any future world publisher).
 * Mirrors docs/MQTT.md: `corridor/sim/world`.
 */
export interface WorldVehicle {
  id: number;
  side: Side;
  type: VehicleType;
  /** Normalized position along the corridor [0..1]; 0 = side A entry, 1 = side B entry. */
  x: number;
  /** Lateral offset from lane center (reserved for future maneuvers). */
  y: number;
  /** Speed in m/s. */
  speed: number;
  /** Vehicle length in meters; used to scale the rendered car. */
  len_m: number;
  /** True for an emergency vehicle (ambulance, fire truck, etc.). */
  emergency: boolean;
}

/**
 * Live world snapshot consumed by the dashboard. Pushed at 10–20 Hz from
 * the simulator, ignored by the controller.
 */
export interface WorldSnapshot {
  ts: number;
  zone_length_m: number;
  phase: Phase;
  vehicles: WorldVehicle[];
  queues: { A: number; B: number };
}

export type WSMessage =
  | { topic: 'corridor/state'; payload: CorridorState }
  | { topic: 'corridor/metrics/tick'; payload: MetricsTick }
  | { topic: 'corridor/alerts'; payload: CorridorAlert }
  | { topic: 'corridor/sim/world'; payload: WorldSnapshot }
  | {
      topic: `corridor/cam/${Side}/${Direction}/event`;
      payload: CamEvent;
    }
  | {
      topic: `corridor/cam/${Side}/${Direction}/heartbeat`;
      payload: CamHeartbeat;
    };

export const ALL_CAMERAS: CameraId[] = ['A_in', 'A_out', 'B_in', 'B_out'];
