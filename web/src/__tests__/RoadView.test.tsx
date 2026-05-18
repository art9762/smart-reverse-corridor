import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RoadView } from '../components/RoadView';
import { useDashboard } from '../store';
import type { CorridorState } from '../types';

const baseState: CorridorState = {
  phase: 'GREEN_A',
  phase_started_at: 1000,
  phase_planned_end_at: 1080,
  inside_A: 2,
  inside_B: 1,
  queue_A: 4,
  queue_B: 7,
  mode: 'adaptive',
  camera_health: { A_in: true, A_out: true, B_in: true, B_out: true },
};

describe('<RoadView />', () => {
  beforeEach(() => {
    useDashboard.getState().reset();
  });

  it('renders an SVG region with a corridor label', () => {
    render(<RoadView now={1010} />);
    const svg = screen.getByRole('img');
    expect(svg.tagName.toLowerCase()).toBe('svg');
    expect(svg.getAttribute('aria-label')).toContain('phase');
  });

  it('reflects queue counts from the store', () => {
    useDashboard.getState().ingest({ topic: 'corridor/state', payload: baseState });
    render(<RoadView now={1010} />);
    expect(screen.getByText(/QA: 4/)).toBeInTheDocument();
    expect(screen.getByText(/QB: 7/)).toBeInTheDocument();
  });

  it('updates aria phase label when the state changes', () => {
    useDashboard.getState().ingest({
      topic: 'corridor/state',
      payload: { ...baseState, phase: 'GREEN_B' },
    });
    render(<RoadView now={1010} />);
    const svg = screen.getByRole('img');
    expect(svg.getAttribute('aria-label')).toContain('GREEN_B');
  });

  it('renders signal indicators for both sides', () => {
    useDashboard.getState().ingest({ topic: 'corridor/state', payload: baseState });
    render(<RoadView now={1010} />);
    expect(screen.getByLabelText('Signal A')).toBeInTheDocument();
    expect(screen.getByLabelText('Signal B')).toBeInTheDocument();
  });
});
