"""Showcase — a narrative demo scenario for hackathon presentation.

Timeline (4 minutes total):
  0-60s:   Moderate symmetric traffic — system runs smoothly
  60-120s: Asymmetric peak from A — adaptive gives more green to A
  120-150s: Truck convoy from B — heavier vehicles, adjusted timing
  150-180s: AMBULANCE from A — instant priority, dramatic switch
  180-240s: Return to normal — metrics settle, comparison visible
"""
from __future__ import annotations

from ..spawner import SideSpawnConfig, SpawnerConfig
from ..world import Side, VehicleType
from . import Scenario, ScheduledEvent


def build(seed: int | None = None) -> Scenario:
    # Moderate base traffic — visually interesting but not overwhelming.
    # The spawner uses these rates for the whole run; scripted spawns add
    # drama on top.
    spawner = SpawnerConfig(
        side_a=SideSpawnConfig(lambda_per_s=0.30, truck_share=0.08, bus_share=0.05),
        side_b=SideSpawnConfig(lambda_per_s=0.20, truck_share=0.10, bus_share=0.05),
        rng_seed=seed,
    )

    # Scripted spawns for narrative beats:
    scripted = [
        # Phase 2: extra cars from A (rush hour burst at 65-100s)
        (65.0, Side.A, VehicleType.CAR),
        (68.0, Side.A, VehicleType.CAR),
        (72.0, Side.A, VehicleType.CAR),
        (76.0, Side.A, VehicleType.TRUCK),
        (80.0, Side.A, VehicleType.CAR),
        (84.0, Side.A, VehicleType.CAR),
        (88.0, Side.A, VehicleType.CAR),
        (92.0, Side.A, VehicleType.BUS),
        (96.0, Side.A, VehicleType.CAR),
        (100.0, Side.A, VehicleType.CAR),
        # Phase 3: truck convoy from B (125-145s)
        (125.0, Side.B, VehicleType.TRUCK),
        (128.0, Side.B, VehicleType.TRUCK),
        (132.0, Side.B, VehicleType.TRUCK),
        (136.0, Side.B, VehicleType.BUS),
        (140.0, Side.B, VehicleType.TRUCK),
        (145.0, Side.B, VehicleType.TRUCK),
        # Phase 4: AMBULANCE from A (dramatic!)
        (155.0, Side.A, VehicleType.EMERGENCY),
    ]

    return Scenario(
        name="showcase",
        title="Hackathon showcase demo",
        description=(
            "A 4-minute narrative scenario: symmetric warmup → rush hour "
            "from A → truck convoy from B → ambulance priority → calm return. "
            "Designed to show off all system capabilities in one run."
        ),
        spawner=spawner,
        scripted_spawns=scripted,
    )
