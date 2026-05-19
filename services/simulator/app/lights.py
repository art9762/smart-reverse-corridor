"""Traffic-light state for the corridor.

Two modes:

* `baseline` — internal fixed-time controller. Cycles GREEN_A → YELLOW →
  ALL_RED → GREEN_B → YELLOW → ALL_RED → ... using values from
  `SimulatorSettings`.
* `adaptive` — listens to `corridor/state` published (retained) by the
  external controller, and just mirrors `phase`.

`Lights` is intentionally MQTT-agnostic: callers feed it ticks
(`tick(now)`) and may apply external phase updates via `apply_state(...)`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import SimulatorSettings
from .world import Phase

log = logging.getLogger(__name__)


@dataclass
class Lights:
    settings: SimulatorSettings
    mode: str = "baseline"  # "baseline" | "adaptive"
    phase: Phase = Phase.GREEN_A
    phase_started_at: float = 0.0
    # In adaptive mode the controller drives all transitions; we stay on a
    # safe ALL_RED fallback if no state arrived recently.
    last_state_at: float = 0.0
    fallback_after_s: float = 10.0

    # ------------------------------------------------------------------ tick
    def tick(self, now: float) -> Phase:
        """Return the current phase, advancing baseline timers if applicable."""
        if self.mode == "baseline":
            self._tick_baseline(now)
        else:
            # In adaptive mode, fall back to ALL_RED if we lost the controller.
            if (
                self.last_state_at > 0
                and now - self.last_state_at > self.fallback_after_s
                and self.phase != Phase.ALL_RED
            ):
                log.warning("adaptive: controller silent, falling back to ALL_RED")
                self.phase = Phase.ALL_RED
                self.phase_started_at = now
        return self.phase

    def _tick_baseline(self, now: float) -> None:
        elapsed = now - self.phase_started_at
        s = self.settings
        sequence = {
            Phase.GREEN_A: (s.baseline_green_s, Phase.YELLOW_A),
            Phase.YELLOW_A: (s.baseline_yellow_s, Phase.ALL_RED_AFTER_A),
            Phase.ALL_RED_AFTER_A: (s.baseline_all_red_s, Phase.GREEN_B),
            Phase.GREEN_B: (s.baseline_green_s, Phase.YELLOW_B),
            Phase.YELLOW_B: (s.baseline_yellow_s, Phase.ALL_RED_AFTER_B),
            Phase.ALL_RED_AFTER_B: (s.baseline_all_red_s, Phase.GREEN_A),
            # Legacy/fallback entries
            Phase.YELLOW: (s.baseline_yellow_s, Phase.ALL_RED),
            Phase.ALL_RED: (s.baseline_all_red_s, None),
            Phase.RED_BOTH: (s.baseline_all_red_s, Phase.GREEN_A),
            Phase.EMERGENCY_STOP: (999999.0, Phase.EMERGENCY_STOP),
            Phase.INIT: (1.0, Phase.RED_BOTH),
        }
        entry = sequence.get(self.phase)
        if entry is None:
            return
        duration, nxt = entry
        if elapsed < duration:
            return
        if nxt is None:
            # Legacy ALL_RED toggle
            nxt = Phase.GREEN_B if self._last_green is Phase.GREEN_A else Phase.GREEN_A
        log.debug("baseline: %s -> %s after %.1fs", self.phase.value, nxt.value, elapsed)
        if self.phase in (Phase.GREEN_A, Phase.GREEN_B):
            self._last_green = self.phase
        self.phase = nxt
        self.phase_started_at = now

    # Default, overwritten by _tick_baseline once we leave the first green.
    _last_green: Phase = Phase.GREEN_A

    # ------------------------------------------------------------ adaptive
    def apply_state(self, payload: dict, now: float) -> None:
        """Apply an external `corridor/state` snapshot (adaptive mode)."""
        if self.mode != "adaptive":
            return
        phase_str = payload.get("phase")
        if not phase_str:
            log.warning("ignored corridor/state without phase: %s", payload)
            return
        try:
            new_phase = Phase(phase_str)
        except ValueError:
            # Controller may send phases we don't have in our enum (shouldn't
            # happen now, but be defensive). Map unknown to ALL_RED for safety.
            log.warning("unknown phase '%s', treating as ALL_RED", phase_str)
            new_phase = Phase.ALL_RED
        if new_phase != self.phase:
            log.info("adaptive: phase %s -> %s", self.phase.value, new_phase.value)
        self.phase = new_phase
        self.phase_started_at = float(payload.get("phase_started_at", now))
        self.last_state_at = now
