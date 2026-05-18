"""Phase finite-state machine for the corridor controller.

The FSM itself is synchronous and side-effect free: it just owns the
phase state, transition guards, and timing markers. The asyncio
application loop drives transitions via timers and external events.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from transitions import Machine, MachineError


# -- States --------------------------------------------------------------------

INIT = "INIT"
RED_BOTH = "RED_BOTH"
GREEN_A = "GREEN_A"
YELLOW_A = "YELLOW_A"
ALL_RED_AFTER_A = "ALL_RED_AFTER_A"
GREEN_B = "GREEN_B"
YELLOW_B = "YELLOW_B"
ALL_RED_AFTER_B = "ALL_RED_AFTER_B"
EMERGENCY_STOP = "EMERGENCY_STOP"

STATES = [
    INIT,
    RED_BOTH,
    GREEN_A,
    YELLOW_A,
    ALL_RED_AFTER_A,
    GREEN_B,
    YELLOW_B,
    ALL_RED_AFTER_B,
    EMERGENCY_STOP,
]


# -- Helpers -------------------------------------------------------------------

@dataclass
class FSMTimings:
    """Timing parameters used for guards."""

    yellow_s: float = 3.0
    all_red_guard_s: float = 5.0
    clear_timeout_s: float = 60.0


# -- The FSM -------------------------------------------------------------------

class CorridorFSM:
    """Wraps a `transitions.Machine` with corridor-specific guards.

    External code feeds the FSM:
      * a `zone_empty_fn` returning bool — both insides are zero
      * a `now_fn` — monotonic clock (overridable for tests)

    The FSM tracks `phase_started_at` and `last_yellow_ended_at` so guards
    can verify ALL_RED_GUARD_S has elapsed.
    """

    transitions_spec = [
        # bootstrap
        {"trigger": "boot", "source": INIT, "dest": RED_BOTH},
        # main cycle (A side)
        {"trigger": "go_green_a", "source": [RED_BOTH, ALL_RED_AFTER_B],
         "dest": GREEN_A, "conditions": ["_can_go_green"]},
        {"trigger": "go_yellow", "source": GREEN_A, "dest": YELLOW_A},
        {"trigger": "go_all_red", "source": YELLOW_A, "dest": ALL_RED_AFTER_A,
         "after": "_mark_yellow_ended"},
        # main cycle (B side)
        {"trigger": "go_green_b", "source": [RED_BOTH, ALL_RED_AFTER_A],
         "dest": GREEN_B, "conditions": ["_can_go_green"]},
        {"trigger": "go_yellow", "source": GREEN_B, "dest": YELLOW_B},
        {"trigger": "go_all_red", "source": YELLOW_B, "dest": ALL_RED_AFTER_B,
         "after": "_mark_yellow_ended"},
        # emergency from anywhere
        {"trigger": "emergency", "source": "*", "dest": EMERGENCY_STOP},
        # operator resume
        {"trigger": "resume", "source": EMERGENCY_STOP, "dest": RED_BOTH},
        # operator can also drop to RED_BOTH from a steady (non-yellow) state
        {"trigger": "halt_to_red", "source": [GREEN_A, GREEN_B, RED_BOTH,
                                              ALL_RED_AFTER_A, ALL_RED_AFTER_B],
         "dest": RED_BOTH},
    ]

    def __init__(
        self,
        timings: FSMTimings,
        zone_empty_fn: Callable[[], bool],
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timings = timings
        self._zone_empty_fn = zone_empty_fn
        self._now = now_fn

        # marker timestamps (monotonic seconds)
        self.phase_started_at: float = self._now()
        self.last_yellow_ended_at: Optional[float] = None
        self.last_green_side: Optional[str] = None

        self.machine = Machine(
            model=self,
            states=STATES,
            transitions=self.transitions_spec,
            initial=INIT,
            auto_transitions=False,
            send_event=False,
            after_state_change="_after_state_change",
        )

    # ----- Properties -------------------------------------------------------

    @property
    def phase(self) -> str:
        return self.state  # provided by transitions Machine

    def time_in_phase(self) -> float:
        return self._now() - self.phase_started_at

    # ----- Conditions / hooks ----------------------------------------------

    def _can_go_green(self) -> bool:
        """Guard: zone must be empty and ALL_RED_GUARD_S elapsed since YELLOW."""
        if not self._zone_empty_fn():
            return False
        # If we ever ran a YELLOW, enforce the guard interval.
        if self.last_yellow_ended_at is not None:
            elapsed = self._now() - self.last_yellow_ended_at
            if elapsed < self.timings.all_red_guard_s:
                return False
        return True

    def _mark_yellow_ended(self) -> None:
        self.last_yellow_ended_at = self._now()

    def _after_state_change(self) -> None:
        self.phase_started_at = self._now()
        if self.state == GREEN_A:
            self.last_green_side = "A"
        elif self.state == GREEN_B:
            self.last_green_side = "B"

    # ----- Convenience ------------------------------------------------------

    def try_trigger(self, trigger: str, **kwargs) -> bool:
        """Attempt a transition; return True on success, False if guarded out."""
        method = getattr(self, trigger, None)
        if method is None:
            return False
        try:
            return bool(method(**kwargs))
        except MachineError:
            return False

    def is_emergency(self) -> bool:
        return self.state == EMERGENCY_STOP

    def is_green(self) -> bool:
        return self.state in (GREEN_A, GREEN_B)

    def is_all_red(self) -> bool:
        return self.state in (RED_BOTH, ALL_RED_AFTER_A, ALL_RED_AFTER_B)


@dataclass
class PhaseTimer:
    """Tracks the planned end of the current phase for `corridor/state`."""

    started_at: float = field(default_factory=time.time)
    duration_s: float = 0.0

    @property
    def planned_end_at(self) -> float:
        return self.started_at + self.duration_s

    def restart(self, duration_s: float) -> None:
        self.started_at = time.time()
        self.duration_s = duration_s
