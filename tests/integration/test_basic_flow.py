"""Happy path: A -> YELLOW_A -> ALL_RED_AFTER_A -> GREEN_B.

We drive the controller via fake camera events on `corridor/cam/<side>/<dir>/event`
and assert the FSM transitions visible on `corridor/state`.
"""
from __future__ import annotations

import time

import httpx
import pytest

from .conftest import MqttBus, _CamPublisher

pytestmark = pytest.mark.integration


def _phase(payload: dict) -> str | None:
    return payload.get("phase")


def test_phase_progresses_a_to_b(
    mqtt_client: MqttBus, cam: _CamPublisher, http: httpx.Client
) -> None:
    # Force GREEN_A as a known starting point.
    r = http.post(
        "/override",
        json={"action": "force_phase", "phase": "GREEN_A", "reason": "test-init", "by": "itest"},
    )
    assert r.status_code in (200, 202), r.text

    # Wait until /corridor/state shows GREEN_A.
    mqtt_client.wait_for(
        lambda t, p: t == "corridor/state" and _phase(p) == "GREEN_A",
        timeout=10.0,
    )

    # Drive a balanced flow on side A so the zone is genuinely empty.
    for tid in (101, 102, 103):
        cam.event("A", "in", track_id=tid)
    time.sleep(0.2)
    for tid in (101, 102, 103):
        cam.event("A", "out", track_id=tid)

    # Ask the planner to end GREEN_A early. Implementations differ; we accept
    # either an explicit /override end_phase or just letting the planner do it
    # if the queue is zero. We send a polite hint and then wait.
    http.post(
        "/override",
        json={"action": "end_phase", "reason": "test-progress", "by": "itest"},
    )

    seen_phases: list[str] = []

    def _record(topic: str, payload: dict) -> bool:
        if topic != "corridor/state":
            return False
        ph = _phase(payload)
        if ph and (not seen_phases or seen_phases[-1] != ph):
            seen_phases.append(ph)
        return ph == "GREEN_B"

    mqtt_client.wait_for(_record, timeout=30.0)

    # Contract: from GREEN_A we must pass through YELLOW_A and an ALL_RED
    # state before GREEN_B.
    assert "GREEN_A" in seen_phases, seen_phases
    assert "YELLOW_A" in seen_phases, seen_phases
    assert any(p.startswith("ALL_RED") for p in seen_phases), seen_phases
    assert seen_phases[-1] == "GREEN_B", seen_phases

    # Order: GREEN_A < YELLOW_A < ALL_RED_* < GREEN_B.
    idx_g_a = seen_phases.index("GREEN_A")
    idx_y_a = seen_phases.index("YELLOW_A")
    idx_red = next(i for i, p in enumerate(seen_phases) if p.startswith("ALL_RED"))
    idx_g_b = seen_phases.index("GREEN_B")
    assert idx_g_a < idx_y_a < idx_red < idx_g_b, seen_phases
