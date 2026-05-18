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
  action: 'force_phase' | 'emergency_stop' | 'resume' | 'priority';
  phase?: Phase;
  side?: Side;
  reason?: string;
  by?: string;
}

export interface PriorityWeights {
  PRIO_W_QUEUE: number;
  PRIO_W_WAIT: number;
  PRIO_W_TRUCK: number;
}

export type WSMessage =
  | { topic: 'corridor/state'; payload: CorridorState }
  | { topic: 'corridor/metrics/tick'; payload: MetricsTick }
  | { topic: 'corridor/alerts'; payload: CorridorAlert }
  | {
      topic: `corridor/cam/${Side}/${Direction}/event`;
      payload: CamEvent;
    }
  | {
      topic: `corridor/cam/${Side}/${Direction}/heartbeat`;
      payload: CamHeartbeat;
    };

export const ALL_CAMERAS: CameraId[] = ['A_in', 'A_out', 'B_in', 'B_out'];
