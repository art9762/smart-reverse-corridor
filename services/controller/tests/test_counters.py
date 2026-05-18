"""Tests for the per-side counters and stuck watchdog."""

from __future__ import annotations

import time

from app.counters import Counters


def test_basic_enter_exit():
    c = Counters(stuck_threshold_s=10)
    c.on_event("A", "in")
    c.on_event("A", "in")
    c.on_event("A", "out")
    assert c.inside("A") == 1
    assert c.snapshot()["A"]["enter"] == 2
    assert c.snapshot()["A"]["exit"] == 1


def test_inside_never_negative():
    c = Counters()
    c.on_event("B", "out")
    assert c.inside("B") == 0


def test_zone_empty_predicate():
    c = Counters()
    assert c.is_zone_empty()
    c.on_event("A", "in")
    assert not c.is_zone_empty()
    c.on_event("A", "out")
    assert c.is_zone_empty()


def test_stuck_detection_uses_threshold():
    c = Counters(stuck_threshold_s=2)
    c.on_event("A", "in")
    # immediately not stuck
    assert c.stuck_sides(now=time.monotonic()) == {}
    # advance past threshold
    future = time.monotonic() + 5
    stuck = c.stuck_sides(now=future)
    assert "A" in stuck
    assert stuck["A"] >= 2
