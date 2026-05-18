"""Symmetric flow — equal moderate λ on both sides, classic baseline test."""
from __future__ import annotations

from ..spawner import SideSpawnConfig, SpawnerConfig
from . import Scenario


def build(seed: int | None = None) -> Scenario:
    spawner = SpawnerConfig(
        side_a=SideSpawnConfig(
            lambda_per_s=0.20, truck_share=0.08, bus_share=0.04, moto_share=0.04
        ),
        side_b=SideSpawnConfig(
            lambda_per_s=0.20, truck_share=0.08, bus_share=0.04, moto_share=0.04
        ),
        rng_seed=seed,
    )
    return Scenario(
        name="symmetric",
        title="Symmetric balanced flow",
        description=(
            "Equal Poisson arrivals on both sides (~12 veh/min each). "
            "Used as the baseline reference run."
        ),
        spawner=spawner,
    )
