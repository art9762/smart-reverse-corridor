"""Tests for the green-phase scheduler."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.scheduler import Scheduler, SchedulerInputs, clamp


def make_settings(**overrides) -> Settings:
    base = dict(
        green_min_s=15,
        green_max_s=240,
        base_green_s=20,
        prio_w_queue=1.0,
        prio_w_wait=0.05,
        prio_w_other_empty=2.0,
    )
    base.update(overrides)
    # Settings reads from env; instantiate then override fields directly.
    s = Settings()
    for k, v in base.items():
        setattr(s, k, v)
    return s


def test_clamp_helper():
    assert clamp(5, 10, 20) == 10
    assert clamp(25, 10, 20) == 20
    assert clamp(15, 10, 20) == 15


def test_baseline_returns_constant():
    sched = Scheduler(make_settings(green_min_s=10, green_max_s=30))
    assert sched.baseline_green() == 20  # midpoint
    # baseline ignores inputs
    inp = SchedulerInputs(queue_side=999, wait_other=999, other_empty=False)
    assert sched.compute("baseline", inp) == 20


def test_adaptive_grows_with_queue():
    sched = Scheduler(make_settings())
    short = sched.adaptive_green(SchedulerInputs(queue_side=2, wait_other=0, other_empty=False))
    longer = sched.adaptive_green(SchedulerInputs(queue_side=20, wait_other=0, other_empty=False))
    assert longer > short


def test_adaptive_clamps_to_max():
    sched = Scheduler(make_settings(green_max_s=30, green_min_s=10, base_green_s=10))
    out = sched.adaptive_green(SchedulerInputs(queue_side=10_000, wait_other=10_000, other_empty=False))
    assert out == 30


def test_adaptive_clamps_to_min():
    sched = Scheduler(make_settings(green_min_s=15, prio_w_other_empty=999))
    # other_empty heavily punishes -> floor at min
    out = sched.adaptive_green(SchedulerInputs(queue_side=0, wait_other=0, other_empty=True))
    assert out == 15


def test_adaptive_other_empty_reduces_duration():
    sched = Scheduler(make_settings())
    full = sched.adaptive_green(SchedulerInputs(queue_side=5, wait_other=10, other_empty=False))
    empty = sched.adaptive_green(SchedulerInputs(queue_side=5, wait_other=10, other_empty=True))
    assert empty <= full


def test_pick_next_side_priority_and_alternation():
    assert Scheduler.pick_next_side(queue_a=5, queue_b=2, last_side=None) == "A"
    assert Scheduler.pick_next_side(queue_a=2, queue_b=5, last_side=None) == "B"
    # tie + last_side="A" -> alternate to B
    assert Scheduler.pick_next_side(queue_a=3, queue_b=3, last_side="A") == "B"
    assert Scheduler.pick_next_side(queue_a=3, queue_b=3, last_side="B") == "A"
    assert Scheduler.pick_next_side(queue_a=0, queue_b=0, last_side=None) == "A"


def test_scheduler_update_overrides_weights():
    sched = Scheduler(make_settings())
    sched.update(prio_w_queue=10.0, base_green_s=5)
    assert sched.settings.prio_w_queue == 10.0
    assert sched.settings.base_green_s == 5
