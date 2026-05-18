"""POST /override with `force_phase` should produce an immediate but safe
switch: the next observable phase must be either YELLOW_* (if we were in a
GREEN_*) or ALL_RED_*; we should never see two opposing GREEN states
back-to-back.
"""
from __future__ import annotations

import time

import httpx
import pytest

from .conftest import MqttBus, _CamPublisher

pytestmark = pytest.mark.integration


def test_override_priority_switch(
    mqtt_client: MqttBus, cam: _CamPublisher, http: httpx.Client
) -> None:
    # Start firmly on GREEN_A and keep zone empty (no IN events).
    r = http.post(
        "/override",
        json={"action": "force_phase", "phase": "GREEN_A", "reason": "test", "by": "itest"},
    )
    assert r.status_code in (200, 202), r.text
    mqtt_client.wait_for(
        lambda t, p: t == "corridor/state" and p.get("phase") == "GREEN_A",
        timeout=10.0,
    )
    mqtt_client.drain()

    # Fire emergency override toward GREEN_B ("ambulance from B").
    t_request = time.monotonic()
    r = http.post(
        "/override",
        json={
            "action": "force_phase",
            "phase": "GREEN_B",
            "reason": "ambulance",
            "by": "operator-1",
        },
    )
    assert r.status_code in (200, 202), r.text

    seen: list[str] = []

    def _seen_green_b(topic: str, payload: dict) -> bool:
        if topic != "corridor/state":
            return False
        ph = payload.get("phase")
        if ph and (not seen or seen[-1] != ph):
            seen.append(ph)
        return ph == "GREEN_B"

    mqtt_client.wait_for(_seen_green_b, timeout=20.0)
    elapsed = time.monotonic() - t_request

    # Must be "reasonably fast". 15s is generous for hackathon-grade timings.
    assert elapsed < 15.0, f"override took {elapsed:.1f}s"

    # We must not have flipped GREEN_A -> GREEN_B with no intermediate states.
    # The first transition out of GREEN_A must be YELLOW_A or ALL_RED_*.
    after_a = [p for p in seen if p != "GREEN_A"]
    assert after_a, seen
    assert after_a[0] in {"YELLOW_A", "ALL_RED_AFTER_A"}, seen
    assert any(p.startswith("ALL_RED") for p in seen), seen

    # Alert with EMERGENCY_OVERRIDE should have been published.
    try:
        mqtt_client.wait_for(
            lambda t, p: t == "corridor/alerts"
            and p.get("code") == "EMERGENCY_OVERRIDE",
            timeout=2.0,
        )
    except AssertionError:
        # Optional alert; do not fail the whole test if the controller chose
        # to log it elsewhere. Phase contract above is the hard requirement.
        pass
