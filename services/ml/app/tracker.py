"""Lightweight tracker wrapper.

We do NOT depend on a specific Ultralytics tracker API surface — they change
between versions. Instead we ship a small ByteTrack-style tracker built on
top of IoU + Kalman-free greedy assignment. It's enough for line-crossing
counting on stationary cameras, and unit-testable.

If you have `ultralytics`'s built-in tracker available you can swap it in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .detector import Detection


@dataclass
class Track:
    """A persistent track across frames."""

    track_id: int
    bbox: tuple[float, float, float, float]
    confidence: float
    cls_name: str
    age: int = 0          # frames since first seen
    misses: int = 0       # consecutive frames without a match
    hits: int = 1         # total matched frames

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) * 0.5, (y1 + y2) * 0.5)


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    iw = max(0.0, inter_x2 - inter_x1)
    ih = max(0.0, inter_y2 - inter_y1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class ByteTracker:
    """Greedy IoU-based multi-object tracker (ByteTrack-lite).

    - High-conf detections drive matching first; low-conf are tried second
      against still-unmatched tracks (the ByteTrack idea).
    - Tracks that miss > `max_age` frames are dropped.
    - `track_id` monotonically increases. `reset()` re-bases the offset so
      that looped video doesn't keep growing IDs forever.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_age: int = 30,
        high_conf: float = 0.5,
    ) -> None:
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.high_conf = high_conf
        self._tracks: list[Track] = []
        self._next_id = 1
        self._id_offset = 0

    def reset(self) -> None:
        """Drop all tracks; bump ID offset so external IDs stay unique."""
        self._id_offset += self._next_id
        self._next_id = 1
        self._tracks = []

    def _new_track(self, det: Detection) -> Track:
        tid = self._next_id + self._id_offset
        self._next_id += 1
        return Track(
            track_id=tid,
            bbox=det.bbox,
            confidence=det.confidence,
            cls_name=det.cls_name,
        )

    def update(self, detections: list[Detection]) -> list[Track]:
        """Match detections to existing tracks, return active tracks."""
        # Split by confidence (ByteTrack)
        high = [d for d in detections if d.confidence >= self.high_conf]
        low = [d for d in detections if d.confidence < self.high_conf]

        unmatched_tracks = list(range(len(self._tracks)))
        matched_pairs: list[tuple[int, int]] = []  # (track_idx, det) NOT used directly
        used_dets: set[int] = set()

        def _greedy(dets: list[Detection], pool: list[int]) -> list[int]:
            """Match `dets` to track indices in `pool` greedily by IoU."""
            still_unmatched = list(pool)
            for di, d in enumerate(dets):
                if di in used_dets:
                    continue
                best_iou = self.iou_threshold
                best_ti: Optional[int] = None
                for ti in still_unmatched:
                    iou = _iou(self._tracks[ti].bbox, d.bbox)
                    if iou >= best_iou:
                        best_iou = iou
                        best_ti = ti
                if best_ti is not None:
                    t = self._tracks[best_ti]
                    t.bbox = d.bbox
                    t.confidence = d.confidence
                    if d.cls_name == "emergency":
                        t.cls_name = "emergency"
                    elif t.cls_name != "emergency":
                        t.cls_name = d.cls_name
                    t.misses = 0
                    t.hits += 1
                    t.age += 1
                    still_unmatched.remove(best_ti)
                    used_dets.add(di)
            return still_unmatched

        unmatched_tracks = _greedy(high, unmatched_tracks)
        unmatched_tracks = _greedy(low, unmatched_tracks)

        # Unmatched high-conf detections start new tracks.
        for di, d in enumerate(high):
            if di in used_dets:
                continue
            self._tracks.append(self._new_track(d))

        # Age out unmatched tracks.
        survivors: list[Track] = []
        # Set of indices we already advanced via `_greedy`.
        advanced = {ti for ti in range(len(self._tracks)) if ti not in unmatched_tracks}
        for i, t in enumerate(self._tracks):
            if i in unmatched_tracks:
                t.misses += 1
                t.age += 1
            elif i not in advanced:
                # Fresh track from this frame's high-conf det
                t.age = max(t.age, 1)
            if t.misses <= self.max_age:
                survivors.append(t)
        self._tracks = survivors

        return [t for t in self._tracks if t.misses == 0]


__all__ = ["ByteTracker", "Track"]
