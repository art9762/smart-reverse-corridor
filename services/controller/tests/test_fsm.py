"""Tests for the corridor FSM."""

from __future__ import annotations

import time
from typing import List

import pytest

from app.counters import Counters
from app.fsm import (
    ALL_RED_AFTER_A,
    ALL_RED_AFTER_B,
    EMERGENCY_STOP,
    GREEN_A,
    GREEN_B,
    INIT,
    RED_BOTH,
    YELLOW_A,
    YELLOW_B,
    CorridorFSM,
    FSMTimings,
)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += delta


def make_fsm(counters: Counters | None = None,
             timings: FSMTimings | None = None) -> tuple[CorridorFSM, Counters, FakeClock]:
    counters = counters or Counters(stuck_threshold_s=10)
    timings = timings or FSMTimings(yellow_s=3, all_red_guard_s=5, clear_timeout_s=60)
    clock = FakeClock()
    fsm = CorridorFSM(timings, zone_empty_fn=counters.is_zone_empty, now_fn=clock)
    return fsm, counters, clock


def test_boot_to_green_a_when_zone_empty():
    fsm, counters, clock = make_fsm()
    assert fsm.phase == INIT
    assert fsm.try_trigger("boot")
    assert fsm.phase == RED_BOTH
    # zone empty + no prior YELLOW -> can go green immediately
    assert fsm.try_trigger("go_green_a")
    assert fsm.phase == GREEN_A


def test_cannot_go_green_when_zone_not_empty():
    """Safety guard: GREEN_X is forbidden while inside_A or inside_B != 0."""
    fsm, counters, clock = make_fsm()
    fsm.try_trigger("boot")
    counters.on_event("A", "in")  # someone is still in zone A
    # try transition through full cycle
    assert not fsm.try_trigger("go_green_a")
    assert fsm.phase == RED_BOTH
    # now drain
    counters.on_event("A", "out")
    assert counters.is_zone_empty()
    assert fsm.try_trigger("go_green_a")
    assert fsm.phase == GREEN_A


def test_full_cycle_with_all_red_guard():
    fsm, counters, clock = make_fsm()
    fsm.try_trigger("boot")
    assert fsm.try_trigger("go_green_a")
    # GREEN_A -> YELLOW_A -> ALL_RED_AFTER_A
    assert fsm.try_trigger("go_yellow")
    assert fsm.phase == YELLOW_A
    assert fsm.try_trigger("go_all_red")
    assert fsm.phase == ALL_RED_AFTER_A
    # Zone empty but guard not elapsed yet
    assert counters.is_zone_empty()
    assert not fsm.try_trigger("go_green_b")  # guard < 5s
    clock.advance(4.9)
    assert not fsm.try_trigger("go_green_b")
    clock.advance(0.2)  # total 5.1s elapsed
    assert fsm.try_trigger("go_green_b")
    assert fsm.phase == GREEN_B


def test_guard_blocks_green_b_until_zone_clears():
    fsm, counters, clock = make_fsm()
    fsm.try_trigger("boot")
    fsm.try_trigger("go_green_a")
    # Add a vehicle on side B during green A
    counters.on_event("B", "in")
    fsm.try_trigger("go_yellow")
    fsm.try_trigger("go_all_red")
    clock.advance(10)  # plenty of time
    assert not fsm.try_trigger("go_green_b")  # zone not empty
    counters.on_event("B", "out")
    assert fsm.try_trigger("go_green_b")


def test_emergency_from_anywhere_and_resume():
    fsm, counters, clock = make_fsm()
    fsm.try_trigger("boot")
    fsm.try_trigger("go_green_a")
    assert fsm.try_trigger("emergency")
    assert fsm.phase == EMERGENCY_STOP
    # operator resume returns to RED_BOTH
    assert fsm.try_trigger("resume")
    assert fsm.phase == RED_BOTH


def test_emergency_override_forces_safe_path():
    """An emergency in YELLOW should still cleanly land in EMERGENCY_STOP."""
    fsm, counters, clock = make_fsm()
    fsm.try_trigger("boot")
    fsm.try_trigger("go_green_a")
    fsm.try_trigger("go_yellow")
    assert fsm.try_trigger("emergency")
    assert fsm.phase == EMERGENCY_STOP
    fsm.try_trigger("resume")
    assert fsm.phase == RED_BOTH


def test_alternation_across_two_full_cycles():
    fsm, counters, clock = make_fsm()
    fsm.try_trigger("boot")
    expected: List[str] = []
    for side, green, yellow, all_red in (
        ("A", GREEN_A, YELLOW_A, ALL_RED_AFTER_A),
        ("B", GREEN_B, YELLOW_B, ALL_RED_AFTER_B),
        ("A", GREEN_A, YELLOW_A, ALL_RED_AFTER_A),
        ("B", GREEN_B, YELLOW_B, ALL_RED_AFTER_B),
    ):
        clock.advance(10)
        assert fsm.try_trigger(f"go_green_{side.lower()}")
        assert fsm.phase == green
        assert fsm.try_trigger("go_yellow")
        assert fsm.phase == yellow
        assert fsm.try_trigger("go_all_red")
        assert fsm.phase == all_red


def test_zone_clear_timeout_triggers_emergency_via_engine_logic():
    """Independent of the engine, FSM allows emergency from ALL_RED states."""
    fsm, counters, clock = make_fsm(
        timings=FSMTimings(yellow_s=3, all_red_guard_s=2, clear_timeout_s=10)
    )
    fsm.try_trigger("boot")
    fsm.try_trigger("go_green_a")
    counters.on_event("A", "in")  # vehicle that will get stuck
    fsm.try_trigger("go_yellow")
    fsm.try_trigger("go_all_red")
    clock.advance(15)
    # zone still not empty -> guard prevents next green
    assert not fsm.try_trigger("go_green_b")
    # operator/engine raises emergency
    assert fsm.try_trigger("emergency")
    assert fsm.phase == EMERGENCY_STOP


def test_camera_lost_path_drops_to_red_both():
    """`halt_to_red` is allowed from GREEN states for fallback."""
    fsm, counters, clock = make_fsm()
    fsm.try_trigger("boot")
    fsm.try_trigger("go_green_a")
    assert fsm.phase == GREEN_A
    assert fsm.try_trigger("halt_to_red")
    assert fsm.phase == RED_BOTH
