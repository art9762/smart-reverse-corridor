#!/usr/bin/env python3
"""ML pipeline demo: YOLO detection + ByteTrack + line crossing visualization.

Usage:
    python scripts/demo_ml.py --video path/to/video.mp4
    python scripts/demo_ml.py --synthetic          # no video needed
    python scripts/demo_ml.py --video path.mp4 --publish  # also send to MQTT
"""
import argparse
import os
import sys

import cv2
import numpy as np

# Add ML service to path so `from app.xxx import ...` works.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ml"))


# ---------------------------------------------------------------------------
# Synthetic mode helpers
# ---------------------------------------------------------------------------

def _create_synthetic_frame(
    width: int,
    height: int,
    vehicles: list,
) -> np.ndarray:
    """Generate a synthetic frame with moving rectangles simulating vehicles."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    # Road surface
    cv2.rectangle(frame, (0, height // 3), (width, 2 * height // 3), (40, 40, 40), -1)
    # Dashed centre line
    for x in range(0, width, 40):
        cv2.line(frame, (x, height // 2), (x + 20, height // 2), (200, 200, 200), 2)
    # Vehicles as filled rectangles
    for v in vehicles:
        x, y, w, h = int(v["x"]), int(v["y"]), int(v["w"]), int(v["h"])
        cv2.rectangle(frame, (x, y), (x + w, y + h), v["color"], -1)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 255), 1)
    return frame


def run_synthetic_demo(
    publish: bool = False,
    mqtt_host: str = "127.0.0.1",
    mqtt_port: int = 1883,
) -> None:
    """Run demo with synthetic moving rectangles (no ML deps required)."""
    width, height = 1280, 720
    line_x = width // 2

    vehicles: list = []
    next_id = 1
    tick = 0
    in_count = 0
    out_count = 0

    print("=== Synthetic ML Demo ===")
    print(f"Virtual crossing line at x={line_x}")
    print("Press 'q' to quit, 's' to spawn a vehicle immediately")
    print()

    while True:
        tick += 1

        # Auto-spawn every 60 ticks
        if tick % 60 == 0:
            _spawn_vehicle(vehicles, next_id, width, height)
            next_id += 1

        # Update positions
        for v in vehicles:
            v["x"] += v["speed"]

        # Check line crossings
        for v in vehicles:
            if not v["crossed"]:
                prev_x = v["x"] - v["speed"]
                curr_x = v["x"]
                if v["direction"] > 0 and prev_x < line_x <= curr_x:
                    v["crossed"] = True
                    in_count += 1
                    print(f"  [CROSS] Vehicle {v['id']} crossed IN  (->)")
                elif v["direction"] < 0 and prev_x > line_x >= curr_x:
                    v["crossed"] = True
                    out_count += 1
                    print(f"  [CROSS] Vehicle {v['id']} crossed OUT (<-)")

        # Remove off-screen vehicles
        vehicles = [v for v in vehicles if -200 < v["x"] < width + 200]

        frame = _create_synthetic_frame(width, height, vehicles)

        # Crossing line
        cv2.line(frame, (line_x, height // 3), (line_x, 2 * height // 3), (0, 255, 255), 3)
        cv2.putText(
            frame, "CROSSING LINE",
            (line_x - 60, height // 3 - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1,
        )

        # Bounding boxes with IDs (simulating tracker output)
        for v in vehicles:
            x, y, w, h = int(v["x"]), int(v["y"]), int(v["w"]), int(v["h"])
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(
                frame, f"ID:{v['id']} car",
                (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1,
            )

        # HUD
        cv2.putText(
            frame, f"IN: {in_count}  OUT: {out_count}",
            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2,
        )
        cv2.putText(
            frame, f"Vehicles: {len(vehicles)}",
            (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1,
        )
        cv2.putText(
            frame, "SYNTHETIC MODE - Press Q to quit",
            (20, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 128, 128), 1,
        )

        cv2.imshow("ML Pipeline Demo (Synthetic)", frame)
        key = cv2.waitKey(33) & 0xFF  # ~30 FPS
        if key == ord("q"):
            break
        elif key == ord("s"):
            _spawn_vehicle(vehicles, next_id, width, height)
            next_id += 1

    cv2.destroyAllWindows()
    print(f"\nFinal: IN={in_count}, OUT={out_count}")


def _spawn_vehicle(vehicles: list, vid: int, width: int, height: int) -> None:
    """Append a new synthetic vehicle to the list."""
    side = "left" if np.random.random() < 0.5 else "right"
    speed = float(np.random.uniform(3, 7))
    if side == "left":
        x: float = -80.0
        direction = 1
    else:
        x = float(width + 10)
        speed = -speed
        direction = -1

    y = float(height // 3 + np.random.randint(20, height // 3 - 40))
    color = (
        int(np.random.randint(100, 255)),
        int(np.random.randint(100, 255)),
        int(np.random.randint(100, 255)),
    )
    vehicles.append({
        "id": vid,
        "x": x, "y": y,
        "w": float(np.random.randint(60, 120)),
        "h": float(np.random.randint(30, 50)),
        "speed": speed,
        "color": color,
        "direction": direction,
        "crossed": False,
    })


# ---------------------------------------------------------------------------
# Real video mode
# ---------------------------------------------------------------------------

def run_video_demo(
    video_path: str,
    publish: bool = False,
    mqtt_host: str = "127.0.0.1",
    mqtt_port: int = 1883,
) -> None:
    """Run demo on a real video file using the full ML pipeline."""
    try:
        from app.detector import Detector
        from app.tracker import ByteTracker
        from app.line_crossing import LineCrossingDetector
        from app.config import get_settings
    except ImportError as exc:
        print(f"Error importing ML modules: {exc}")
        print("Install dependencies first:")
        print("  pip install -r services/ml/requirements.txt")
        sys.exit(1)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: cannot open video {video_path}")
        sys.exit(1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    print("=== ML Pipeline Demo ===")
    print(f"Video: {video_path} ({width}x{height} @ {fps:.1f} FPS)")

    settings = get_settings()
    detector = Detector(
        model_path=settings.ml_model,
        conf=settings.ml_conf,
        iou=settings.ml_iou,
        device=settings.ml_device,
        imgsz=settings.ml_imgsz,
        emergency_hsv=settings.ml_emergency_hsv,
    )
    tracker = ByteTracker(max_age=30)

    # Horizontal crossing line at vertical midpoint.
    # expected_dir=+1 means crossing from side -1 to +1 counts as "in".
    line_p1 = (0.0, float(height // 2))
    line_p2 = (float(width), float(height // 2))
    crossing = LineCrossingDetector(p1=line_p1, p2=line_p2, expected_dir=1)

    in_count = 0
    out_count = 0
    frame_num = 0
    paused = False

    print(f"Crossing line at y={height // 2}")
    print("Press 'q' to quit, SPACE to pause/resume")
    print()

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                # Loop video
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                tracker.reset()
                crossing.reset()
                continue

            frame_num += 1
            detections = detector.infer(frame)
            tracks = tracker.update(detections)
            events = crossing.update(tracks)

            for ev in events:
                if ev.direction == "in":
                    in_count += 1
                    print(f"  [IN]  Track {ev.track_id} ({ev.cls_name}) crossed line")
                else:
                    out_count += 1
                    print(f"  [OUT] Track {ev.track_id} ({ev.cls_name}) crossed line")

            # Draw tracks
            for track in tracks:
                x1, y1, x2, y2 = (int(c) for c in track.bbox)
                color = (0, 0, 255) if track.cls_name == "emergency" else (0, 255, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f"ID:{track.track_id} {track.cls_name} {track.confidence:.2f}"
                cv2.putText(frame, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                cx, cy = track.center
                cv2.circle(frame, (int(cx), int(cy)), 3, color, -1)

            # Crossing line
            cv2.line(frame, (0, height // 2), (width, height // 2), (0, 255, 255), 3)

            # HUD
            cv2.putText(
                frame, f"IN: {in_count}  OUT: {out_count}",
                (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2,
            )
            cv2.putText(
                frame, f"Frame: {frame_num}  Tracks: {len(tracks)}",
                (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1,
            )
            cv2.putText(
                frame, "Press Q to quit, SPACE to pause",
                (20, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 128, 128), 1,
            )

        cv2.imshow("ML Pipeline Demo", frame)
        delay = max(1, int(1000 / fps))
        key = cv2.waitKey(delay) & 0xFF
        if key == ord("q"):
            break
        elif key == ord(" "):
            paused = not paused

    cap.release()
    cv2.destroyAllWindows()
    print(f"\nFinal: IN={in_count}, OUT={out_count}, Frames={frame_num}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ML pipeline demo for Smart Reverse Corridor"
    )
    parser.add_argument("--video", type=str, help="Path to video file")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use synthetic moving rectangles (no video or ML deps needed)",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish crossing events to MQTT (video mode only)",
    )
    parser.add_argument(
        "--mqtt-host",
        default=os.environ.get("MQTT_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=int(os.environ.get("MQTT_PORT", "1883")),
    )
    args = parser.parse_args()

    if not args.video and not args.synthetic:
        print("Error: specify --video <path> or --synthetic")
        parser.print_help()
        sys.exit(1)

    if args.synthetic:
        run_synthetic_demo(
            publish=args.publish,
            mqtt_host=args.mqtt_host,
            mqtt_port=args.mqtt_port,
        )
    else:
        run_video_demo(
            args.video,
            publish=args.publish,
            mqtt_host=args.mqtt_host,
            mqtt_port=args.mqtt_port,
        )


if __name__ == "__main__":
    main()
