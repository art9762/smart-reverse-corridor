import { describe, it, expect, beforeEach } from 'vitest';
import { useDashboard } from '../store';
import type { WorldSnapshot } from '../types';

const snapshot1: WorldSnapshot = {
  ts: 1.0,
  zone_length_m: 800,
  phase: 'GREEN_A',
  vehicles: [
    { id: 1, side: 'A', type: 'car', x: 0.1, y: 0.0, speed: 12, len_m: 4.5, emergency: false },
  ],
  queues: { A: 1, B: 2 },
};

const snapshot2: WorldSnapshot = {
  ts: 2.0,
  zone_length_m: 800,
  phase: 'YELLOW_A',
  vehicles: [
    { id: 1, side: 'A', type: 'car', x: 0.2, y: 0.0, speed: 14, len_m: 4.5, emergency: false },
    { id: 2, side: 'B', type: 'truck', x: 0.85, y: 0.0, speed: 0, len_m: 12.0, emergency: false },
  ],
  queues: { A: 0, B: 4 },
};

describe('store.ingestWorld', () => {
  beforeEach(() => {
    useDashboard.getState().reset();
  });

  it('starts with worldSnapshot === null', () => {
    expect(useDashboard.getState().worldSnapshot).toBeNull();
  });

  it('updates worldSnapshot on ingestWorld', () => {
    useDashboard.getState().ingestWorld(snapshot1);
    expect(useDashboard.getState().worldSnapshot).toEqual(snapshot1);
  });

  it('replaces the previous snapshot (no history retained)', () => {
    const store = useDashboard.getState();
    store.ingestWorld(snapshot1);
    store.ingestWorld(snapshot2);
    const got = useDashboard.getState().worldSnapshot;
    expect(got).toEqual(snapshot2);
    // Should hold exactly one snapshot — no array, no list of frames.
    expect(got?.vehicles).toHaveLength(2);
    expect(got?.ts).toBe(2.0);
  });

  it('reset() clears worldSnapshot back to null', () => {
    useDashboard.getState().ingestWorld(snapshot1);
    useDashboard.getState().reset();
    expect(useDashboard.getState().worldSnapshot).toBeNull();
  });

  it('also accepts corridor/sim/world via the WSMessage ingest path', () => {
    useDashboard.getState().ingest({
      topic: 'corridor/sim/world',
      payload: snapshot2,
    });
    expect(useDashboard.getState().worldSnapshot).toEqual(snapshot2);
  });
}); 
