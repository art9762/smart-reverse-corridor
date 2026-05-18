"""Adaptive green-phase scheduler."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Settings


@dataclass
class SchedulerInputs:
    """Inputs for the green-phase duration calculation."""

    queue_side: int  # vehicles waiting on the side that's about to go green
    wait_other: float  # how long the other side has been waiting (s)
    other_empty: bool  # is the other side fully empty / no demand


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class Scheduler:
    """Calculate `T_green` for the adaptive mode and pick the next phase.

    Formula (per FSM.md):
        T_green = clamp(
            base + a * queue_side + b * wait_other - c * (1 if other_empty else 0),
            GREEN_MIN_S, GREEN_MAX_S
        )
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # Hot-reload of weights and timings from /config
    def update(self, **kwargs: float) -> None:
        for k, v in kwargs.items():
            if hasattr(self.settings, k) and v is not None:
                setattr(self.settings, k, type(getattr(self.settings, k))(v))

    def baseline_green(self) -> float:
        """Fixed timer used when mode == 'baseline'."""
        # midpoint between min and max as a sane baseline default
        s = self.settings
        return clamp(
            (s.green_min_s + s.green_max_s) / 2,
            s.green_min_s,
            s.green_max_s,
        )

    def adaptive_green(self, inp: SchedulerInputs) -> float:
        s = self.settings
        a = s.prio_w_queue
        b = s.prio_w_wait
        c = s.prio_w_other_empty
        raw = (
            s.base_green_s
            + a * max(0, inp.queue_side)
            + b * max(0.0, inp.wait_other)
            - c * (1.0 if inp.other_empty else 0.0)
        )
        return clamp(raw, s.green_min_s, s.green_max_s)

    def compute(self, mode: str, inp: SchedulerInputs) -> float:
        if mode == "baseline":
            return self.baseline_green()
        return self.adaptive_green(inp)

    @staticmethod
    def pick_next_side(queue_a: int, queue_b: int, last_side: str | None) -> str:
        """Pick the next side to go green.

        Priority: side with the larger queue. Ties go to the side that *did
        not* run last so we keep alternating fairly.
        """
        if queue_a > queue_b:
            return "A"
        if queue_b > queue_a:
            return "B"
        # tie — alternate
        if last_side == "A":
            return "B"
        return "A"
