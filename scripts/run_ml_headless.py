#!/usr/bin/env python3
"""Headless ML pipeline: processes video, outputs JSON report + per-frame CSV.

Designed for hackathon demo without GUI. Produces:
  - results/ml_report.json  — summary stats
  - results/crossings.csv   — every crossing event with timestamp
  - results/stats.json      — per-class breakdown

Usage:
    python scripts/run_ml_headless.py --video "4K Video of Highway Traffic!.mp4"
    python scripts/run_ml_headless.py --video input.mp4 --max-frames 500 --publish
"""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ml"))

from app.detector import Detector
from app.tracker import ByteTracker
from app.line_crossing import LineCrossingDetector


def run(args):
    video_path = Path(args.video)
    if not video_path.exists():
        print(f"Error: '{video_path}' not found")
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    max_frames = args.max_frames or total_frames

    print(f"Processing: {video_path.name} ({width}x{height}, {total_frames} frames)")
    print(f"Max frames: {max_frames}, skip: {args.skip}")

    detector = Detector(
        model_path=args.model,
        conf=args.conf,
        iou=args.iou,
        device=args.device,
        imgsz=args.imgsz,
        emergency_hsv=args.emergency_hsv,
    )
    print("Loading model...")
    _ = detector.model
    print("Model ready.")

    tracker = ByteTracker(iou_threshold=0.3, max_age=30)
    line_y = height // 2
    crossing = LineCrossingDetector(
        p1=(0.0, float(line_y)),
        p2=(float(width), float(line_y)),
        expected_dir=1,
    )

    # MQTT bridge (optional)
    mqtt_client = None
    if args.publish:
        try:
            import paho.mqtt.client as mqtt
            try:
                mqtt_client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id="demo-headless",
                )
            except AttributeError:
                mqtt_client = mqtt.Client(client_id="demo-headless")
            mqtt_client.connect(args.mqtt_host, args.mqtt_port)
            mqtt_client.loop_start()
            print(f"[MQTT] Connected to {args.mqtt_host}:{args.mqtt_port}")
        except Exception as e:
            print(f"[MQTT] Failed: {e}")
            mqtt_client = None

    crossings_log = []
    class_counts = {}
    in_count = 0
    out_count = 0
    frame_num = 0
    processed = 0
    t_start = time.time()

    while frame_num < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame_num += 1

        if args.skip > 1 and frame_num % args.skip != 0:
            continue

        # Downscale 4K for speed
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
        events = crossing.update(tracks)
        processed += 1

        for ev in events:
            if ev.direction == "in":
                in_count += 1
            else:
                out_count += 1

            class_counts[ev.cls_name] = class_counts.get(ev.cls_name, 0) + 1

            entry = {
                "frame": frame_num,
                "timestamp": frame_num / video_fps,
                "track_id": ev.track_id,
                "class": ev.cls_name,
                "direction": ev.direction,
                "confidence": round(ev.confidence, 4),
            }
            crossings_log.append(entry)

            if mqtt_client:
                payload = {
                    "ts": time.time(),
                    "track_id": ev.track_id,
                    "class": ev.cls_name,
                    "side": "A",
                    "dir": ev.direction,
                    "confidence": round(ev.confidence, 4),
                    "plate": None,
                }
                mqtt_client.publish(
                    f"corridor/cam/A/in/event",
                    json.dumps(payload),
                    qos=1,
                )

        if processed % 50 == 0:
            elapsed = time.time() - t_start
            pct = frame_num / max_frames * 100
            print(f"  [{pct:5.1f}%] frame {frame_num}/{max_frames} | "
                  f"IN={in_count} OUT={out_count} | "
                  f"{processed / elapsed:.1f} proc-fps")

    elapsed = time.time() - t_start
    cap.release()

    if mqtt_client:
        mqtt_client.disconnect()
        mqtt_client.loop_stop()

    # Write results
    report = {
        "video": str(video_path.name),
        "resolution": f"{width}x{height}",
        "video_fps": video_fps,
        "total_frames_read": frame_num,
        "frames_processed": processed,
        "processing_time_s": round(elapsed, 2),
        "processing_fps": round(processed / elapsed, 2) if elapsed > 0 else 0,
        "crossings_in": in_count,
        "crossings_out": out_count,
        "crossings_total": in_count + out_count,
        "class_breakdown": class_counts,
        "model": args.model,
        "confidence_threshold": args.conf,
        "device": args.device,
    }

    report_path = out_dir / "ml_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    csv_path = out_dir / "crossings.csv"
    if crossings_log:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=crossings_log[0].keys())
            writer.writeheader()
            writer.writerows(crossings_log)

    stats_path = out_dir / "stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(class_counts, f, indent=2)

    print("\n" + "=" * 60)
    print("  ML Pipeline Results")
    print("=" * 60)
    print(f"  Crossings IN:  {in_count}")
    print(f"  Crossings OUT: {out_count}")
    print(f"  Total:         {in_count + out_count}")
    print(f"  Classes:       {class_counts}")
    print(f"  Processing:    {processed / elapsed:.1f} FPS ({elapsed:.1f}s)")
    print(f"  Report:        {report_path}")
    print(f"  CSV:           {csv_path}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Headless ML pipeline — JSON/CSV output")
    parser.add_argument("--video", required=True)
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--emergency-hsv", action="store_true")
    parser.add_argument("--skip", type=int, default=1, help="Process every Nth frame")
    parser.add_argument("--max-frames", type=int, default=None, help="Stop after N frames")
    parser.add_argument("--output-dir", default="results", help="Output directory")
    parser.add_argument("--publish", action="store_true", help="Publish to MQTT")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
