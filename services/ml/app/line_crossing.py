"""Virtual line-crossing detector.

A line is a pair of points (p1, p2). For every track we remember which
side of the line its center was on in the previous frame. When the side
flips, we emit a crossing event. The "expected" direction is configured
per camera via calibration; only matching crossings are reported as
events (others are noise).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .tracker import Track


Point = tuple[float, float]


def _side(line_p1: Point, line_p2: Point, p: Point) -> int:
    """Return sign of cross-product: +1, -1, or 0 (on the line)."""
    (x1, y1), (x2, y2), (px, py) = line_p1, line_p2, p
    cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
    if cross > 0:
        return 1
    if cross < 0:
        return -1
    return 0


@dataclass
class CrossingEvent:
    """One line crossing event."""

    track_id: int
    cls_name: str
    confidence: float
    direction: str  # "in" or "out" (from the camera's perspective)
    crossed_from: int  # -1 / +1
    crossed_to: int  # -1 / +1


@dataclass
class LineCrossingDetector:
    """Stateful crossing detector for a single virtual line.

    Parameters
    ----------
    p1, p2:
        Endpoints of the line (image coordinates).
    expected_dir:
        Which sign-flip counts as the "in" direction. Either +1 or -1.
        A track going from `-expected_dir` to `+expected_dir` produces an
        "in" event; the opposite produces "out". If None, both directions
        are reported as "in".
    """

    p1: Point
    p2: Point
    expected_dir: Optional[int] = None
    _last_side: dict[int, int] = field(default_factory=dict)

    def update(self, tracks: list[Track]) -> list[CrossingEvent]:
        """Feed current tracks; return events for this frame."""
        events: list[CrossingEvent] = []
        seen_ids: set[int] = set()
        for t in tracks:
            seen_ids.add(t.track_id)
            now = _side(self.p1, self.p2, t.center)
            prev = self._last_side.get(t.track_id)
            self._last_side[t.track_id] = now
            if prev is None or now == 0 or prev == 0:
                continue
            if prev == now:
                continue
            # Sign flipped → crossing
            if self.expected_dir is None:
                direction = "in"
            else:
                direction = "in" if now == self.expected_dir else "out"
            events.append(
                CrossingEvent(
                    track_id=t.track_id,
                    cls_name=t.cls_name,
                    confidence=t.confidence,
                    direction=direction,
                    crossed_from=prev,
                    crossed_to=now,
                )
            )
        # Forget tracks that are gone, so memory stays bounded.
        for tid in list(self._last_side.keys()):
            if tid not in seen_ids:
                self._last_side.pop(tid, None)
        return events

    def reset(self) -> None:
        """Forget all per-track side history (used on video loop)."""
        self._last_side.clear()


__all__ = ["LineCrossingDetector", "CrossingEvent", "Point"]
