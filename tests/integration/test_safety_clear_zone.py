"""Safety: never switch GREEN while the work zone still has vehicles inside.

We leave one car "inside_A" (enter without exit) and try to nudge the
controller toward GREEN_B. The contract says it must stay in ALL_RED_AFTER_A
until the zone is empty (or eventually escalate to EMERGENCY_STOP after
CLEAR_TIMEOUT_S).
"""
from __future__ import annotations

import time

import httpx
import pytest

from .conftest import MqttBus, _CamPublisher

pytestmark = pytest.mark.integration


def test_no_switch_while_zone_not_empty(
    mqtt_client: MqttBus, cam: _CamPublisher, http: httpx.Client
) -> None:
    http.post(
        "/override",
        json={"action": "force_phase", "phase": "GREEN_A", "reason": "test", "by": "itest"},
    )
    mqtt_client.wait_for(
        lambda t, p: t == "corridor/state" and p.get("phase") == "GREEN_A",
        timeout=10.0,
    )

    # Send three IN events on A but only two OUT events: one car is still
    # inside the zone.
    for tid in (201, 202, 203):
        cam.event("A", "in", track_id=tid)
    time.sleep(0.2)
    for tid in (201, 202):
        cam.event("A", "out", track_id=tid)

    # Try to end the phase.
    http.post(
        "/override",
        json={"action": "end_phase", "reason": "test", "by": "itest"},
    )

    # Within a reasonable window we must NOT see GREEN_B and inside_A must stay > 0.
    deadline = time.monotonic() + 8.0
    saw_green_b = False
    last_inside_a: int | None = None
    while time.monotonic() < deadline:
        try:
            topic, payload = mqtt_client.wait_for(
                lambda t, p: t == "corridor/state",
                timeout=max(0.1, deadline - time.monotonic()),
            )
        except AssertionError:
            break
        if payload.get("phase") == "GREEN_B":
            saw_green_b = True
            break
        if "inside_A" in payload:
            last_inside_a = payload["inside_A"]

    assert not saw_green_b, "Controller switched to GREEN_B while zone was not empty"
    if last_inside_a is not None:
        assert last_inside_a >= 1, last_inside_a

    # Drain the zone; controller should now be allowed to progress.
    cam.event("A", "out", track_id=203)
    mqtt_client.wait_for(
        lambda t, p: t == "corridor/state" and p.get("phase") == "GREEN_B",
        timeout=20.0,
    )
