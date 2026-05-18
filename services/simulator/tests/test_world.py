"""Headless tests for the World model (no pygame, no MQTT)."""
from __future__ import annotations

from app.world import Phase, Side, VehicleType, World, kmh_to_ms


def _make_world() -> World:
    return World(approach_m=200.0, zone_m=800.0)


def test_kmh_to_ms_conversion() -> None:
    assert kmh_to_ms(36) == 10.0
    assert round(kmh_to_ms(60), 4) == 16.6667


def test_spawn_appends_to_correct_queue() -> None:
    world = _make_world()
    world.spawn(Side.A, VehicleType.CAR, 4.5, kmh_to_ms(60), now=0.0)
    world.spawn(Side.B, VehicleType.TRUCK, 12.0, kmh_to_ms(40), now=0.0)
    assert len(world.queue_a) == 1
    assert len(world.queue_b) == 1
    assert world.queue_a[0].type is VehicleType.CAR
    assert world.queue_b[0].type is VehicleType.TRUCK


def test_step_advances_lead_car_when_green() -> None:
    world = _make_world()
    v = world.spawn(Side.A, VehicleType.CAR, 4.5, kmh_to_ms(60), now=0.0)
    initial = v.position_m
    # Run a few seconds with GREEN_A.
    for _ in range(60):
        world.step(0.1, Phase.GREEN_A, world.now + 0.1)
    assert v.position_m > initial


def test_lead_car_holds_when_red() -> None:
    world = _make_world()
    v = world.spawn(Side.A, VehicleType.CAR, 4.5, kmh_to_ms(60), now=0.0)
    initial = v.position_m
    for _ in range(60):
        world.step(0.1, Phase.GREEN_B, world.now + 0.1)
    # No advancement: car should be roughly where it started.
    assert abs(v.position_m - initial) < 0.5


def test_detect_crossings_in_event_for_side_a() -> None:
    world = _make_world()
    v = world.spawn(Side.A, VehicleType.CAR, 4.5, kmh_to_ms(60), now=0.0)
    # Force the vehicle's front past the camera_x_a line.
    v.position_m = world.camera_x_a + 1.0
    crossings = world.detect_crossings()
    assert ((v, Side.A, "in")) in crossings
    # Replaying the same step does not produce duplicates.
    assert world.detect_crossings() == []


def test_detect_crossings_out_event_for_side_b() -> None:
    world = _make_world()
    v = world.spawn(Side.B, VehicleType.CAR, 4.5, kmh_to_ms(60), now=0.0)
    # Walk B-side car all the way through the zone.
    v.position_m = world.camera_x_b - 1.0
    world.detect_crossings()  # B_in
    v.position_m = world.camera_x_a - 1.0
    crossings = world.detect_crossings()
    out_events = [c for c in crossings if c[2] == "out"]
    assert len(out_events) == 1
    assert out_events[0][1] is Side.A


def test_finished_vehicles_leave_the_world() -> None:
    world = _make_world()
    v = world.spawn(Side.A, VehicleType.CAR, 4.5, kmh_to_ms(60), now=0.0)
    v.position_m = world.total_m + 1.0
    world.detect_crossings()
    world._reap_finished()
    assert v not in world.vehicles
    assert v in world.finished
    assert v.finished is True
