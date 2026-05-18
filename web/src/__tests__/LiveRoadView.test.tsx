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
});
