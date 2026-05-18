"""YOLOv8 wrapper that yields filtered vehicle detections.

Returns a list of `Detection` objects per frame. Filters by COCO classes:
car (2), motorcycle (3), bus (5), truck (7).

Optionally tags `class="emergency"` via simple HSV heuristic for blue/red
flashers (can be toggled via ML_EMERGENCY_HSV).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np

# COCO class ids that we care about.
VEHICLE_COCO_IDS = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


@dataclass
class Detection:
    """One detected vehicle on a single frame."""

    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    confidence: float
    cls_id: int
    cls_name: str
    extra: dict = field(default_factory=dict)


def _emergency_score(frame: np.ndarray, bbox: tuple[float, float, float, float]) -> float:
    """Cheap HSV check: ratio of bright blue OR red pixels inside bbox.

    Returns score in [0, 1]; >0.05 typically indicates a flasher present.
    `cv2` import is local so unit tests can mock it out.
    """
    try:
        import cv2  # local import keeps tests light
    except Exception:  # pragma: no cover - cv2 always present in runtime
        return 0.0

    x1, y1, x2, y2 = (int(v) for v in bbox)
    h, w = frame.shape[:2]
    x1 = max(0, min(w - 1, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h - 1, y1))
    y2 = max(0, min(h, y2))
    if x2 <= x1 or y2 <= y1:
        return 0.0

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    # bright red: H<10 or H>170, S>120, V>180
    red1 = cv2.inRange(hsv, (0, 120, 180), (10, 255, 255))
    red2 = cv2.inRange(hsv, (170, 120, 180), (180, 255, 255))
    # bright blue: H 100-130, S>120, V>180
    blue = cv2.inRange(hsv, (100, 120, 180), (130, 255, 255))

    flasher = cv2.bitwise_or(cv2.bitwise_or(red1, red2), blue)
    return float(np.count_nonzero(flasher)) / float(crop.shape[0] * crop.shape[1])


class Detector:
    """Thin wrapper around `ultralytics.YOLO`.

    Loads model once and exposes `infer(frame)` returning `list[Detection]`.
    """

    def __init__(
        self,
        model_path: str,
        conf: float = 0.35,
        iou: float = 0.5,
        device: str = "cpu",
        imgsz: int = 640,
        emergency_hsv: bool = False,
    ) -> None:
        self.model_path = model_path
        self.conf = conf
        self.iou = iou
        self.device = device
        self.imgsz = imgsz
        self.emergency_hsv = emergency_hsv
        self._model = None  # lazy

    @property
    def model(self):
        """Lazy-load the YOLO model so unit tests don't need weights."""
        if self._model is None:
            # If running on CPU keep torch threads small (per task spec).
            if self.device == "cpu":
                try:
                    import torch

                    torch.set_num_threads(2)
                except Exception:
                    pass
            from ultralytics import YOLO  # local import

            self._model = YOLO(self.model_path)
        return self._model

    def infer(self, frame: np.ndarray) -> list[Detection]:
        """Run YOLO on one frame, return only vehicle detections."""
        results = self.model.predict(
            source=frame,
            conf=self.conf,
            iou=self.iou,
            device=self.device,
            imgsz=self.imgsz,
            verbose=False,
        )
        detections: list[Detection] = []
        if not results:
            return detections

        r0 = results[0]
        boxes = getattr(r0, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return detections

        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy().astype(int)

        for bb, cf, cls_id in zip(xyxy, confs, clss):
            if int(cls_id) not in VEHICLE_COCO_IDS:
                continue
            cls_name = VEHICLE_COCO_IDS[int(cls_id)]
            d = Detection(
                bbox=tuple(float(v) for v in bb),
                confidence=float(cf),
                cls_id=int(cls_id),
                cls_name=cls_name,
            )
            if self.emergency_hsv:
                score = _emergency_score(frame, d.bbox)
                if score > 0.05:
                    d.cls_name = "emergency"
                    d.extra["emergency_score"] = score
            detections.append(d)
        return detections


__all__ = ["Detector", "Detection", "VEHICLE_COCO_IDS"]
