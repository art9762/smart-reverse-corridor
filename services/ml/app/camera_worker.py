"""Per-camera worker thread.

Owns its own VideoCapture, Detector instance is shared (thread-safe enough
for our use; YOLO inference releases the GIL). Each worker:

1. Reads frames in a loop.
2. Runs detector → tracker → line-crossing.
3. Publishes events + heartbeat via MQTT.
4. On EOF (file source), reset tracker + line state and re-open.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import structlog

from .detector import Detector
from .line_crossing import LineCrossingDetector
from .publisher import MqttPublisher
from .tracker import ByteTracker

log = structlog.get_logger(__name__)


class CameraWorker(threading.Thread):
    """One thread per camera."""

    def __init__(
        self,
        camera_id: str,        # e.g. "A_in"
        side: str,             # "A" / "B"
        dir_: str,             # "in" / "out"
        source: str,           # path to mp4 or RTSP url
        line: tuple[tuple[float, float], tuple[float, float]],
        expected_dir: Optional[int],
        detector: Detector,
        publisher: MqttPublisher,
        loop_video: bool = True,
        heartbeat_interval_s: float = 1.0,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        super().__init__(name=f"cam-{camera_id}", daemon=True)
        self.camera_id = camera_id
        self.side = side
        self.dir_ = dir_
        self.source = source
        self.detector = detector
        self.publisher = publisher
        self.tracker = ByteTracker()
        self.line = LineCrossingDetector(
            p1=tuple(line[0]),
            p2=tuple(line[1]),
            expected_dir=expected_dir,
        )
        self.loop_video = loop_video
        self.heartbeat_interval_s = heartbeat_interval_s
        self.stop_event = stop_event or threading.Event()
        self._fps_ema: float = 0.0

    def stop(self) -> None:
        self.stop_event.set()

    # ---- main loop ----

    def run(self) -> None:  # noqa: C901 - linear flow, clearer top-down
        import cv2  # local import; speeds up unit tests

        log.info("worker.start", camera=self.camera_id, source=self.source)
        cap = self._open(cv2)
        last_hb = 0.0
        last_frame_t = time.time()
        healthy = cap is not None and cap.isOpened()

        while not self.stop_event.is_set():
            frame = None
            if cap is not None and cap.isOpened():
                ok, frame = cap.read()
                if not ok or frame is None:
                    # EOF or read error.
                    if self.loop_video:
                        log.info("worker.loop_reset", camera=self.camera_id)
                        cap.release()
                        self.tracker.reset()
                        self.line.reset()
                        cap = self._open(cv2)
                        healthy = cap is not None and cap.isOpened()
                        continue
                    healthy = False
                    cap.release()
                    cap = None
            else:
                # Try to recover; throttle reconnect attempts.
                time.sleep(1.0)
                cap = self._open(cv2)
                healthy = cap is not None and cap.isOpened()
                if cap is None:
                    self._maybe_heartbeat(last_hb_ref=lambda: last_hb, healthy=False)
                    last_hb = time.time()
                    continue

            if frame is None:
                continue

            # Pipeline.
            try:
                dets = self.detector.infer(frame)
            except Exception:
                log.exception("detector.error", camera=self.camera_id)
                dets = []

            tracks = self.tracker.update(dets)
            events = self.line.update(tracks)
            for ev in events:
                self.publisher.publish_event(
                    side=self.side,
                    dir_=self.dir_,
                    track_id=ev.track_id,
                    cls_name=ev.cls_name,
                    confidence=ev.confidence,
                )

            # FPS EMA.
            now = time.time()
            dt = now - last_frame_t
            last_frame_t = now
            if dt > 0:
                inst = 1.0 / dt
                self._fps_ema = (
                    inst if self._fps_ema == 0 else 0.9 * self._fps_ema + 0.1 * inst
                )

            # Heartbeat.
            if now - last_hb >= self.heartbeat_interval_s:
                self.publisher.publish_heartbeat(
                    side=self.side,
                    dir_=self.dir_,
                    fps=self._fps_ema,
                    healthy=healthy,
                    camera_id=self.camera_id,
                )
                last_hb = now

        if cap is not None:
            cap.release()
        log.info("worker.stop", camera=self.camera_id)

    # ---- helpers ----

    def _open(self, cv2_module):
        try:
            cap = cv2_module.VideoCapture(self.source)
            if not cap.isOpened():
                log.warning("worker.open_failed", camera=self.camera_id, source=self.source)
                return cap  # still return so loop can retry
            return cap
        except Exception:
            log.exception("worker.open_exception", camera=self.camera_id)
            return None

    def _maybe_heartbeat(self, last_hb_ref, healthy: bool) -> None:
        try:
            self.publisher.publish_heartbeat(
                side=self.side,
                dir_=self.dir_,
                fps=0.0,
                healthy=healthy,
                camera_id=self.camera_id,
            )
        except Exception:
            log.warning("heartbeat.publish_failed", camera=self.camera_id)


__all__ = ["CameraWorker"]
