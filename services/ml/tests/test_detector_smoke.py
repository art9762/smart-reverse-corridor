"""Smoke test for the detector wrapper without loading a real model.

We monkeypatch `Detector.model` to a stub that emulates ultralytics output.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import detector as detector_mod  # noqa: E402
from app.detector import Detector  # noqa: E402


class _FakeBoxes:
    def __init__(self, xyxy, conf, cls):
        self.xyxy = SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.array(xyxy, dtype=float)))
        self.conf = SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.array(conf, dtype=float)))
        self.cls = SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.array(cls, dtype=float)))

    def __len__(self):
        return len(self.cls.cpu().numpy())


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class _FakeModel:
    """Stand-in for ultralytics.YOLO."""

    def __init__(self, predictions):
        self._predictions = predictions

    def predict(self, **kwargs):
        return self._predictions


def test_detector_filters_non_vehicle_classes(monkeypatch):
    """Only car/truck/bus/motorcycle survive filtering."""
    boxes = _FakeBoxes(
        xyxy=[[10, 10, 50, 50], [60, 60, 100, 100], [110, 110, 150, 150]],
        conf=[0.9, 0.8, 0.7],
        cls=[2, 0, 7],  # car, person, truck
    )
    fake = _FakeModel(predictions=[_FakeResult(boxes)])

    det = Detector(model_path="fake.pt", emergency_hsv=False)
    monkeypatch.setattr(Detector, "model", property(lambda self: fake))

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    out = det.infer(frame)

    assert len(out) == 2
    assert {d.cls_name for d in out} == {"car", "truck"}


def test_detector_handles_empty_results(monkeypatch):
    fake = _FakeModel(predictions=[])
    det = Detector(model_path="fake.pt")
    monkeypatch.setattr(Detector, "model", property(lambda self: fake))

    out = det.infer(np.zeros((100, 100, 3), dtype=np.uint8))
    assert out == []


def test_detector_handles_no_boxes(monkeypatch):
    fake = _FakeModel(predictions=[_FakeResult(boxes=None)])
    det = Detector(model_path="fake.pt")
    monkeypatch.setattr(Detector, "model", property(lambda self: fake))
    out = det.infer(np.zeros((100, 100, 3), dtype=np.uint8))
    assert out == []


def test_emergency_hsv_disabled_keeps_yolo_class(monkeypatch):
    """With emergency_hsv=False we never override class to 'emergency'."""
    boxes = _FakeBoxes(
        xyxy=[[10, 10, 50, 50]],
        conf=[0.95],
        cls=[2],
    )
    fake = _FakeModel(predictions=[_FakeResult(boxes)])
    det = Detector(model_path="fake.pt", emergency_hsv=False)
    monkeypatch.setattr(Detector, "model", property(lambda self: fake))

    # Frame full of bright blue — should NOT matter when flag is off.
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[:, :] = (255, 0, 0)  # BGR blue

    out = det.infer(frame)
    assert len(out) == 1
    assert out[0].cls_name == "car"


def test_detection_dataclass_fields():
    from app.detector import Detection

    d = Detection(bbox=(0, 0, 10, 10), confidence=0.5, cls_id=2, cls_name="car")
    assert d.bbox == (0, 0, 10, 10)
    assert d.cls_name == "car"
    assert d.extra == {}
