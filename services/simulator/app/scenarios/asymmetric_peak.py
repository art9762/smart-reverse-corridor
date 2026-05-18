"""Asymmetric peak — A is rush-hour, B is light traffic."""
from __future__ import annotations

from ..spawner import SideSpawnConfig, SpawnerConfig
from . import Scenario


def build(seed: int | None = None) -> Scenario:
    spawner = SpawnerConfig(
        side_a=SideSpawnConfig(lambda_per_s=0.55, truck_share=0.05),
        side_b=SideSpawnConfig(lambda_per_s=0.10, truck_share=0.05),
        rng_seed=seed,
    )
    return Scenario(
        name="asymmetric_peak",
        title="Asymmetric peak hour",
        description=(
            "Side A under heavy load (~33 veh/min), side B light (~6 veh/min). "
            "Highlights how the adaptive controller skews phase length."
        ),
        spawner=spawner,
    )
