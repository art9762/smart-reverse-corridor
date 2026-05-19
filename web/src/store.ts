import { create } from 'zustand';
import type {
  CamEvent,
  CamHeartbeat,
  CameraId,
  CorridorAlert,
  CorridorState,
  MetricsTick,
  Mode,
  Phase,
  WSMessage,
  WorldSnapshot,
} from './types';

const MAX_METRICS_POINTS = 240; // ~4 min at 1 Hz
const MAX_EVENTS = 80;
const MAX_ALERTS = 80;

export interface QueueSeriesPoint {
  ts: number;
  A: number;
  B: number;
}

export interface ThroughputSeriesPoint {
  ts: number;
  A: number;
  B: number;
}

export interface DelaySeriesPoint {
  ts: number;
  A: number;
  B: number;
}

export interface CameraHealthSnapshot {
  id: CameraId;
  healthy: boolean;
  fps: number;
  ts: number;
}

export interface DashboardState {
  state: CorridorState | null;
  lastTick: MetricsTick | null;
  queueSeries: QueueSeriesPoint[];
  throughputSeries: ThroughputSeriesPoint[];
  delaySeries: DelaySeriesPoint[];
  alerts: CorridorAlert[];
  recentEvents: CamEvent[];
  cameras: Record<CameraId, CameraHealthSnapshot>;
  worldSnapshot: WorldSnapshot | null;
  connected: boolean;

  ingest: (msg: WSMessage) => void;
  ingestWorld: (snapshot: WorldSnapshot) => void;
  setConnected: (v: boolean) => void;
  acknowledgeAlert: (id: string) => void;
  reset: () => void;
}

const emptyCameras = (): Record<CameraId, CameraHealthSnapshot> => ({
  A_in: { id: 'A_in', healthy: false, fps: 0, ts: 0 },
  A_out: { id: 'A_out', healthy: false, fps: 0, ts: 0 },
  B_in: { id: 'B_in', healthy: false, fps: 0, ts: 0 },
  B_out: { id: 'B_out', healthy: false, fps: 0, ts: 0 },
});

const isCameraId = (v: string): v is CameraId =>
  v === 'A_in' || v === 'A_out' || v === 'B_in' || v === 'B_out';

let alertCounter = 0;

export const useDashboard = create<DashboardState>((set) => ({
  state: null,
  lastTick: null,
  queueSeries: [],
  throughputSeries: [],
  delaySeries: [],
  alerts: [],
  recentEvents: [],
  cameras: emptyCameras(),
  worldSnapshot: null,
  connected: false,

  setConnected: (v) => set({ connected: v }),

  reset: () =>
    set({
      state: null,
      lastTick: null,
      queueSeries: [],
      throughputSeries: [],
      delaySeries: [],
      alerts: [],
      recentEvents: [],
      cameras: emptyCameras(),
      worldSnapshot: null,
    }),

  acknowledgeAlert: (id) =>
    set((s) => ({ alerts: s.alerts.filter((a) => a.id !== id) })),

  ingestWorld: (snapshot) => set({ worldSnapshot: snapshot }),

  ingest: (msg) =>
    set((prev) => {
      const next: Partial<DashboardState> = {};

      if (msg.topic === 'corridor/state') {
        const cs = msg.payload;
        next.state = cs;
        const cams = { ...prev.cameras };
        for (const k of Object.keys(cs.camera_health) as CameraId[]) {
          const healthy = cs.camera_health[k];
          cams[k] = {
            ...cams[k],
            id: k,
            healthy,
            ts: cs.phase_started_at,
          };
        }
        next.cameras = cams;
      } else if (msg.topic === 'corridor/metrics/tick') {
        const tick = msg.payload;
        next.lastTick = tick;
        next.queueSeries = pushCapped(prev.queueSeries, {
          ts: tick.ts,
          A: tick.queue.A,
          B: tick.queue.B,
        });
        next.throughputSeries = pushCapped(prev.throughputSeries, {
          ts: tick.ts,
          A: tick.throughput_5min.A,
          B: tick.throughput_5min.B,
        });
        next.delaySeries = pushCapped(prev.delaySeries, {
          ts: tick.ts,
          A: tick.avg_delay_5min?.A ?? 0,
          B: tick.avg_delay_5min?.B ?? 0,
        });
      } else if (msg.topic === 'corridor/alerts') {
        const a = msg.payload;
        const id = a.id ?? `alert-${++alertCounter}-${a.ts}`;
        next.alerts = [{ ...a, id }, ...prev.alerts].slice(0, MAX_ALERTS);
      } else if (msg.topic === 'corridor/sim/world') {
        next.worldSnapshot = msg.payload;
      } else if (msg.topic.endsWith('/event')) {
        next.recentEvents = [msg.payload as CamEvent, ...prev.recentEvents].slice(
          0,
          MAX_EVENTS,
        );
      } else if (msg.topic.endsWith('/heartbeat')) {
        const hb = msg.payload as CamHeartbeat;
        if (isCameraId(hb.camera_id)) {
          next.cameras = {
            ...prev.cameras,
            [hb.camera_id]: {
              id: hb.camera_id,
              healthy: hb.healthy,
              fps: hb.fps,
              ts: hb.ts,
            },
          };
        }
      }

      return next;
    }),
}));

function pushCapped<T>(arr: T[], item: T, max = MAX_METRICS_POINTS): T[] {
  const out = arr.length >= max ? arr.slice(arr.length - max + 1) : [...arr];
  out.push(item);
  return out;
}

// Derived helpers

export function phaseRemaining(state: CorridorState | null, nowSec: number): number {
  if (!state) return 0;
  if (!Number.isFinite(state.phase_planned_end_at)) return 0;
  return Math.max(0, Math.round(state.phase_planned_end_at - nowSec));
}

export function phaseElapsed(state: CorridorState | null, nowSec: number): number {
  if (!state) return 0;
  return Math.max(0, Math.round(nowSec - state.phase_started_at));
}

export function phaseTotal(state: CorridorState | null): number {
  if (!state) return 0;
  return Math.max(1, Math.round(state.phase_planned_end_at - state.phase_started_at));
}

export const phaseColor = (p: Phase | undefined | null): string => {
  switch (p) {
    case 'GREEN_A':
    case 'GREEN_B':
      return 'green';
    case 'YELLOW_A':
    case 'YELLOW_B':
      return 'yellow';
    case 'RED_BOTH':
    case 'ALL_RED':
      return 'red';
    default:
      return 'slate';
  }
};

export const modeLabel = (m: Mode | undefined): string =>
  m === 'adaptive' ? 'Адаптивный' : 'Фиксированный';
