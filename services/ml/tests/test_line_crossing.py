"""Unit tests for the virtual line-crossing detector."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python -m pytest tests/` from services/ml without packaging.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.line_crossing import LineCrossingDetector  # noqa: E402
from app.tracker import Track  # noqa: E402


def _track_at(track_id: int, x: float, y: float, cls_name: str = "car") -> Track:
    return Track(
        track_id=track_id,
        bbox=(x - 5, y - 5, x + 5, y + 5),
        confidence=0.9,
        cls_name=cls_name,
    )


def test_horizontal_line_crossing_top_to_bottom_emits_in():
    """Horizontal line y=100. Track moves from y=80 → y=120 → 'in'."""
    det = LineCrossingDetector(p1=(0, 100), p2=(200, 100), expected_dir=1)
    # Frame 1: above the line (no event yet)
    assert det.update([_track_at(1, 50, 80)]) == []
    # Frame 2: below the line — should emit one event
    events = det.update([_track_at(1, 50, 120)])
    assert len(events) == 1
    e = events[0]
    assert e.track_id == 1
    assert e.cls_name == "car"
    # `expected_dir=1` so crossing into +1 is "in".
    assert e.direction == "in"


def test_horizontal_line_reverse_direction_is_out():
    det = LineCrossingDetector(p1=(0, 100), p2=(200, 100), expected_dir=1)
    det.update([_track_at(1, 50, 120)])  # below first
    events = det.update([_track_at(1, 50, 80)])  # crosses upward
    assert len(events) == 1
    assert events[0].direction == "out"


def test_no_event_if_track_stays_same_side():
    det = LineCrossingDetector(p1=(0, 100), p2=(200, 100), expected_dir=1)
    det.update([_track_at(1, 50, 50)])
    events = det.update([_track_at(1, 60, 60)])
    assert events == []


def test_track_disappears_then_reappears_does_not_double_count():
    det = LineCrossingDetector(p1=(0, 100), p2=(200, 100), expected_dir=1)
    det.update([_track_at(1, 50, 80)])
    events1 = det.update([_track_at(1, 50, 120)])
    assert len(events1) == 1

    # Track disappears for a frame.
    det.update([])

    # New track id is treated as new track; first frame seen is 'below', no
    # event yet because there is no previous side info.
    events_new = det.update([_track_at(2, 50, 130)])
    assert events_new == []


def test_multiple_tracks_independent():
    det = LineCrossingDetector(p1=(0, 100), p2=(200, 100), expected_dir=1)
    det.update([_track_at(1, 50, 80), _track_at(2, 60, 130)])
    events = det.update([_track_at(1, 50, 120), _track_at(2, 60, 80)])
    assert len(events) == 2
    by_id = {e.track_id: e.direction for e in events}
    assert by_id[1] == "in"
    assert by_id[2] == "out"


def test_reset_clears_state():
    det = LineCrossingDetector(p1=(0, 100), p2=(200, 100), expected_dir=1)
    det.update([_track_at(1, 50, 80)])
    det.reset()
    # After reset the same track at y=120 has no prior side info → no event.
    events = det.update([_track_at(1, 50, 120)])
    assert events == []


def test_diagonal_line():
    """Line from (0,0) to (100,100). Track moving across triggers crossing."""
    det = LineCrossingDetector(p1=(0, 0), p2=(100, 100), expected_dir=1)
    det.update([_track_at(1, 80, 20)])  # below the diagonal (y < x → side -1)
    events = det.update([_track_at(1, 20, 80)])  # above the diagonal
    assert len(events) == 1


def test_class_name_propagates():
    det = LineCrossingDetector(p1=(0, 100), p2=(200, 100), expected_dir=1)
    det.update([_track_at(1, 50, 80, cls_name="truck")])
    events = det.update([_track_at(1, 50, 120, cls_name="truck")])
    assert events[0].cls_name == "truck"


def test_emergency_class_carries_through():
    det = LineCrossingDetector(p1=(0, 100), p2=(200, 100), expected_dir=1)
    det.update([_track_at(1, 50, 80, cls_name="emergency")])
    events = det.update([_track_at(1, 50, 120, cls_name="emergency")])
    assert events[0].cls_name == "emergency"
