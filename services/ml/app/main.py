"""Service entrypoint: spawn one worker per camera."""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
import time
from pathlib import Path

import structlog

from .camera_worker import CameraWorker
from .config import get_settings
from .detector import Detector
from .publisher import MqttPublisher


def _setup_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _load_calibration(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"calibration not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    _setup_logging()
    log = structlog.get_logger("ml-cv")
    settings = get_settings()

    log.info("startup", model=settings.ml_model, device=settings.ml_device)

    calibration = _load_calibration(settings.ml_calibration_path)

    publisher = MqttPublisher(
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_user or None,
        password=settings.mqtt_pass or None,
        client_id=settings.mqtt_client_id,
    )
    publisher.start()

    detector = Detector(
        model_path=settings.ml_model,
        conf=settings.ml_conf,
        iou=settings.ml_iou,
        device=settings.ml_device,
        imgsz=settings.ml_imgsz,
        emergency_hsv=settings.ml_emergency_hsv,
    )
    # Eagerly load to fail-fast if weights are missing.
    _ = detector.model

    stop_event = threading.Event()
    workers: list[CameraWorker] = []
    sources = settings.cameras
    for camera_id, source in sources.items():
        cam_cfg = calibration.get(camera_id)
        if not cam_cfg:
            log.warning("camera.no_calibration", camera=camera_id)
            continue
        line = cam_cfg["line"]  # [[x1,y1],[x2,y2]]
        side = cam_cfg["side"]
        dir_ = cam_cfg["dir"]
        expected_dir = cam_cfg.get("expected_dir")  # +1 / -1 / null
        w = CameraWorker(
            camera_id=camera_id,
            side=side,
            dir_=dir_,
            source=source,
            line=(tuple(line[0]), tuple(line[1])),
            expected_dir=expected_dir,
            detector=detector,
            publisher=publisher,
            loop_video=settings.ml_loop_video,
            heartbeat_interval_s=settings.ml_heartbeat_interval_s,
            stop_event=stop_event,
        )
        workers.append(w)

    if not workers:
        log.error("startup.no_workers")
        publisher.stop()
        return 1

    def _shutdown(signum, frame):  # noqa: ARG001
        log.info("shutdown.signal", signum=signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    for w in workers:
        w.start()

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    finally:
        for w in workers:
            w.stop()
        for w in workers:
            w.join(timeout=5)
        publisher.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
