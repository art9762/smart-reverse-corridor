"""Domain model for the reverse-corridor world.

Pure data + transition logic; no pygame, no MQTT. Headless-friendly.

Layout (X axis runs left → right, in metres):

    0                 approach_m         approach_m + zone_m            total_m
    ├── A approach ───┼──── work zone ─────────┼─── B approach ────┤
                      ▲                          ▲
                  A camera lines            B camera lines
                  (A_in / A_out)            (B_in / B_out)

* "Side A" cars enter the zone moving right (positive direction).
* "Side B" cars enter the zone moving left (negative direction).
* `Side.A` queue waits at x ≈ approach_m (just before A camera lines).
* `Side.B` queue waits at x ≈ approach_m + zone_m (just before B camera lines).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class Side(str, Enum):
    A = "A"
    B = "B"

    @property
    def opposite(self) -> "Side":
        return Side.B if self is Side.A else Side.A


class VehicleType(str, Enum):
    CAR = "car"
    TRUCK = "truck"
    BUS = "bus"
    MOTORCYCLE = "motorcycle"
    EMERGENCY = "emergency"


class Phase(str, Enum):
    """Phases mirror the controller FSM contract."""

    GREEN_A = "GREEN_A"
    GREEN_B = "GREEN_B"
    YELLOW = "YELLOW"
    ALL_RED = "ALL_RED"


def kmh_to_ms(kmh: float) -> float:
    return kmh * 1000.0 / 3600.0


@dataclass
class Vehicle:
    """A single vehicle in the simulated world."""

    id: int
    type: VehicleType
    side: Side  # origin side
    length_m: float
    cruise_speed_ms: float
    position_m: float
    speed_ms: float = 0.0
    in_zone: bool = False
    finished: bool = False
    spawned_at: float = 0.0
    entered_zone_at: float | None = None
    exited_zone_at: float | None = None
    # Tracking of which camera lines have already been reported, so each
    # crossing fires exactly once.
    crossed: set[str] = field(default_factory=set)
    # Per-vehicle artificial freeze (used by the stuck_vehicle scenario).
    stuck_until: float | None = None

    @property
    def direction(self) -> int:
        """+1 for A→B, -1 for B→A."""
        return 1 if self.side is Side.A else -1

    @property
    def is_emergency(self) -> bool:
        return self.type is VehicleType.EMERGENCY

    @property
    def front_m(self) -> float:
        """X coordinate of the vehicle's front bumper."""
        return self.position_m + (self.length_m / 2.0) * self.direction

    @property
    def rear_m(self) -> float:
        return self.position_m - (self.length_m / 2.0) * self.direction


@dataclass
class World:
    """Holds geometry, queues, and all live vehicles."""

    approach_m: float
    zone_m: float
    next_id: int = 1
    now: float = 0.0
    vehicles: list[Vehicle] = field(default_factory=list)
    queue_a: list[Vehicle] = field(default_factory=list)
    queue_b: list[Vehicle] = field(default_factory=list)
    inside_a: list[Vehicle] = field(default_factory=list)
    inside_b: list[Vehicle] = field(default_factory=list)
    finished: list[Vehicle] = field(default_factory=list)
    # Camera line X coordinates: both A_in and A_out sit at the A boundary,
    # both B_in and B_out at the B boundary. Direction selects which one.
    camera_x_a: float = 0.0
    camera_x_b: float = 0.0
    total_m: float = 0.0

    def __post_init__(self) -> None:
        self.camera_x_a = self.approach_m
        self.camera_x_b = self.approach_m + self.zone_m
        self.total_m = self.approach_m * 2 + self.zone_m

    # ------------------------------------------------------------------ spawn
    def spawn(
        self,
        side: Side,
        type_: VehicleType,
        length_m: float,
        cruise_speed_ms: float,
        now: float,
    ) -> Vehicle:
        """Add a vehicle at the far approach of `side` and queue it up."""
        position = self._tail_position(
            self._queue_for(side), side, length_m
        )
        v = Vehicle(
            id=self.next_id,
            type=type_,
            side=side,
            length_m=length_m,
            cruise_speed_ms=cruise_speed_ms,
            position_m=position,
            speed_ms=0.0,
            spawned_at=now,
        )
        self.next_id += 1
        self.vehicles.append(v)
        self._queue_for(side).append(v)
        return v

    def _tail_position(
        self, queue: list[Vehicle], side: Side, length_m: float
    ) -> float:
        """Return spawn x-coordinate for a new vehicle on `side`.

        Cars stack up behind the camera-line stop bar with a 1m gap. The
        lead car's front bumper sits just before the stop bar, accounting
        for vehicle length so spawning never crosses the camera line.
        """
        gap_m = 1.0
        if side is Side.A:
            stop = self.camera_x_a
            if not queue:
                # Front bumper at stop - gap. Center is half-length behind.
                return stop - gap_m - length_m / 2.0
            tail = min(v.rear_m for v in queue)
            # Behind tail by gap, center half-length behind that.
            return tail - gap_m - length_m / 2.0
        else:
            stop = self.camera_x_b
            if not queue:
                return stop + gap_m + length_m / 2.0
            tail = max(v.rear_m for v in queue)
            return tail + gap_m + length_m / 2.0

    def _queue_for(self, side: Side) -> list[Vehicle]:
        return self.queue_a if side is Side.A else self.queue_b

    # ----------------------------------------------------------------- update
    def step(self, dt: float, phase: Phase, now: float) -> None:
        """Advance the world by `dt` seconds.

        `phase` is the active corridor phase (controller- or baseline-driven).
        """
        self.now = now
        # Each side's stop bar is open only when its phase is GREEN.
        green_a = phase is Phase.GREEN_A
        green_b = phase is Phase.GREEN_B
        # Process queues + in-zone vehicles; cars proceed into the zone only
        # when their side has the green light AND the gap ahead is clear.
        self._advance_queue(self.queue_a, Side.A, green_a, dt)
        self._advance_queue(self.queue_b, Side.B, green_b, dt)
        self._advance_in_zone(dt)
        self._reap_finished()

    def _advance_queue(
        self,
        queue: list[Vehicle],
        side: Side,
        green: bool,
        dt: float,
    ) -> None:
        # Queued cars: lead car may move towards/across the camera line if
        # green; followers always close the gap to the car ahead.
        ordered = self._ordered_queue(queue, side)
        prev_front: float | None = None
        for idx, v in enumerate(ordered):
            target_speed = v.cruise_speed_ms if (idx == 0 and green) else 0.0
            # Followers track the rear of the car ahead with a 1m buffer.
            if prev_front is not None:
                buffer = 1.0
                gap_target = prev_front - buffer * v.direction
                # If we are already behind gap_target, follower may inch up.
                if side is Side.A and gap_target > v.front_m:
                    target_speed = v.cruise_speed_ms
                elif side is Side.B and gap_target < v.front_m:
                    target_speed = v.cruise_speed_ms
            self._apply_speed(v, target_speed, dt)
            prev_front = v.rear_m

    def _ordered_queue(self, queue: list[Vehicle], side: Side) -> list[Vehicle]:
        # Lead car is the one closest to its camera line.
        if side is Side.A:
            return sorted(queue, key=lambda v: v.front_m, reverse=True)
        return sorted(queue, key=lambda v: v.front_m)

    def _advance_in_zone(self, dt: float) -> None:
        for v in list(self.inside_a) + list(self.inside_b):
            self._apply_speed(v, v.cruise_speed_ms, dt)

    def _apply_speed(self, v: Vehicle, target_speed: float, dt: float) -> None:
        if v.stuck_until is not None and self.now < v.stuck_until:
            v.speed_ms = 0.0
            return
        # Simple smoothing: 1 m/s² accel/decel limit.
        accel = 1.5
        delta = target_speed - v.speed_ms
        v.speed_ms += max(-accel * dt, min(accel * dt, delta))
        v.position_m += v.speed_ms * dt * v.direction

    # ----------------------------------------------------------------- camera
    def detect_crossings(self) -> list[tuple[Vehicle, Side, str]]:
        """Yield (vehicle, camera_side, dir) tuples for newly-crossed lines.

        Each crossing fires once thanks to the per-vehicle `crossed` set.

        * Vehicle from `Side.A` crossing camera_x_a (going right) → `(A, in)`
        * Vehicle from `Side.A` crossing camera_x_b (going right) → `(B, out)`
        * Vehicle from `Side.B` crossing camera_x_b (going left)  → `(B, in)`
        * Vehicle from `Side.B` crossing camera_x_a (going left)  → `(A, out)`
        """
        events: list[tuple[Vehicle, Side, str]] = []
        for v in self.vehicles:
            if v.finished:
                continue
            if v.side is Side.A:
                key_in = "A_in"
                if key_in not in v.crossed and v.front_m >= self.camera_x_a:
                    v.crossed.add(key_in)
                    v.in_zone = True
                    v.entered_zone_at = self.now
                    self._move_to_zone(v)
                    events.append((v, Side.A, "in"))
                key_out = "B_out"
                if key_out not in v.crossed and v.front_m >= self.camera_x_b:
                    v.crossed.add(key_out)
                    v.in_zone = False
                    v.exited_zone_at = self.now
                    events.append((v, Side.B, "out"))
            else:
                key_in = "B_in"
                if key_in not in v.crossed and v.front_m <= self.camera_x_b:
                    v.crossed.add(key_in)
                    v.in_zone = True
                    v.entered_zone_at = self.now
                    self._move_to_zone(v)
                    events.append((v, Side.B, "in"))
                key_out = "A_out"
                if key_out not in v.crossed and v.front_m <= self.camera_x_a:
                    v.crossed.add(key_out)
                    v.in_zone = False
                    v.exited_zone_at = self.now
                    events.append((v, Side.A, "out"))
        return events

    def _move_to_zone(self, v: Vehicle) -> None:
        if v.side is Side.A and v in self.queue_a:
            self.queue_a.remove(v)
            self.inside_a.append(v)
        elif v.side is Side.B and v in self.queue_b:
            self.queue_b.remove(v)
            self.inside_b.append(v)

    def _reap_finished(self) -> None:
        """Move vehicles past the far approach into the finished bucket."""
        for v in list(self.vehicles):
            if v.finished:
                continue
            if v.side is Side.A and v.position_m >= self.total_m:
                self._finish(v)
            elif v.side is Side.B and v.position_m <= 0:
                self._finish(v)

    def _finish(self, v: Vehicle) -> None:
        v.finished = True
        if v in self.inside_a:
            self.inside_a.remove(v)
        if v in self.inside_b:
            self.inside_b.remove(v)
        if v in self.queue_a:
            self.queue_a.remove(v)
        if v in self.queue_b:
            self.queue_b.remove(v)
        if v in self.vehicles:
            self.vehicles.remove(v)
        self.finished.append(v)

    # ------------------------------------------------------------------ misc
    def queue_lengths(self) -> tuple[int, int]:
        return len(self.queue_a), len(self.queue_b)

    def inside_counts(self) -> tuple[int, int]:
        return len(self.inside_a), len(self.inside_b)

    def all_active(self) -> Iterable[Vehicle]:
        yield from self.vehicles
