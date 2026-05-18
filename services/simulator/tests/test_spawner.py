"""Headless tests for the Spawner (Poisson + scripted)."""
from __future__ import annotations

import random

from app.config import SimulatorSettings
from app.spawner import SideSpawnConfig, Spawner, SpawnerConfig
from app.world import Side, VehicleType, World


def _world() -> World:
    return World(approach_m=200.0, zone_m=800.0)


def test_zero_lambda_never_spawns() -> None:
    world = _world()
    cfg = SpawnerConfig(
        side_a=SideSpawnConfig(lambda_per_s=0.0),
        side_b=SideSpawnConfig(lambda_per_s=0.0),
        rng_seed=1,
    )
    spawner = Spawner(world, cfg, settings=SimulatorSettings())
    for t in range(0, 600, 1):
        spawner.tick(float(t))
    assert world.queue_lengths() == (0, 0)


def test_poisson_mean_within_tolerance() -> None:
    world = _world()
    cfg = SpawnerConfig(
        side_a=SideSpawnConfig(lambda_per_s=1.0),
        side_b=SideSpawnConfig(lambda_per_s=0.0),
        rng_seed=42,
    )
    spawner = Spawner(world, cfg, settings=SimulatorSettings())
    horizon = 600.0  # 10 minutes of "sim" time, sampled finely.
    t = 0.0
    while t <= horizon:
        spawner.tick(t)
        t += 0.1
    qa, qb = world.queue_lengths()
    # λ=1/s over 600s => ~600 ± a few sigmas; we allow generous bounds.
    assert qb == 0
    assert 500 <= qa <= 700, f"unexpected count: {qa}"


def test_scripted_spawn_fires_at_scheduled_time() -> None:
    world = _world()
    cfg = SpawnerConfig(
        side_a=SideSpawnConfig(lambda_per_s=0.0),
        side_b=SideSpawnConfig(lambda_per_s=0.0),
        rng_seed=1,
    )
    spawner = Spawner(world, cfg, settings=SimulatorSettings())
    spawner.script(at=120.0, side=Side.B, type_=VehicleType.EMERGENCY)
    spawner.tick(now=119.9)
    assert world.queue_lengths() == (0, 0)
    spawner.tick(now=120.1)
    assert world.queue_lengths() == (0, 1)
    assert world.queue_b[0].is_emergency


def test_truck_share_respected_in_aggregate() -> None:
    world = _world()
    cfg = SpawnerConfig(
        side_a=SideSpawnConfig(lambda_per_s=2.0, truck_share=0.5, bus_share=0.0, moto_share=0.0),
        side_b=SideSpawnConfig(lambda_per_s=0.0),
        rng_seed=7,
    )
    spawner = Spawner(world, cfg, settings=SimulatorSettings())
    t = 0.0
    while t <= 200.0:
        spawner.tick(t)
        t += 0.1
    types = [v.type for v in world.queue_a]
    truck_share = sum(1 for x in types if x is VehicleType.TRUCK) / max(len(types), 1)
    assert 0.35 <= truck_share <= 0.65
