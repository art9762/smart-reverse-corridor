#!/usr/bin/env python3
"""Generate detection snapshots from video for presentation slides.

Saves annotated frames at regular intervals to results/snapshots/.
Great for hackathon pitch decks.

Usage:
    python scripts/generate_snapshots.py --video "4K Video of Highway Traffic!.mp4" --count 5
"""
import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ml"))

from app.detector import Detector
from app.tracker import ByteTracker


def _class_color(cls_name: str) -> tuple:
    return {
        "car": (0, 255, 0),
        "motorcycle": (255, 0, 255),
        "bus": (255, 165, 0),
        "truck": (0, 165, 255),
        "emergency": (0, 0, 255),
    }.get(cls_name, (255, 255, 255))


def main():
    parser = argparse.ArgumentParser(description="Generate annotated snapshots")
    parser.add_argument("--video", required=True)
    parser.add_argument("--count", type=int, default=5, help="Number of snapshots")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output-dir", default="results/snapshots")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"Cannot open: {args.video}")
        sys.exit(1)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    interval = max(1, total // (args.count + 1))

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    detector = Detector(model_path=args.model, conf=args.conf, device=args.device, imgsz=640)
    print("Loading model...")
    _ = detector.model
    tracker = ByteTracker()

    print(f"Generating {args.count} snapshots from {total} frames (interval={interval})")

    saved = 0
    for i in range(args.count):
        target_frame = (i + 1) * interval
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        if not ret:
            break

        if width > 1920:
            scale = 1920.0 / width
            proc = cv2.resize(frame, (1920, int(height * scale)))
        else:
            scale = 1.0
            proc = frame

        dets = detector.infer(proc)
        if scale != 1.0:
            for d in dets:
                x1, y1, x2, y2 = d.bbox
                d.bbox = (x1 / scale, y1 / scale, x2 / scale, y2 / scale)

        tracks = tracker.update(dets)

        for t in tracks:
            x1, y1, x2, y2 = (int(c) for c in t.bbox)
            color = _class_color(t.cls_name)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            label = f"{t.cls_name} {t.confidence:.0%}"
            cv2.putText(frame, label, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # Add crossing line
        line_y = height // 2
        cv2.line(frame, (0, line_y), (width, line_y), (0, 255, 255), 3)

        # Add branding
        cv2.putText(frame, "Smart Reverse Corridor | YOLOv8 Detection",
                    (20, height - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        # Save (downscale to 1920 for reasonable file size)
        if width > 1920:
            frame = cv2.resize(frame, (1920, int(height * 1920 / width)))

        path = out_dir / f"snapshot_{saved + 1:02d}_frame{target_frame}.jpg"
        cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f"  Saved: {path}")
        saved += 1

    cap.release()
    print(f"\nDone. {saved} snapshots in {out_dir}/")


if __name__ == "__main__":
    main()
