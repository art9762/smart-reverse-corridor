"""Headless tests for the camera bus (matches `docs/MQTT.md` schema)."""
from __future__ import annotations

from app.cameras import ALL_CAMERAS, CameraBus, camera_id
from app.world import Side, VehicleType, World, kmh_to_ms


class _RecordBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict, int, bool]] = []

    def __call__(self, topic: str, payload: dict, qos: int, retain: bool) -> None:
        self.published.append((topic, payload, qos, retain))


def _world_with_car_at_a_in() -> tuple[World, list]:
    world = World(approach_m=200.0, zone_m=800.0)
    v = world.spawn(Side.A, VehicleType.CAR, 4.5, kmh_to_ms(60), now=0.0)
    v.position_m = world.camera_x_a + 0.5  # already past the line.
    crossings = world.detect_crossings()
    return world, crossings


def test_event_topic_and_schema() -> None:
    bus = _RecordBus()
    cam = CameraBus(publish=bus)
    _, crossings = _world_with_car_at_a_in()
    sent = cam.emit_events(crossings, now=10.0)
    assert sent == 1
    topic, payload, qos, retain = bus.published[0]
    assert topic == "corridor/cam/A/in/event"
    assert qos == 1 and retain is False
    # MQTT contract fields:
    expected_keys = {"ts", "track_id", "class", "side", "dir", "confidence", "plate"}
    assert set(payload.keys()) == expected_keys
    assert payload["side"] == "A"
    assert payload["dir"] == "in"
    assert payload["class"] == "car"
    assert payload["plate"] is None


def test_heartbeat_schema_and_rate_limit() -> None:
    bus = _RecordBus()
    cam = CameraBus(publish=bus)
    sent = cam.emit_heartbeats(now=0.0)
    assert sent == len(ALL_CAMERAS)
    # Within 1 second of the previous emission we should send nothing.
    assert cam.emit_heartbeats(now=0.5) == 0
    assert cam.emit_heartbeats(now=1.05) == len(ALL_CAMERAS)
    topic, payload, qos, retain = bus.published[0]
    assert topic.startswith("corridor/cam/") and topic.endswith("/heartbeat")
    assert retain is True and qos == 1
    expected_keys = {"ts", "camera_id", "fps", "healthy"}
    assert set(payload.keys()) == expected_keys
    assert payload["healthy"] is True


def test_lost_camera_blocks_events_and_marks_unhealthy() -> None:
    bus = _RecordBus()
    cam = CameraBus(publish=bus)
    cam.set_lost("A_in", until=100.0)
    _, crossings = _world_with_car_at_a_in()
    sent = cam.emit_events(crossings, now=50.0)
    assert sent == 0
    # Heartbeats keep flowing but mark A_in unhealthy.
    cam.emit_heartbeats(now=50.0)
    a_in_payloads = [p for t, p, _, _ in bus.published if "A/in/heartbeat" in t]
    assert a_in_payloads
    assert a_in_payloads[-1]["healthy"] is False
    # After expiry, A_in heals automatically.
    assert cam.is_healthy("A_in", now=101.0) is True


def test_camera_id_helper() -> None:
    assert camera_id(Side.A, "in") == "A_in"
    assert camera_id(Side.B, "out") == "B_out"
