import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LiveRoadView } from '../components/LiveRoadView';
import { useDashboard } from '../store';
import type { WorldSnapshot } from '../types';

const baseSnapshot: WorldSnapshot = {
  ts: 1715789123.456,
  zone_length_m: 800,
  phase: 'GREEN_A',
  vehicles: [
    { id: 1, side: 'A', type: 'car', x: 0.18, y: 0.0, speed: 13.4, len_m: 4.5, emergency: false },
    { id: 2, side: 'A', type: 'truck', x: 0.45, y: 0.0, speed: 9.8, len_m: 12.0, emergency: false },
    { id: 3, side: 'B', type: 'emergency', x: 0.72, y: 0.0, speed: 18.0, len_m: 5.5, emergency: true },
    { id: 4, side: 'B', type: 'bus', x: 0.92, y: 0.0, speed: 0.0, len_m: 11.0, emergency: false },
  ],
  queues: { A: 7, B: 12 },
};

describe('<LiveRoadView />', () => {
  beforeEach(() => {
    useDashboard.getState().reset();
  });

  it('shows the waiting overlay when no snapshot is present', () => {
    render(<LiveRoadView now={1715789200} />);
    expect(screen.getByTestId('waiting-overlay')).toBeInTheDocument();
    expect(screen.getByText(/Waiting for simulator/i)).toBeInTheDocument();
    // No vehicle nodes when there is no snapshot.
    expect(document.querySelectorAll('[data-testid^="vehicle-"]')).toHaveLength(0);
  });

  it('renders one vehicle per snapshot entry, sorted left-to-right by x', () => {
    useDashboard.getState().ingestWorld(baseSnapshot);
    render(<LiveRoadView now={1715789200} />);

    const nodes = Array.from(
      document.querySelectorAll<SVGGElement>('[data-testid^="vehicle-"]'),
    );
    expect(nodes).toHaveLength(baseSnapshot.vehicles.length);

    const idsInOrder = nodes.map((n) => n.getAttribute('data-testid'));
    expect(idsInOrder).toEqual([
      'vehicle-1',
      'vehicle-2',
      'vehicle-3',
      'vehicle-4',
    ]);

    // Waiting overlay must be gone once we have a snapshot.
    expect(screen.queryByTestId('waiting-overlay')).toBeNull();
  });

  it('preserves vehicle types so the renderer can color them correctly', () => {
    useDashboard.getState().ingestWorld(baseSnapshot);
    render(<LiveRoadView now={1715789200} />);

    const types = Array.from(
      document.querySelectorAll<SVGGElement>('[data-testid^="vehicle-"]'),
    ).map((n) => n.getAttribute('data-type'));
    expect(types).toEqual(['car', 'truck', 'emergency', 'bus']);
  });

  it('renders both signal indicators and exposes the live phase via aria-label', () => {
    useDashboard.getState().ingestWorld(baseSnapshot);
    render(<LiveRoadView now={1715789200} />);
    expect(screen.getByTestId('live-signal-A')).toBeInTheDocument();
    expect(screen.getByTestId('live-signal-B')).toBeInTheDocument();
    const svg = screen.getByRole('img');
    expect(svg.getAttribute('aria-label')).toContain('GREEN_A');
    expect(svg.getAttribute('aria-label')).toContain('4 vehicles');
  });

  // -------------------------------------------------------------------
  // Single-lane reverse corridor placement rules:
  //   x < 0           -> queue A (approach)
  //   0 <= x <= 1     -> inside the shared single-lane zone
  //   x > 1           -> queue B (approach)
  // -------------------------------------------------------------------

  it('places vehicles with x<0 into queue A, in [0..1] into the zone, and x>1 into queue B', () => {
    const snap: WorldSnapshot = {
      ts: 1,
      zone_length_m: 600,
      phase: 'GREEN_A',
      vehicles: [
        { id: 10, side: 'A', type: 'car', x: -0.4, y: 0, speed: 0, len_m: 4.5, emergency: false },
        { id: 11, side: 'A', type: 'truck', x: -0.05, y: 0, speed: 0, len_m: 12, emergency: false },
        { id: 20, side: 'A', type: 'car', x: 0.2, y: 0, speed: 8, len_m: 4.5, emergency: false },
        { id: 21, side: 'B', type: 'car', x: 0.85, y: 0, speed: 6, len_m: 4.5, emergency: false },
        { id: 30, side: 'B', type: 'bus', x: 1.05, y: 0, speed: 0, len_m: 11, emergency: false },
        { id: 31, side: 'B', type: 'car', x: 1.4, y: 0, speed: 0, len_m: 4.5, emergency: false },
      ],
      queues: { A: 2, B: 2 },
    };
    useDashboard.getState().ingestWorld(snap);
    render(<LiveRoadView now={2} />);

    const get = (id: number) =>
      document.querySelector<SVGGElement>(`[data-testid="vehicle-${id}"]`);

    expect(get(10)?.getAttribute('data-zone')).toBe('queue_a');
    expect(get(11)?.getAttribute('data-zone')).toBe('queue_a');
    expect(get(20)?.getAttribute('data-zone')).toBe('zone');
    expect(get(21)?.getAttribute('data-zone')).toBe('zone');
    expect(get(30)?.getAttribute('data-zone')).toBe('queue_b');
    expect(get(31)?.getAttribute('data-zone')).toBe('queue_b');
  });

  it('treats the zone boundary x==0 and x==1 as inside the zone', () => {
    const snap: WorldSnapshot = {
      ts: 1,
      zone_length_m: 500,
      phase: 'GREEN_B',
      vehicles: [
        { id: 100, side: 'A', type: 'car', x: 0, y: 0, speed: 0, len_m: 4.5, emergency: false },
        { id: 101, side: 'B', type: 'car', x: 1, y: 0, speed: 0, len_m: 4.5, emergency: false },
      ],
      queues: { A: 0, B: 0 },
    };
    useDashboard.getState().ingestWorld(snap);
    render(<LiveRoadView now={2} />);

    const get = (id: number) =>
      document.querySelector<SVGGElement>(`[data-testid="vehicle-${id}"]`);
    expect(get(100)?.getAttribute('data-zone')).toBe('zone');
    expect(get(101)?.getAttribute('data-zone')).toBe('zone');
  });
});
