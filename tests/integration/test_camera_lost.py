"""Camera watchdog: missing heartbeat -> alert + fallback.

The contract:
- Heartbeat is published every ~1s with retain=true.
- If a camera goes silent for > 5s, the controller should emit an alert with
  code=CAMERA_LOST and update `camera_health` in `corridor/state`.
- If only one camera on a side is lost, the controller falls back to the
  paired one (no EMERGENCY_STOP). If both on a side are lost, it should
  RED_BOTH.
"""
from __future__ import annotations

import time

import httpx
import pytest

from .conftest import MqttBus, _CamPublisher

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_single_camera_lost_alert_and_health(
    mqtt_client: MqttBus, cam: _CamPublisher, http: httpx.Client
) -> None:
    # Confirm starting health.
    cam.heartbeat_all(healthy=True)
    mqtt_client.wait_for(
        lambda t, p: t == "corridor/state"
        and p.get("camera_health", {}).get("B_out") is True,
        timeout=10.0,
    )

    # Stop heartbeating B_out and keep beating the others.
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        for side, direction in [("A", "in"), ("A", "out"), ("B", "in")]:
            cam.heartbeat(side, direction, healthy=True)
        time.sleep(0.5)

    # Expect an alert with code CAMERA_LOST.
    mqtt_client.wait_for(
        lambda t, p: t == "corridor/alerts" and p.get("code") == "CAMERA_LOST",
        timeout=10.0,
    )

    # Expect camera_health to reflect the loss.
    mqtt_client.wait_for(
        lambda t, p: t == "corridor/state"
        and p.get("camera_health", {}).get("B_out") is False,
        timeout=10.0,
    )

    # Side B is degraded but not dead: controller should still be running
    # (not EMERGENCY_STOP) because A's pair is healthy.
    state = http.get("/state").json()
    assert state.get("phase") != "EMERGENCY_STOP", state
