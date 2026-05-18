"""Local metrics calculator.

Runs alongside the simulator so we can compare its in-process numbers with
whatever the controller is publishing on `corridor/metrics/tick`. Useful for
demo "before/after" plots without depending on Influx/Grafana.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .world import Side, Vehicle, World


@dataclass
class _RollingCounter:
    """Counts events in the last `window_s` seconds."""

    window_s: float
    samples: deque = field(default_factory=deque)

    def add(self, ts: float) -> None:
        self.samples.append(ts)
        self._trim(ts)

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_s
        while self.samples and self.samples[0] < cutoff:
            self.samples.popleft()

    def count(self, now: float) -> int:
        self._trim(now)
        return len(self.samples)


@dataclass
class _RollingMean:
    window_s: float
    samples: deque = field(default_factory=deque)  # list of (ts, value).

    def add(self, ts: float, value: float) -> None:
        self.samples.append((ts, value))
        self._trim(ts)

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_s
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()

    def mean(self, now: float) -> float:
        self._trim(now)
        if not self.samples:
            return 0.0
        return sum(v for _, v in self.samples) / len(self.samples)


@dataclass
class LocalMetrics:
    """Throughput / delay / queue tracker per side."""

    window_s: float = 300.0  # 5-minute rolling windows.
    throughput: dict[Side, _RollingCounter] = field(default_factory=dict)
    delays: dict[Side, _RollingMean] = field(default_factory=dict)
    max_queue_today: dict[Side, int] = field(default_factory=lambda: {Side.A: 0, Side.B: 0})

    def __post_init__(self) -> None:
        if not self.throughput:
            self.throughput = {
                Side.A: _RollingCounter(self.window_s),
                Side.B: _RollingCounter(self.window_s),
            }
        if not self.delays:
            self.delays = {
                Side.A: _RollingMean(self.window_s),
                Side.B: _RollingMean(self.window_s),
            }

    def record_exit(self, vehicle: Vehicle, exit_side: Side, now: float) -> None:
        """Called when a vehicle exits the work zone."""
        self.throughput[exit_side].add(now)
        if vehicle.entered_zone_at is not None:
            wait = vehicle.entered_zone_at - vehicle.spawned_at
            # Origin side queue wait — that's the "delay".
            self.delays[vehicle.side].add(now, wait)

    def update_queues(self, world: World) -> None:
        qa, qb = world.queue_lengths()
        self.max_queue_today[Side.A] = max(self.max_queue_today[Side.A], qa)
        self.max_queue_today[Side.B] = max(self.max_queue_today[Side.B], qb)

    def snapshot(self, world: World, now: float) -> dict:
        qa, qb = world.queue_lengths()
        return {
            "ts": now,
            "throughput_5min": {
                "A": self.throughput[Side.A].count(now),
                "B": self.throughput[Side.B].count(now),
            },
            "avg_delay_5min": {
                "A": round(self.delays[Side.A].mean(now), 2),
                "B": round(self.delays[Side.B].mean(now), 2),
            },
            "queue": {"A": qa, "B": qb},
            "max_queue_today": {
                "A": self.max_queue_today[Side.A],
                "B": self.max_queue_today[Side.B],
            },
        }
