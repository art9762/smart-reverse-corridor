"""Per-side counters and stuck-vehicle watchdog."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict


@dataclass
class SideCounters:
    """Counters for a single side (A or B)."""

    enter: int = 0
    exit: int = 0
    inside: int = 0
    last_change_ts: float = field(default_factory=time.monotonic)
    last_event_ts: float = 0.0  # wall clock for diagnostics

    def on_enter(self, now: float | None = None) -> None:
        now = now if now is not None else time.monotonic()
        self.enter += 1
        self.inside += 1
        self.last_change_ts = now
        self.last_event_ts = time.time()

    def on_exit(self, now: float | None = None) -> None:
        now = now if now is not None else time.monotonic()
        self.exit += 1
        # never let inside go negative — exit without enter is treated as noise
        if self.inside > 0:
            self.inside -= 1
        self.last_change_ts = now
        self.last_event_ts = time.time()


class Counters:
    """Thread-safe per-side counters with watchdog.

    The MQTT thread mutates counters; the asyncio loop reads them.
    """

    def __init__(self, stuck_threshold_s: int = 30) -> None:
        self._lock = RLock()
        self.stuck_threshold_s = stuck_threshold_s
        self.sides: Dict[str, SideCounters] = {
            "A": SideCounters(),
            "B": SideCounters(),
        }

    def reset(self) -> None:
        with self._lock:
            for s in self.sides.values():
                s.enter = 0
                s.exit = 0
                s.inside = 0
                s.last_change_ts = time.monotonic()

    def on_event(self, side: str, direction: str) -> None:
        side = side.upper()
        if side not in self.sides:
            return
        with self._lock:
            sc = self.sides[side]
            if direction == "in":
                sc.on_enter()
            elif direction == "out":
                sc.on_exit()

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return {
                side: {
                    "enter": sc.enter,
                    "exit": sc.exit,
                    "inside": sc.inside,
                    "last_change_ts": sc.last_change_ts,
                    "last_event_ts": sc.last_event_ts,
                }
                for side, sc in self.sides.items()
            }

    def inside(self, side: str) -> int:
        with self._lock:
            return self.sides[side.upper()].inside

    def total_inside(self) -> int:
        with self._lock:
            return sum(s.inside for s in self.sides.values())

    def is_zone_empty(self) -> bool:
        return self.total_inside() == 0

    def stuck_sides(self, now: float | None = None) -> Dict[str, float]:
        """Return sides whose `inside > 0` for longer than stuck_threshold_s.

        Value is the duration in seconds since the last counter change.
        """
        now = now if now is not None else time.monotonic()
        out: Dict[str, float] = {}
        with self._lock:
            for side, sc in self.sides.items():
                if sc.inside > 0:
                    duration = now - sc.last_change_ts
                    if duration >= self.stuck_threshold_s:
                        out[side] = duration
        return out
