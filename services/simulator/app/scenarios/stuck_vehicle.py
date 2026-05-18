"""Stuck-vehicle — one vehicle freezes inside the zone for 60s."""
from __future__ import annotations

from ..spawner import SideSpawnConfig, SpawnerConfig
from . import Scenario, ScheduledEvent


def build(seed: int | None = None) -> Scenario:
    spawner = SpawnerConfig(
        side_a=SideSpawnConfig(lambda_per_s=0.22),
        side_b=SideSpawnConfig(lambda_per_s=0.22),
        rng_seed=seed,
    )
    # Pick the next car that crosses A_in after t=80s and freeze it.
    events = [
        ScheduledEvent(
            at=80.0,
            kind="stick_next_inside",
            payload={"side": "A", "duration": 60.0},
        )
    ]
    return Scenario(
        name="stuck_vehicle",
        title="Stuck vehicle inside the zone",
        description=(
            "Symmetric flow. After t=80s the next vehicle that enters from "
            "side A freezes for 60s, simulating a breakdown inside the zone. "
            "Controller must trigger a STUCK_VEHICLE alert."
        ),
        spawner=spawner,
        events=events,
    )
