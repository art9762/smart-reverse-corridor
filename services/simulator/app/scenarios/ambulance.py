"""Ambulance — single emergency vehicle scripted into a normal flow."""
from __future__ import annotations

from ..spawner import SideSpawnConfig, SpawnerConfig
from ..world import Side, VehicleType
from . import Scenario


def build(seed: int | None = None) -> Scenario:
    spawner = SpawnerConfig(
        side_a=SideSpawnConfig(lambda_per_s=0.25),
        side_b=SideSpawnConfig(lambda_per_s=0.25),
        rng_seed=seed,
    )
    scripted = [(120.0, Side.B, VehicleType.EMERGENCY)]
    return Scenario(
        name="ambulance",
        title="Emergency vehicle priority",
        description=(
            "Symmetric flow with a scripted ambulance arriving on side B at "
            "t=120s. The controller should pre-empt and grant immediate "
            "GREEN_B."
        ),
        spawner=spawner,
        scripted_spawns=scripted,
    )
