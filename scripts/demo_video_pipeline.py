#!/usr/bin/env python3
"""Full ML pipeline demo: YOLOv8 vehicle detection on highway video.

Processes a traffic video through:
  1. YOLOv8n detection (car, motorcycle, bus, truck)
  2. ByteTrack multi-object tracking
  3. Virtual line-crossing counting
  4. MQTT event publishing (optional, for integration with controller)
  5. Real-time OpenCV visualization with HUD

Usage:
    # Basic visualization (just video + detection overlay):
    python scripts/demo_video_pipeline.py --video "4K Video of Highway Traffic!.mp4"

    # With MQTT publishing (needs mosquitto running on localhost:1883):
    python scripts/demo_video_pipeline.py --video "4K Video of Highway Traffic!.mp4" --publish

    # Headless mode (no GUI, prints events to console):
    python scripts/demo_video_pipeline.py --video "4K Video of Highway Traffic!.mp4" --headless

    # Custom model/confidence:
    python scripts/demo_video_pipeline.py --video input.mp4 --conf 0.4 --device cuda:0
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ml"))

from app.detector import Detector, Detection
from app.tracker import ByteTracker, Track
from app.line_crossing import LineCrossingDetector, CrossingEvent


class MqttBridge:
    """Lightweight MQTT bridge for demo — publishes crossing events to controller."""

    def __init__(self, host: str, port: int, side: str = "A", dir_: str = "in"):
        self.side = side
        self.dir_ = dir_
        self._client = None
        try:
            import paho.mqtt.client as mqtt
            try:
                self._client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id="demo-ml-pipeline",
                )
            except AttributeError:
                self._client = mqtt.Client(client_id="demo-ml-pipeline")
            self._client.connect(host, port, keepalive=30)
            self._client.loop_start()
            print(f"[MQTT] Connected to {host}:{port}")
        except Exception as e:
            print(f"[MQTT] Connection failed: {e} — events will only print to console")
            self._client = None

    def publish_crossing(self, track_id: int, cls_name: str, confidence: float, direction: str):
        payload = {
            "ts": time.time(),
            "track_id": track_id,
            "class": cls_name,
            "side": self.side,
            "dir": direction,
            "confidence": round(confidence, 4),
            "plate": None,
        }
        topic = f"corridor/cam/{self.side}/{self.dir_}/event"
        if self._client:
            self._client.publish(topic, json.dumps(payload), qos=1)

    def publish_heartbeat(self, fps: float, healthy: bool):
        payload = {
            "ts": time.time(),
            "camera_id": f"{self.side}_{self.dir_}",
            "fps": round(fps, 2),
            "healthy": healthy,
        }
        topic = f"corridor/cam/{self.side}/{self.dir_}/heartbeat"
        if self._client:
            self._client.publish(topic, json.dumps(payload), qos=1, retain=True)

    def stop(self):
        if self._client:
            self._client.disconnect()
            self._client.loop_stop()


def draw_detections(frame: np.ndarray, tracks: list, line_y: int,
                    in_count: int, out_count: int, fps: float, frame_num: int):
    """Draw tracking boxes, crossing line, and HUD overlay."""
    h, w = frame.shape[:2]

    cv2.line(frame, (0, line_y), (w, line_y), (0, 255, 255), 3)
    cv2.putText(frame, "CROSSING LINE", (w // 2 - 80, line_y - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    for track in tracks:
        x1, y1, x2, y2 = (int(c) for c in track.bbox)
        is_emergency = track.cls_name == "emergency"
        color = (0, 0, 255) if is_emergency else _class_color(track.cls_name)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label = f"#{track.track_id} {track.cls_name} {track.confidence:.0%}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        cx, cy = track.center
        cv2.circle(frame, (int(cx), int(cy)), 4, color, -1)

    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (300, 130), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    cv2.putText(frame, f"IN: {in_count}", (20, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
    cv2.putText(frame, f"OUT: {out_count}", (160, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 128, 255), 2)
    cv2.putText(frame, f"FPS: {fps:.1f}  Tracks: {len(tracks)}", (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    cv2.putText(frame, f"Frame: {frame_num}", (20, 110),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

    cv2.putText(frame, "Smart Reverse Corridor | YOLOv8 + ByteTrack",
                (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 128, 128), 1)

    return frame


def _class_color(cls_name: str) -> tuple:
    colors = {
        "car": (0, 255, 0),
        "motorcycle": (255, 0, 255),
        "bus": (255, 165, 0),
        "truck": (0, 165, 255),
        "emergency": (0, 0, 255),
    }
    return colors.get(cls_name, (255, 255, 255))


def run_pipeline(args):
    video_path = args.video
    if not Path(video_path).exists():
        print(f"Error: video not found at '{video_path}'")
        sys.exit(1)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: cannot open video '{video_path}'")
        sys.exit(1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print("=" * 60)
    print("  Smart Reverse Corridor — ML Pipeline Demo")
    print("=" * 60)
    print(f"  Video:      {video_path}")
    print(f"  Resolution: {width}x{height} @ {video_fps:.1f} FPS")
    print(f"  Frames:     {total_frames}")
    print(f"  Model:      YOLOv8n (conf={args.conf}, device={args.device})")
    print(f"  MQTT:       {'enabled' if args.publish else 'disabled'}")
    print("=" * 60)

    detector = Detector(
        model_path=args.model,
        conf=args.conf,
        iou=args.iou,
        device=args.device,
        imgsz=args.imgsz,
        emergency_hsv=args.emergency_hsv,
    )
    # Force model load at startup
    print("Loading YOLOv8 model...")
    _ = detector.model
    print("Model loaded.")

    tracker = ByteTracker(iou_threshold=0.3, max_age=30, high_conf=0.5)

    line_y = height // 2
    line_p1 = (0.0, float(line_y))
    line_p2 = (float(width), float(line_y))
    crossing = LineCrossingDetector(p1=line_p1, p2=line_p2, expected_dir=1)

    mqtt_bridge = None
    if args.publish:
        mqtt_bridge = MqttBridge(args.mqtt_host, args.mqtt_port, side="A", dir_="in")

    in_count = 0
    out_count = 0
    frame_num = 0
    fps_ema = 0.0
    last_t = time.time()
    paused = False

    if not args.headless:
        print("\nControls: Q=quit, SPACE=pause, R=reset counters, L=move line up/down")

    try:
        while True:
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    if args.loop:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        tracker.reset()
                        crossing.reset()
                        print(f"\n[LOOP] Restarting video. Total: IN={in_count}, OUT={out_count}")
                        continue
                    else:
                        break

                frame_num += 1

                # Skip frames for speed on high-res video
                if args.skip > 1 and frame_num % args.skip != 0:
                    continue

                # Resize for faster inference if video is 4K
                if width > 1920:
                    scale = 1920.0 / width
                    proc_frame = cv2.resize(frame, (1920, int(height * scale)))
                    proc_h = int(height * scale)
                    proc_line_y = int(line_y * scale)
                else:
                    proc_frame = frame
                    scale = 1.0
                    proc_h = height
                    proc_line_y = line_y

                detections = detector.infer(proc_frame)

                # Scale bboxes back to original resolution
                if scale != 1.0:
                    for d in detections:
                        x1, y1, x2, y2 = d.bbox
                        d.bbox = (x1 / scale, y1 / scale, x2 / scale, y2 / scale)

                tracks = tracker.update(detections)

                # Update line crossing with scaled line
                crossing_scaled = LineCrossingDetector(
                    p1=(0.0, float(line_y)),
                    p2=(float(width), float(line_y)),
                    expected_dir=1,
                )
                crossing_scaled._last_side = crossing._last_side
                events = crossing.update(tracks)

                for ev in events:
                    if ev.direction == "in":
                        in_count += 1
                    else:
                        out_count += 1

                    print(f"  [{ev.direction.upper():3s}] Track #{ev.track_id} "
                          f"({ev.cls_name}, {ev.confidence:.0%}) crossed line")

                    if mqtt_bridge:
                        mqtt_bridge.publish_crossing(
                            track_id=ev.track_id,
                            cls_name=ev.cls_name,
                            confidence=ev.confidence,
                            direction=ev.direction,
                        )

                # FPS
                now = time.time()
                dt = now - last_t
                last_t = now
                if dt > 0:
                    inst_fps = 1.0 / dt
                    fps_ema = inst_fps if fps_ema == 0 else 0.9 * fps_ema + 0.1 * inst_fps

                # Heartbeat every ~1s
                if mqtt_bridge and frame_num % int(video_fps) == 0:
                    mqtt_bridge.publish_heartbeat(fps=fps_ema, healthy=True)

                if not args.headless:
                    vis = draw_detections(frame, tracks, line_y,
                                         in_count, out_count, fps_ema, frame_num)
                    # Resize display if 4K
                    if width > 1920:
                        vis = cv2.resize(vis, (1920, int(height * (1920 / width))))
                    cv2.imshow("Smart Reverse Corridor - ML Demo", vis)

            if not args.headless:
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                elif key == ord(" "):
                    paused = not paused
                    print(f"{'PAUSED' if paused else 'RESUMED'}")
                elif key == ord("r"):
                    in_count = 0
                    out_count = 0
                    print("[RESET] Counters cleared")
            else:
                if frame_num % 100 == 0:
                    print(f"  [PROGRESS] Frame {frame_num}/{total_frames} | "
                          f"IN={in_count} OUT={out_count} | FPS={fps_ema:.1f}")

    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
    finally:
        cap.release()
        if not args.headless:
            cv2.destroyAllWindows()
        if mqtt_bridge:
            mqtt_bridge.stop()

    print("\n" + "=" * 60)
    print(f"  Results: IN={in_count}  OUT={out_count}  Frames={frame_num}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Smart Reverse Corridor — ML Video Pipeline Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/demo_video_pipeline.py --video "4K Video of Highway Traffic!.mp4"
  python scripts/demo_video_pipeline.py --video input.mp4 --publish --mqtt-host localhost
  python scripts/demo_video_pipeline.py --video input.mp4 --headless --skip 3
        """,
    )
    parser.add_argument("--video", required=True, help="Path to input video file")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLOv8 model path (default: yolov8n.pt)")
    parser.add_argument("--conf", type=float, default=0.35, help="Detection confidence threshold")
    parser.add_argument("--iou", type=float, default=0.5, help="NMS IoU threshold")
    parser.add_argument("--device", default="cpu", help="Inference device (cpu, cuda:0, mps)")
    parser.add_argument("--imgsz", type=int, default=640, help="YOLO input image size")
    parser.add_argument("--emergency-hsv", action="store_true", help="Enable emergency vehicle HSV detection")
    parser.add_argument("--publish", action="store_true", help="Publish events via MQTT")
    parser.add_argument("--mqtt-host", default="127.0.0.1", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--headless", action="store_true", help="No GUI, console output only")
    parser.add_argument("--loop", action="store_true", help="Loop video on EOF")
    parser.add_argument("--skip", type=int, default=1, help="Process every Nth frame (speed up)")
    args = parser.parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()
