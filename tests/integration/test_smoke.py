"""Smoke tests for the full stack (requires running services).

Run with: pytest tests/integration/ -v --timeout=30
Skip if services not available.
"""
import json
import os
import time

import pytest

CONTROLLER_URL = os.environ.get("CONTROLLER_URL", "http://127.0.0.1:8000")
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))


def _controller_available() -> bool:
    try:
        import httpx
        r = httpx.get(f"{CONTROLLER_URL}/health", timeout=2.0)
        return r.status_code < 500
    except Exception:
        return False


def _mqtt_available() -> bool:
    try:
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smoke-test")
        c.connect(MQTT_HOST, MQTT_PORT, keepalive=5)
        c.disconnect()
        return True
    except Exception:
        return False


skip_no_stack = pytest.mark.skipif(
    not _controller_available() or not _mqtt_available(),
    reason="Stack not running (controller or MQTT unavailable)",
)


@skip_no_stack
class TestSmoke:
    def test_controller_health(self):
        import httpx
        r = httpx.get(f"{CONTROLLER_URL}/health", timeout=5.0)
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert data["status"] == "ok"

    def test_controller_state(self):
        import httpx
        r = httpx.get(f"{CONTROLLER_URL}/state", timeout=5.0)
        assert r.status_code == 200
        data = r.json()
        assert "phase" in data
        assert "mode" in data
        assert data["mode"] in ("baseline", "adaptive")

    def test_controller_metrics(self):
        import httpx
        r = httpx.get(f"{CONTROLLER_URL}/metrics", timeout=5.0)
        assert r.status_code == 200
        data = r.json()
        assert "throughput_5min" in data
        assert "avg_delay_5min" in data
        assert "queue" in data

    def test_mode_switch(self):
        import httpx
        with httpx.Client(base_url=CONTROLLER_URL, timeout=5.0) as c:
            # Switch to baseline
            r = c.post("/override", json={"action": "mode_switch", "mode": "baseline", "by": "test"})
            assert r.status_code == 200
            assert r.json().get("ok") is True

            # Verify
            r = c.get("/state")
            assert r.json()["mode"] == "baseline"

            # Switch back to adaptive
            r = c.post("/override", json={"action": "mode_switch", "mode": "adaptive", "by": "test"})
            assert r.status_code == 200

    def test_cam_event_updates_state(self):
        import httpx
        import paho.mqtt.client as mqtt

        # Get initial state
        with httpx.Client(base_url=CONTROLLER_URL, timeout=5.0) as c:
            initial = c.get("/state").json()
            initial_inside_a = initial.get("inside_A", 0)

        # Publish a cam event
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smoke-cam")
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
        client.loop_start()
        event = {
            "ts": time.time(),
            "track_id": 9999,
            "class": "car",
            "side": "A",
            "dir": "in",
            "confidence": 0.95,
            "plate": None,
        }
        info = client.publish("corridor/cam/A/in/event", json.dumps(event), qos=1)
        info.wait_for_publish(timeout=2)
        time.sleep(2)  # Wait for controller to process

        # Check state updated
        with httpx.Client(base_url=CONTROLLER_URL, timeout=5.0) as c:
            updated = c.get("/state").json()
            assert updated.get("inside_A", 0) >= initial_inside_a

        # Cleanup: publish out event
        event_out = {**event, "dir": "out"}
        info = client.publish("corridor/cam/A/out/event", json.dumps(event_out), qos=1)
        info.wait_for_publish(timeout=2)
        client.loop_stop()
        client.disconnect()
