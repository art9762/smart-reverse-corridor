"""Headless tests for the world snapshot publisher.

No broker, no display: we use the in-process ``_NoopBus`` to capture
published messages and assert against the contract from ``docs/MQTT.md``.
"""
from __future__ import annotations

import pytest

from app.mqtt_bus import _NoopBus
from app.world import Phase, Side, VehicleType, World, kmh_to_ms
from app.world_publisher import TOPIC, WorldPublisher


ZONE_M = 800.0
APPROACH_M = 200.0


def _world_with_two_in_zone() -> World:
    """Build a world with one A-car and one B-truck already inside the zone."""
    world = World(approach_m=APPROACH_M, zone_m=ZONE_M)
    a = world.spawn(Side.A, VehicleType.CAR, 4.5, kmh_to_ms(60), now=0.0)
    b = world.spawn(Side.B, VehicleType.TRUCK, 12.0, kmh_to_ms(40), now=0.0)
    # Move them into the zone manually (skip spawner/queue dynamics).
    a.position_m = world.camera_x_a + ZONE_M * 0.25
    a.in_zone = True
    a.speed_ms = kmh_to_ms(60)
    if a in world.queue_a:
        world.queue_a.remove(a)
    world.inside_a.append(a)
    b.position_m = world.camera_x_a + ZONE_M * 0.75
    b.in_zone = True
    b.speed_ms = kmh_to_ms(40)
    if b in world.queue_b:
        world.queue_b.remove(b)
    world.inside_b.append(b)
    return world


def test_topic_qos_retain_match_contract() -> None:
    bus = _NoopBus()
    pub = WorldPublisher(publish=bus.publish, hz=15.0)
    world = _world_with_two_in_zone()
    assert pub.maybe_emit(world, Phase.GREEN_A, now=1.0) is True
    assert len(bus.published) == 1
    topic, payload, qos, retain = bus.published[0]
    assert topic == TOPIC == "corridor/sim/world"
    assert qos == 0
    assert retain is False
    assert isinstance(payload, dict)


def test_snapshot_schema_and_normalized_x() -> None:
    bus = _NoopBus()
    pub = WorldPublisher(publish=bus.publish, hz=15.0)
    world = _world_with_two_in_zone()
    pub.maybe_emit(world, Phase.GREEN_A, now=1.5)
    _, payload, _, _ = bus.published[-1]

    assert set(payload.keys()) == {
        "ts",
        "zone_length_m",
        "phase",
        "vehicles",
        "queues",
    }
    assert payload["ts"] == 1.5
    assert payload["zone_length_m"] == ZONE_M
    assert payload["phase"] == "GREEN_A"
    # Both vehicles are inside the zone, neither is in a queue.
    assert payload["queues"] == {"A": 0, "B": 0}

    assert len(payload["vehicles"]) == 2
    expected_keys = {
        "id",
        "side",
        "type",
        "x",
        "y",
        "speed",
        "len_m",
        "emergency",
    }
    for v in payload["vehicles"]:
        assert set(v.keys()) == expected_keys

    by_side = {v["side"]: v for v in payload["vehicles"]}
    assert by_side["A"]["type"] == "car"
    assert by_side["B"]["type"] == "truck"
    # x normalized to zone length: A car at zone_m * 0.25 → x ≈ 0.25.
    assert by_side["A"]["x"] == pytest.approx(0.25, abs=1e-3)
    assert by_side["B"]["x"] == pytest.approx(0.75, abs=1e-3)
    assert by_side["A"]["len_m"] == 4.5
    assert by_side["B"]["len_m"] == 12.0
    assert by_side["A"]["emergency"] is False
    assert by_side["B"]["emergency"] is False
    assert by_side["A"]["y"] == 0.0


def test_rate_limit_respects_period() -> None:
    bus = _NoopBus()
    pub = WorldPublisher(publish=bus.publish, hz=15.0)
    world = _world_with_two_in_zone()
    # First emit always goes out.
    assert pub.maybe_emit(world, Phase.GREEN_A, now=0.0) is True
    # 1/15 ≈ 0.0667s — still rate-limited.
    assert pub.maybe_emit(world, Phase.GREEN_A, now=0.04) is False
    assert pub.maybe_emit(world, Phase.GREEN_A, now=0.07) is True
    assert len(bus.published) == 2


def test_queues_counted_for_waiting_vehicles() -> None:
    bus = _NoopBus()
    pub = WorldPublisher(publish=bus.publish, hz=15.0)
    world = World(approach_m=APPROACH_M, zone_m=ZONE_M)
    world.spawn(Side.A, VehicleType.CAR, 4.5, kmh_to_ms(60), now=0.0)
    world.spawn(Side.A, VehicleType.CAR, 4.5, kmh_to_ms(60), now=0.0)
    world.spawn(Side.B, VehicleType.TRUCK, 12.0, kmh_to_ms(40), now=0.0)
    pub.maybe_emit(world, Phase.ALL_RED, now=0.5)
    _, payload, _, _ = bus.published[-1]
    assert payload["queues"] == {"A": 2, "B": 1}
    assert payload["phase"] == "ALL_RED"
    # All three vehicles still appear in the snapshot (queues are not
    # filtered out — the dashboard renders them outside the zone).
    assert len(payload["vehicles"]) == 3


def test_emergency_flag_propagates() -> None:
    bus = _NoopBus()
    pub = WorldPublisher(publish=bus.publish, hz=15.0)
    world = World(approach_m=APPROACH_M, zone_m=ZONE_M)
    e = world.spawn(Side.B, VehicleType.EMERGENCY, 5.5, kmh_to_ms(80), now=0.0)
    e.position_m = world.camera_x_a + ZONE_M * 0.5
    e.in_zone = True
    if e in world.queue_b:
        world.queue_b.remove(e)
    world.inside_b.append(e)
    pub.maybe_emit(world, Phase.GREEN_B, now=0.0)
    _, payload, _, _ = bus.published[-1]
    assert len(payload["vehicles"]) == 1
    v = payload["vehicles"][0]
    assert v["type"] == "emergency"
    assert v["emergency"] is True


def test_invalid_hz_rejected() -> None:
    with pytest.raises(ValueError):
        WorldPublisher(publish=_NoopBus().publish, hz=0)
    with pytest.raises(ValueError):
        WorldPublisher(publish=_NoopBus().publish, hz=-5)
