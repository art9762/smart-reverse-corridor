"""Validate camera crossing identities and suppress recent MQTT redeliveries.

This process-local cache is bounded by both age and count. It is a demo
ingestion aid, not a durable exactly-once delivery guarantee.
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from typing import Any


class CameraEventGate:
    def __init__(self, *, ttl_s: float = 600.0, max_events: int = 10_000) -> None:
        if ttl_s <= 0 or max_events < 1:
            raise ValueError("camera event cache limits must be positive")
        self.ttl_s = ttl_s
        self.max_events = max_events
        self._seen: OrderedDict[tuple, float] = OrderedDict()

    def clear(self) -> None:
        self._seen.clear()

    def accept(self, side: str, direction: str, payload: Any) -> bool:
        """Return False for a replay; reject invalid identities before mutation.

        New publishers provide a unique event_id per crossing. Legacy events
        use the topic, track ID and source timestamp as their identity.
        """
        if side not in ("A", "B") or direction not in ("in", "out"):
            raise ValueError("unknown camera side or direction")
        if not isinstance(payload, dict):
            raise TypeError("camera event must be an object")
        if payload.get("side", side) != side or payload.get("dir", direction) != direction:
            raise ValueError("camera event side/dir does not match its topic")
        track_id = payload.get("track_id")
        if type(track_id) is not int or track_id < 0:
            raise ValueError("track_id must be a non-negative integer")
        timestamp = payload.get("ts")
        try:
            valid_timestamp = (
                type(timestamp) in (int, float) and math.isfinite(timestamp) and timestamp >= 0
            )
        except OverflowError:
            valid_timestamp = False
        if not valid_timestamp:
            raise ValueError("ts must be a finite non-negative number")
        if "event_id" in payload:
            event_id = payload["event_id"]
            if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 128:
                raise ValueError("event_id must be a non-empty string of at most 128 characters")
            key = (side, direction, "id", event_id)
        else:
            key = (side, direction, "legacy", track_id, timestamp)

        now = time.monotonic()
        cutoff = now - self.ttl_s
        while self._seen and next(iter(self._seen.values())) <= cutoff:
            self._seen.popitem(last=False)
        if key in self._seen:
            return False
        self._seen[key] = now
        while len(self._seen) > self.max_events:
            self._seen.popitem(last=False)
        return True
