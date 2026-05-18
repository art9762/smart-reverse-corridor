"""MQTT publisher for ml-cv events and heartbeats.

Topics (per docs/MQTT.md):
- corridor/cam/<side>/<dir>/event       qos=1, no retain
- corridor/cam/<side>/<dir>/heartbeat   qos=1, retain=true, ~1 Hz
"""

from __future__ import annotations

import json
import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt
import structlog

log = structlog.get_logger(__name__)


class MqttPublisher:
    """Thread-safe MQTT publisher with auto-reconnect."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: str = "ml-cv",
    ) -> None:
        self.host = host
        self.port = port
        self._lock = threading.Lock()
        # paho-mqtt 2.x: must specify CallbackAPIVersion
        try:
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                clean_session=True,
            )
        except AttributeError:  # paho 1.x fallback
            self._client = mqtt.Client(client_id=client_id, clean_session=True)
        if username:
            self._client.username_pw_set(username, password or "")
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._connected = False

    # ---- lifecycle ----

    def start(self) -> None:
        try:
            self._client.connect_async(self.host, self.port, keepalive=30)
        except Exception:
            log.warning("mqtt.connect_async_failed", host=self.host, port=self.port)
        self._client.loop_start()

    def stop(self) -> None:
        try:
            self._client.disconnect()
        finally:
            self._client.loop_stop()

    # ---- callbacks ----

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        self._connected = True
        log.info("mqtt.connected", host=self.host, port=self.port)

    def _on_disconnect(self, client, userdata, *args, **kwargs):
        self._connected = False
        log.warning("mqtt.disconnected")

    # ---- publish helpers ----

    @staticmethod
    def event_topic(side: str, dir_: str) -> str:
        return f"corridor/cam/{side}/{dir_}/event"

    @staticmethod
    def heartbeat_topic(side: str, dir_: str) -> str:
        return f"corridor/cam/{side}/{dir_}/heartbeat"

    def publish_event(
        self,
        side: str,
        dir_: str,
        track_id: int,
        cls_name: str,
        confidence: float,
        ts: Optional[float] = None,
        plate: Optional[str] = None,
    ) -> None:
        payload = {
            "ts": ts if ts is not None else time.time(),
            "track_id": int(track_id),
            "class": cls_name,
            "side": side,
            "dir": dir_,
            "confidence": round(float(confidence), 4),
            "plate": plate,
        }
        self._publish(self.event_topic(side, dir_), payload, qos=1, retain=False)

    def publish_heartbeat(
        self,
        side: str,
        dir_: str,
        fps: float,
        healthy: bool,
        camera_id: Optional[str] = None,
        ts: Optional[float] = None,
    ) -> None:
        payload = {
            "ts": ts if ts is not None else time.time(),
            "camera_id": camera_id or f"{side}_{dir_}",
            "fps": round(float(fps), 2),
            "healthy": bool(healthy),
        }
        self._publish(
            self.heartbeat_topic(side, dir_), payload, qos=1, retain=True
        )

    def _publish(self, topic: str, payload: dict, qos: int, retain: bool) -> None:
        data = json.dumps(payload, separators=(",", ":"))
        with self._lock:
            try:
                info = self._client.publish(topic, data, qos=qos, retain=retain)
                # Don't block forever on disconnected broker.
                if hasattr(info, "wait_for_publish"):
                    try:
                        info.wait_for_publish(timeout=1.0)
                    except Exception:
                        pass
            except Exception:
                log.warning("mqtt.publish_failed", topic=topic)


__all__ = ["MqttPublisher"]
