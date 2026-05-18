"""World snapshot publisher.

Streams a compact slice of the simulated world to MQTT topic
``corridor/sim/world`` at a configurable rate (default 15 Hz, qos=0,
retain=false). The web UI consumes this topic to render the live road
view; the controller does NOT subscribe — it only reads CV events.

Schema matches ``docs/MQTT.md``::

    {
      "ts": float,
      "zone_length_m": float,
      "phase": "GREEN_A|GREEN_B|YELLOW|ALL_RED",
      "vehicles": [
        {
          "id": int, "side": "A|B", "type": str,
          "x": float,           # normalized to zone length, ~[0..1]
          "y": float,           # lane offset, reserved (always 0.0 today)
          "speed": float,       # m/s
          "len_m": float,
          "emergency": bool
        },
        ...
      ],
      "queues": {"A": int, "B": int}
    }

Vehicles still queueing on the approach lanes are included as well; their
``x`` may sit slightly outside ``[0, 1]`` — the dashboard clamps for
rendering and uses ``queues`` for the count badge.
"""
from __future__ import annotations

from typing import Callable

from .world import Phase, World

TOPIC = "corridor/sim/world"

PublishFn = Callable[[str, dict, int, bool], None]
"""Bus signature: ``(topic, payload_dict, qos, retain) -> None``."""


class WorldPublisher:
    """Periodically publishes a world snapshot to ``corridor/sim/world``.

    The publisher is rate-limited rather than tied to the simulator's tick
    so it stays steady regardless of ``--fast`` vs ``--realtime`` modes.
    """

    def __init__(
        self,
        publish: PublishFn,
        hz: float = 15.0,
        topic: str = TOPIC,
    ) -> None:
        if hz <= 0:
            raise ValueError("hz must be positive")
        self.publish = publish
        self.hz = float(hz)
        self.topic = topic
        self._period = 1.0 / self.hz
        self._last_emit_at: float = -1.0

    # ------------------------------------------------------------------ tick
    def maybe_emit(self, world: World, phase: Phase, now: float) -> bool:
        """Publish a snapshot if at least ``1/hz`` seconds have elapsed.

        Returns ``True`` when a snapshot was actually published.
        """
        if self._last_emit_at >= 0 and (now - self._last_emit_at) < self._period:
            return False
        self._last_emit_at = now
        self.publish(self.topic, self.snapshot(world, phase, now), 0, False)
        return True

    def force_emit(self, world: World, phase: Phase, now: float) -> None:
        """Publish a snapshot unconditionally (useful for tests/shutdown)."""
        self._last_emit_at = now
        self.publish(self.topic, self.snapshot(world, phase, now), 0, False)

    # ----------------------------------------------------------- snapshot
    def snapshot(self, world: World, phase: Phase, now: float) -> dict:
        """Build a single world snapshot dict matching the contract."""
        zone_length_m = float(world.zone_m)
        camera_x_a = world.camera_x_a
        vehicles: list[dict] = []
        for v in world.vehicles:
            if v.finished:
                continue
            x_norm = (v.position_m - camera_x_a) / zone_length_m
            vehicles.append(
                {
                    "id": int(v.id),
                    "side": v.side.value,
                    "type": v.type.value,
                    "x": round(x_norm, 4),
                    "y": 0.0,
                    "speed": round(float(v.speed_ms), 3),
                    "len_m": round(float(v.length_m), 2),
                    "emergency": bool(v.is_emergency),
                }
            )
        return {
            "ts": float(now),
            "zone_length_m": zone_length_m,
            "phase": phase.value,
            "vehicles": vehicles,
            "queues": {
                "A": len(world.queue_a),
                "B": len(world.queue_b),
            },
        }


__all__ = ["WorldPublisher", "TOPIC"]
