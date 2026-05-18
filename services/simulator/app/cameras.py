"""Virtual cameras: publish MQTT events that match `docs/MQTT.md` 1:1.

Each side has two virtual lines (`in` / `out`). When a vehicle crosses one
of them, we publish an event on `corridor/cam/<side>/<dir>/event`. We also
publish a 1 Hz heartbeat on `corridor/cam/<side>/<dir>/heartbeat` (retained).

The simulator can mark a camera "lost" — heartbeats stop and detections are
dropped. The controller observes camera health via the retained heartbeat
and via `corridor/state.camera_health`.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterable

from .world import Side, Vehicle

log = logging.getLogger(__name__)


CameraId = str  # "A_in", "A_out", "B_in", "B_out"
ALL_CAMERAS: tuple[CameraId, ...] = ("A_in", "A_out", "B_in", "B_out")


def camera_id(side: Side, direction: str) -> CameraId:
    return f"{side.value}_{direction}"


@dataclass
class CameraEvent:
    """Payload for `corridor/cam/<side>/<dir>/event`.

    Field order/types match `docs/MQTT.md`.
    """

    ts: float
    track_id: int
    cls: str
    side: str
    dir: str
    confidence: float
    plate: str | None = None

    def to_payload(self) -> dict:
        return {
            "ts": self.ts,
            "track_id": self.track_id,
            "class": self.cls,
            "side": self.side,
            "dir": self.dir,
            "confidence": self.confidence,
            "plate": self.plate,
        }


@dataclass
class HeartbeatPayload:
    ts: float
    camera_id: str
    fps: float
    healthy: bool

    def to_payload(self) -> dict:
        return {
            "ts": self.ts,
            "camera_id": self.camera_id,
            "fps": self.fps,
            "healthy": self.healthy,
        }


PublishFn = Callable[[str, dict, int, bool], None]
"""Callable signature: (topic, payload_dict, qos, retain) -> None."""


class CameraBus:
    """Couples world crossings with MQTT publication."""

    def __init__(
        self,
        publish: PublishFn,
        confidence: float = 0.93,
        fps: float = 24.7,
    ) -> None:
        self.publish = publish
        self.confidence = confidence
        self.fps = fps
        self._lost: dict[CameraId, float | None] = {c: None for c in ALL_CAMERAS}
        # Track when last heartbeat was sent. Negative sentinel ensures the
        # first call always emits.
        self._last_hb_at: float = -1.0

    # --------------------------------------------------------- camera health
    def set_lost(self, cam: CameraId, until: float | None) -> None:
        """Mark camera as lost. `until` may be None for permanent."""
        if cam not in self._lost:
            raise ValueError(f"unknown camera id: {cam}")
        self._lost[cam] = until or float("inf")
        log.info("camera %s marked lost until %s", cam, until)

    def restore(self, cam: CameraId) -> None:
        self._lost[cam] = None
        log.info("camera %s restored", cam)

    def is_healthy(self, cam: CameraId, now: float) -> bool:
        until = self._lost.get(cam)
        if until is None:
            return True
        if now >= until:
            self._lost[cam] = None
            return True
        return False

    # ------------------------------------------------------------------ tick
    def emit_events(
        self,
        crossings: Iterable[tuple[Vehicle, Side, str]],
        now: float,
    ) -> int:
        """Publish event messages for every crossing (skipping lost cams)."""
        sent = 0
        for vehicle, cam_side, direction in crossings:
            cam = camera_id(cam_side, direction)
            if not self.is_healthy(cam, now):
                continue
            evt = CameraEvent(
                ts=now,
                track_id=vehicle.id,
                cls=vehicle.type.value,
                side=cam_side.value,
                dir=direction,
                confidence=round(self.confidence, 3),
                plate=None,
            )
            topic = f"corridor/cam/{cam_side.value}/{direction}/event"
            self.publish(topic, evt.to_payload(), 1, False)
            sent += 1
        return sent

    def emit_heartbeats(self, now: float) -> int:
        """Publish 1 Hz heartbeats. Skipped for cameras marked lost."""
        if now - self._last_hb_at < 1.0:
            return 0
        self._last_hb_at = now
        sent = 0
        for cam in ALL_CAMERAS:
            healthy = self.is_healthy(cam, now)
            if not healthy:
                # Per contract, retained "healthy: false" lets controller
                # observe the loss; emitted once at start of outage.
                payload = HeartbeatPayload(
                    ts=now, camera_id=cam, fps=0.0, healthy=False
                ).to_payload()
            else:
                payload = HeartbeatPayload(
                    ts=now, camera_id=cam, fps=self.fps, healthy=True
                ).to_payload()
            side, direction = cam.split("_", 1)
            topic = f"corridor/cam/{side}/{direction}/heartbeat"
            self.publish(topic, payload, 1, True)
            sent += 1
        return sent
