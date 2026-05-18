"""Truck-jam — extra-long vehicle bursts that need long green windows."""
from __future__ import annotations

from ..spawner import SideSpawnConfig, SpawnerConfig
from ..world import Side, VehicleType
from . import Scenario


def build(seed: int | None = None) -> Scenario:
    spawner = SpawnerConfig(
        side_a=SideSpawnConfig(
            lambda_per_s=0.25, truck_share=0.45, bus_share=0.10, moto_share=0.02
        ),
        side_b=SideSpawnConfig(
            lambda_per_s=0.25, truck_share=0.45, bus_share=0.10, moto_share=0.02
        ),
        rng_seed=seed,
    )
    # Inject a burst of trucks 60s in to make the jam unmistakable.
    scripted = []
    for i, t in enumerate((60.0, 65.0, 70.0, 75.0)):
        side = Side.A if i % 2 == 0 else Side.B
        scripted.append((t, side, VehicleType.TRUCK))
    return Scenario(
        name="truck_jam",
        title="Truck jam",
        description=(
            "High share of trucks (45%) with a scripted burst between t=60s "
            "and t=75s. Long vehicles cannot clear the zone in a 3-minute "
            "fixed phase."
        ),
        spawner=spawner,
        scripted_spawns=scripted,
    )
