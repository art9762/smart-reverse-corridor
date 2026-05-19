"""Scenario presets for the simulator.

A scenario is a small dataclass that wires together:

* baseline `SpawnerConfig` (per-side λ and vehicle mix)
* a list of scripted spawns (e.g. an ambulance at t=120)
* a list of scheduled events (camera failures, stuck vehicles, …)

Scenarios stay declarative; the runtime in `app/main.py` interprets them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..spawner import SideSpawnConfig, SpawnerConfig
from ..world import Side, VehicleType


# A scheduled side-effect to apply at simulation time `at`.
# Kind is opaque to the runtime; main.py knows how to dispatch the known ones.
@dataclass
class ScheduledEvent:
    at: float
    kind: str
    payload: dict = field(default_factory=dict)


@dataclass
class Scenario:
    """Static description of a simulator scenario."""

    name: str
    title: str
    description: str
    spawner: SpawnerConfig
    scripted_spawns: list[tuple[float, Side, VehicleType]] = field(default_factory=list)
    events: list[ScheduledEvent] = field(default_factory=list)


from .symmetric import build as build_symmetric  # noqa: E402
from .asymmetric_peak import build as build_asymmetric_peak  # noqa: E402
from .truck_jam import build as build_truck_jam  # noqa: E402
from .ambulance import build as build_ambulance  # noqa: E402
from .lost_camera import build as build_lost_camera  # noqa: E402
from .stuck_vehicle import build as build_stuck_vehicle  # noqa: E402
from .showcase import build as build_showcase  # noqa: E402


SCENARIOS: dict[str, Callable[[int | None], Scenario]] = {
    "symmetric": build_symmetric,
    "asymmetric": build_asymmetric_peak,
    "asymmetric_peak": build_asymmetric_peak,
    "truck": build_truck_jam,
    "truck_jam": build_truck_jam,
    "ambulance": build_ambulance,
    "lost-camera": build_lost_camera,
    "lost_camera": build_lost_camera,
    "stuck": build_stuck_vehicle,
    "stuck_vehicle": build_stuck_vehicle,
    "showcase": build_showcase,
}


def get_scenario(name: str, seed: int | None = None) -> Scenario:
    if name not in SCENARIOS:
        raise KeyError(
            f"unknown scenario '{name}'. Known: {sorted(set(SCENARIOS))}"
        )
    return SCENARIOS[name](seed)


__all__ = ["Scenario", "ScheduledEvent", "SCENARIOS", "get_scenario"]
