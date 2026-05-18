import { describe, it, expect, beforeEach } from 'vitest';
import { useDashboard, phaseRemaining, phaseElapsed, phaseColor } from '../store';
import type { CamHeartbeat, CorridorAlert, CorridorState, MetricsTick } from '../types';

const sampleState: CorridorState = {
  phase: 'GREEN_A',
  phase_started_at: 1000,
  phase_planned_end_at: 1080,
  inside_A: 3,
  inside_B: 0,
  queue_A: 7,
  queue_B: 12,
  mode: 'adaptive',
  camera_health: { A_in: true, A_out: true, B_in: true, B_out: false },
};

const sampleTick: MetricsTick = {
  ts: 1010,
  throughput_5min: { A: 412, B: 388 },
  avg_delay_5min: { A: 18.4, B: 23.1 },
  queue: { A: 7, B: 12 },
  max_queue_today: { A: 24, B: 31 },
};

describe('dashboard store', () => {
  beforeEach(() => {
    useDashboard.getState().reset();
  });

  it('ingests corridor/state and updates camera health snapshots', () => {
    useDashboard.getState().ingest({ topic: 'corridor/state', payload: sampleState });
    const s = useDashboard.getState();
    expect(s.state).toEqual(sampleState);
    expect(s.cameras.B_out.healthy).toBe(false);
    expect(s.cameras.A_in.healthy).toBe(true);
  });

  it('appends and caps queue/throughput series from metrics ticks', () => {
    const store = useDashboard.getState();
    for (let i = 0; i < 5; i++) {
      store.ingest({
        topic: 'corridor/metrics/tick',
        payload: { ...sampleTick, ts: 1000 + i, queue: { A: i, B: i + 1 } },
      });
    }
    const s = useDashboard.getState();
    expect(s.queueSeries).toHaveLength(5);
    expect(s.queueSeries.at(-1)).toMatchObject({ ts: 1004, A: 4, B: 5 });
    expect(s.throughputSeries).toHaveLength(5);
    expect(s.lastTick?.ts).toBe(1004);
  });

  it('keeps newest alerts first and dismisses by id', () => {
    const a1: CorridorAlert = { ts: 1, level: 'info', code: 'X', detail: 'first' };
    const a2: CorridorAlert = { ts: 2, level: 'warning', code: 'Y', detail: 'second' };
    const store = useDashboard.getState();
    store.ingest({ topic: 'corridor/alerts', payload: a1 });
    store.ingest({ topic: 'corridor/alerts', payload: a2 });
    const after = useDashboard.getState().alerts;
    expect(after[0].detail).toBe('second');
    expect(after[1].detail).toBe('first');
    const id = after[0].id!;
    useDashboard.getState().acknowledgeAlert(id);
    expect(useDashboard.getState().alerts.find((a) => a.id === id)).toBeUndefined();
  });

  it('updates camera fps from heartbeat and ignores unknown camera_ids', () => {
    const hb: CamHeartbeat = { ts: 1, camera_id: 'A_in', fps: 24.7, healthy: true };
    useDashboard.getState().ingest({
      topic: 'corridor/cam/A/in/heartbeat',
      payload: hb,
    });
    expect(useDashboard.getState().cameras.A_in.fps).toBeCloseTo(24.7);

    // unknown id is dropped
    useDashboard.getState().ingest({
      topic: 'corridor/cam/A/in/heartbeat',
      // intentionally bogus camera_id at runtime
      payload: { ts: 2, camera_id: 'C_in' as any, fps: 99, healthy: true },
    });
    expect(useDashboard.getState().cameras.A_in.fps).toBeCloseTo(24.7);
  });

  it('derives countdown helpers from corridor state', () => {
    expect(phaseRemaining(sampleState, 1050)).toBe(30);
    expect(phaseElapsed(sampleState, 1050)).toBe(50);
    expect(phaseColor('GREEN_A')).toBe('green');
    expect(phaseColor('YELLOW_B')).toBe('yellow');
    expect(phaseColor('ALL_RED')).toBe('red');
  });
});
