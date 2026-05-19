#!/usr/bin/env python3
"""Generate realistic sample benchmark results (CSV + graphs) without Docker.

This script synthesises metric ticks that match the format produced by
``scripts/bench.py`` so that ``scripts/plot_results.py`` can consume them
directly.  The generated data is intentionally realistic: the adaptive
controller outperforms the fixed-timer baseline on asymmetric and truck-heavy
loads, while both perform similarly on symmetric traffic.

Usage
-----

.. code-block:: bash

    # Default: all three demo scenarios, 120 s simulated time, output to runs/sample/
    python scripts/generate_sample_results.py

    # Custom output dir and duration
    python scripts/generate_sample_results.py --out runs/my-sample --duration 300

    # Skip graph generation (CSV only)
    python scripts/generate_sample_results.py --no-plot

The generated run directory can be fed straight into plot_results.py:

.. code-block:: bash

    python scripts/plot_results.py runs/sample/
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# CSV schema (must match bench.py METRIC_FIELDS exactly)
# ---------------------------------------------------------------------------

METRIC_FIELDS = [
    "ts",
    "mode",
    "scenario",
    "phase",
    "throughput_A",
    "throughput_B",
    "queue_A",
    "queue_B",
    "avg_delay_A",
    "avg_delay_B",
    "max_queue_today_A",
    "max_queue_today_B",
]

# ---------------------------------------------------------------------------
# Scenario parameters
# ---------------------------------------------------------------------------

@dataclass
class ScenarioParams:
    name: str
    rate_a: float           # vehicle arrivals per second from A
    rate_b: float           # vehicle arrivals per second from B
    truck_share: float      # fraction that are trucks (slower)
    description: str = ""


SCENARIOS: dict[str, ScenarioParams] = {
    "symmetric": ScenarioParams(
        name="symmetric",
        rate_a=1.0,
        rate_b=1.0,
        truck_share=0.05,
        description="Even traffic both ways",
    ),
    "asymmetric_peak": ScenarioParams(
        name="asymmetric_peak",
        rate_a=0.55,
        rate_b=0.10,
        truck_share=0.05,
        description="Asymmetric peak hour — A heavy, B light",
    ),
    "truck_jam": ScenarioParams(
        name="truck_jam",
        rate_a=0.25,
        rate_b=0.25,
        truck_share=0.45,
        description="High truck share with scripted burst",
    ),
}

# ---------------------------------------------------------------------------
# Simulation model
# ---------------------------------------------------------------------------

# Each tick is 1 second of simulated time.
# The model tracks a simple queue on each side and computes throughput /
# delay / queue length as the controller would publish them.

TICK_S = 1.0               # seconds between metric ticks
METRICS_WINDOW_S = 300.0   # rolling window matching engine._metrics_window_s


@dataclass
class SimState:
    """Mutable per-tick simulation state."""

    queue_a: float = 0.0
    queue_b: float = 0.0
    # Rolling throughput: list of (simulated_ts, side) entry events
    throughput_events_a: list[float] = field(default_factory=list)
    throughput_events_b: list[float] = field(default_factory=list)
    # Recent delays for averaging
    delays_a: list[float] = field(default_factory=list)
    delays_b: list[float] = field(default_factory=list)
    max_queue_a: float = 0.0
    max_queue_b: float = 0.0
    # Phase management
    phase: str = "GREEN_A"
    phase_remaining_s: float = 0.0
    mode: str = "adaptive"
    # Track entry timestamps for delay calculation
    pending_a: list[float] = field(default_factory=list)  # entry timestamps
    pending_b: list[float] = field(default_factory=list)


def _baseline_green_s() -> float:
    """Fixed 60 s green for baseline controller."""
    return 60.0


def _adaptive_green_s(queue_mine: float, queue_other: float, wait_other: float) -> float:
    """Simplified adaptive green time matching the real scheduler heuristics.

    The real scheduler (services/controller/app/scheduler.py) uses a weighted
    priority score; we approximate it here with a proportional formula that
    matches the documented behaviour.
    """
    base = 30.0
    queue_bonus = min(queue_mine * 3.0, 60.0)
    wait_bonus = min(wait_other * 0.4, 40.0)
    # Penalise if other side is also heavy
    if queue_other > 5:
        queue_bonus *= 0.75
    return max(15.0, min(base + queue_bonus + wait_bonus, 120.0))


def _simulate_run(
    scenario: ScenarioParams,
    mode: str,
    duration_s: float,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Return a list of row dicts (one per tick) matching METRIC_FIELDS."""

    state = SimState(mode=mode)
    # Start in GREEN_A with a short initial green
    initial_green = 15.0
    state.phase = "GREEN_A"
    state.phase_remaining_s = initial_green
    state.phase_remaining_s = initial_green

    # For delay tracking — time each side last waited
    wait_started_b = 0.0
    wait_started_a = 0.0

    rows: list[dict[str, Any]] = []
    base_ts = time.time() - duration_s  # back-date so graphs look like a real run

    for tick in range(int(duration_s / TICK_S)):
        sim_ts = base_ts + tick * TICK_S
        now = tick * TICK_S  # relative simulation time

        # ---- Arrivals ----
        arrivals_a = rng.poisson_approx(scenario.rate_a * TICK_S)
        arrivals_b = rng.poisson_approx(scenario.rate_b * TICK_S)

        # Add some truck-burst noise around t=60 for truck_jam
        if scenario.name == "truck_jam" and 60 <= now <= 76:
            arrivals_a += rng.randint(0, 2)
            arrivals_b += rng.randint(0, 2)

        state.queue_a += arrivals_a
        state.queue_b += arrivals_b

        for _ in range(int(arrivals_a)):
            state.pending_a.append(now)
            state.throughput_events_a.append(sim_ts)
        for _ in range(int(arrivals_b)):
            state.pending_b.append(now)
            state.throughput_events_b.append(sim_ts)

        # ---- Phase transitions ----
        state.phase_remaining_s -= TICK_S
        if state.phase_remaining_s <= 0:
            if state.phase == "GREEN_A":
                # Discharge some queue
                discharged = min(state.queue_a, max(1, rng.gauss(4, 1)))
                discharged = max(0, discharged)
                state.queue_a = max(0, state.queue_a - discharged)
                for _ in range(int(discharged)):
                    if state.pending_a:
                        entry = state.pending_a.pop(0)
                        state.delays_a.append(now - entry)
                # Switch to GREEN_B
                state.phase = "GREEN_B"
                if mode == "baseline":
                    next_green = _baseline_green_s()
                else:
                    wait_b = now - wait_started_b
                    next_green = _adaptive_green_s(state.queue_b, state.queue_a, wait_b)
                state.phase_remaining_s = next_green
                wait_started_b = now

            elif state.phase == "GREEN_B":
                discharged = min(state.queue_b, max(1, rng.gauss(4, 1)))
                discharged = max(0, discharged)
                state.queue_b = max(0, state.queue_b - discharged)
                for _ in range(int(discharged)):
                    if state.pending_b:
                        entry = state.pending_b.pop(0)
                        state.delays_b.append(now - entry)
                # Switch to GREEN_A
                state.phase = "GREEN_A"
                if mode == "baseline":
                    next_green = _baseline_green_s()
                else:
                    wait_a = now - wait_started_a
                    next_green = _adaptive_green_s(state.queue_a, state.queue_b, wait_a)
                state.phase_remaining_s = next_green
                wait_started_a = now

        # Continuous slow discharge while green (vehicles trickle through)
        trickle = rng.gauss(0.5, 0.1) * TICK_S
        if state.phase == "GREEN_A" and state.queue_a > 0:
            d = min(state.queue_a, max(0.0, trickle))
            state.queue_a -= d
            for _ in range(max(0, int(d))):
                if state.pending_a:
                    entry = state.pending_a.pop(0)
                    state.delays_a.append(now - entry)
        elif state.phase == "GREEN_B" and state.queue_b > 0:
            d = min(state.queue_b, max(0.0, trickle))
            state.queue_b -= d
            for _ in range(max(0, int(d))):
                if state.pending_b:
                    entry = state.pending_b.pop(0)
                    state.delays_b.append(now - entry)

        # Clamp negatives (floating point noise)
        state.queue_a = max(0.0, state.queue_a)
        state.queue_b = max(0.0, state.queue_b)

        # ---- Update max queue ----
        state.max_queue_a = max(state.max_queue_a, state.queue_a)
        state.max_queue_b = max(state.max_queue_b, state.queue_b)

        # ---- Rolling 5-min throughput ----
        cutoff = sim_ts - METRICS_WINDOW_S
        state.throughput_events_a = [t for t in state.throughput_events_a if t > cutoff]
        state.throughput_events_b = [t for t in state.throughput_events_b if t > cutoff]
        tp_a = len(state.throughput_events_a)
        tp_b = len(state.throughput_events_b)

        # ---- Rolling average delay ----
        # Keep only recent 500 entries (matches engine deque maxlen)
        if len(state.delays_a) > 500:
            state.delays_a = state.delays_a[-500:]
        if len(state.delays_b) > 500:
            state.delays_b = state.delays_b[-500:]
        avg_delay_a = sum(state.delays_a) / len(state.delays_a) if state.delays_a else 0.0
        avg_delay_b = sum(state.delays_b) / len(state.delays_b) if state.delays_b else 0.0

        rows.append({
            "ts": round(sim_ts, 3),
            "mode": mode,
            "scenario": scenario.name,
            "phase": state.phase,
            "throughput_A": tp_a,
            "throughput_B": tp_b,
            "queue_A": round(state.queue_a, 2),
            "queue_B": round(state.queue_b, 2),
            "avg_delay_A": round(avg_delay_a, 2),
            "avg_delay_B": round(avg_delay_b, 2),
            "max_queue_today_A": round(state.max_queue_a, 2),
            "max_queue_today_B": round(state.max_queue_b, 2),
        })

    return rows


# ---------------------------------------------------------------------------
# Poisson-approximate helper on random.Random
# ---------------------------------------------------------------------------

class _PoissonRandom(random.Random):
    """random.Random subclass with a simple Poisson approximation."""

    def poisson_approx(self, lam: float) -> int:
        """Knuth's algorithm for small lambda, normal approx for large."""
        if lam <= 0:
            return 0
        if lam < 30:
            # Knuth
            L = math.exp(-lam)
            k = 0
            p = 1.0
            while p > L:
                k += 1
                p *= self.random()
            return k - 1
        # Normal approximation for large lambda
        val = self.gauss(lam, math.sqrt(lam))
        return max(0, round(val))


# ---------------------------------------------------------------------------
# Write CSV
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: runs/sample/<timestamp>)",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=120.0,
        help="Simulated seconds per mode per scenario (default: 120)",
    )
    p.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Scenario name (repeat for multiple). "
        "Defaults to: symmetric, asymmetric_peak, truck_jam",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for reproducible data (default: 42)",
    )
    p.add_argument(
        "--no-plot",
        action="store_true",
        help="Skip graph generation (CSV only)",
    )
    args = p.parse_args(argv)

    scenario_names = args.scenario or ["symmetric", "asymmetric_peak", "truck_jam"]
    for n in scenario_names:
        if n not in SCENARIOS:
            print(f"error: unknown scenario '{n}'. Known: {sorted(SCENARIOS)}", file=sys.stderr)
            return 1

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out or Path("runs") / f"sample_{ts_str}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = _PoissonRandom(args.seed)
    summary: list[dict[str, Any]] = []

    for sc_name in scenario_names:
        sc = SCENARIOS[sc_name]
        for mode in ("baseline", "adaptive"):
            print(f"  simulating {sc_name}/{mode} for {args.duration:.0f}s …")
            rows = _simulate_run(sc, mode, args.duration, rng)
            csv_path = out_dir / f"{sc_name}__{mode}.csv"
            write_csv(rows, csv_path)
            print(f"    → {csv_path}  ({len(rows)} rows)")
            summary.append({
                "scenario": sc_name,
                "mode": mode,
                "csv": str(csv_path.relative_to(out_dir)),
                "rows": len(rows),
                "duration_s": args.duration,
            })

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nCSV summary: {summary_path}")

    if not args.no_plot:
        print("\nGenerating graphs …")
        plot_script = Path(__file__).parent / "plot_results.py"
        figures_dir = out_dir / "figures"
        result = subprocess.run(
            [sys.executable, str(plot_script), str(out_dir), "--out", str(figures_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"plot_results.py failed:\n{result.stderr}", file=sys.stderr)
            return result.returncode
        for line in result.stdout.strip().splitlines():
            print(f"  graph: {line}")
        print(f"\nAll graphs written to: {figures_dir}")

    print(f"\nSample results ready in: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
