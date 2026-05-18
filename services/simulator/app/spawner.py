"""Poisson-driven vehicle spawner.

The spawner does not know about pygame, MQTT, or the controller — it only
mutates a `World` instance. Different scenarios just plug different `λ`
values and a per-spawn type-mix function.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable

from .config import SimulatorSettings, get_settings
from .world import Side, Vehicle, VehicleType, World, kmh_to_ms


@dataclass
class SideSpawnConfig:
    """Spawn parameters for a single side."""

    lambda_per_s: float  # mean arrivals per second (Poisson rate).
    truck_share: float = 0.10
    bus_share: float = 0.05
    moto_share: float = 0.05
    emergency_share: float = 0.0  # raised by ambulance scenario.


@dataclass
class SpawnerConfig:
    side_a: SideSpawnConfig
    side_b: SideSpawnConfig
    rng_seed: int | None = None


class Spawner:
    """Poisson-process vehicle generator.

    For each side we sample inter-arrival times from `Exp(λ)` and emit a
    vehicle once `now >= next_arrival`. Type is sampled from a categorical
    distribution defined by the per-side shares.
    """

    def __init__(
        self,
        world: World,
        config: SpawnerConfig,
        settings: SimulatorSettings | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.world = world
        self.config = config
        self.settings = settings or get_settings()
        self.rng = rng or random.Random(config.rng_seed)
        self._next_at: dict[Side, float] = {
            Side.A: self._draw_next(0.0, config.side_a.lambda_per_s),
            Side.B: self._draw_next(0.0, config.side_b.lambda_per_s),
        }
        # Overrides used by scenarios (e.g. inject an ambulance at t=120).
        self._scripted: list[tuple[float, Side, VehicleType]] = []

    # ------------------------------------------------------------------ misc
    def script(self, at: float, side: Side, type_: VehicleType) -> None:
        """Inject a deterministic spawn (used by ambulance/truck scenarios)."""
        self._scripted.append((at, side, type_))
        self._scripted.sort(key=lambda x: x[0])

    def _draw_next(self, now: float, lam: float) -> float:
        if lam <= 0:
            return math.inf
        # Exponential inter-arrival.
        u = max(self.rng.random(), 1e-9)
        return now + -math.log(u) / lam

    def _pick_type(self, cfg: SideSpawnConfig) -> VehicleType:
        roll = self.rng.random()
        thresholds = [
            (cfg.emergency_share, VehicleType.EMERGENCY),
            (cfg.truck_share, VehicleType.TRUCK),
            (cfg.bus_share, VehicleType.BUS),
            (cfg.moto_share, VehicleType.MOTORCYCLE),
        ]
        acc = 0.0
        for share, t in thresholds:
            acc += share
            if roll < acc:
                return t
        return VehicleType.CAR

    def _vehicle_params(self, type_: VehicleType) -> tuple[float, float]:
        s = self.settings
        if type_ is VehicleType.TRUCK:
            return s.truck_length_m, kmh_to_ms(s.truck_speed_kmh)
        if type_ is VehicleType.BUS:
            return s.bus_length_m, kmh_to_ms(s.bus_speed_kmh)
        if type_ is VehicleType.MOTORCYCLE:
            return s.moto_length_m, kmh_to_ms(s.moto_speed_kmh)
        if type_ is VehicleType.EMERGENCY:
            return s.emergency_length_m, kmh_to_ms(s.emergency_speed_kmh)
        return s.car_length_m, kmh_to_ms(s.car_speed_kmh)

    # ------------------------------------------------------------------ tick
    def tick(self, now: float) -> list[Vehicle]:
        """Spawn any vehicles whose Poisson clock has elapsed."""
        produced: list[Vehicle] = []
        # 1) scripted spawns.
        while self._scripted and self._scripted[0][0] <= now:
            _, side, type_ = self._scripted.pop(0)
            length, speed = self._vehicle_params(type_)
            produced.append(self.world.spawn(side, type_, length, speed, now))
        # 2) Poisson spawns.
        for side, side_cfg in (
            (Side.A, self.config.side_a),
            (Side.B, self.config.side_b),
        ):
            while now >= self._next_at[side]:
                type_ = self._pick_type(side_cfg)
                length, speed = self._vehicle_params(type_)
                produced.append(self.world.spawn(side, type_, length, speed, now))
                self._next_at[side] = self._draw_next(
                    self._next_at[side], side_cfg.lambda_per_s
                )
        return produced
