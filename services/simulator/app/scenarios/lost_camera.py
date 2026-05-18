"""Lost-camera — mid-run we silence one camera for 30s."""
from __future__ import annotations

from ..spawner import SideSpawnConfig, SpawnerConfig
from . import Scenario, ScheduledEvent


def build(seed: int | None = None) -> Scenario:
    spawner = SpawnerConfig(
        side_a=SideSpawnConfig(lambda_per_s=0.20),
        side_b=SideSpawnConfig(lambda_per_s=0.20),
        rng_seed=seed,
    )
    events = [
        ScheduledEvent(at=90.0, kind="camera_lost", payload={"camera": "B_in", "duration": 30.0}),
        ScheduledEvent(at=120.0, kind="camera_restored", payload={"camera": "B_in"}),
    ]
    return Scenario(
        name="lost_camera",
        title="Lost camera (B_in down for 30s)",
        description=(
            "Symmetric flow. At t=90s camera B_in stops emitting heartbeats "
            "and events; restored at t=120s. Validates controller's safe "
            "fallback behaviour."
        ),
        spawner=spawner,
        events=events,
    )
