"""MQTT client wrapper.

The MQTT client runs in its own thread (paho's loop). Incoming messages
are pushed to an asyncio.Queue so the asyncio loop can consume them
safely.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

import structlog

from .config import Settings

log = structlog.get_logger("mqtt")

# Topics
TOPIC_CAM_PREFIX = "corridor/cam"
TOPIC_CMD_PREFIX = "corridor/cmd"
TOPIC_STATE = "corridor/state"
TOPIC_METRICS_TICK = "corridor/metrics/tick"
TOPIC_ALERTS = "corridor/alerts"


@dataclass
class IncomingMessage:
    topic: str
    payload: Dict[str, Any]
    raw: bytes
    received_at: float


class MQTTClient:
    """Wraps paho-mqtt client with an asyncio bridge.

    Submitted messages from MQTT thread are placed into `inbox` (an
    asyncio.Queue) using `loop.call_soon_threadsafe`.
    """

    def __init__(
        self,
        settings: Settings,
        loop: asyncio.AbstractEventLoop,
        inbox: "asyncio.Queue[IncomingMessage]",
    ) -> None:
        self.settings = settings
        self.loop = loop
        self.inbox = inbox
        self._client = None
        self._connected = threading.Event()
        self._stopped = threading.Event()

        # Camera heartbeat tracking (camera_id -> last hb monotonic)
        self._heartbeats: Dict[str, float] = {}
        self._hb_lock = threading.RLock()

        self._connect_paho()

    def _connect_paho(self) -> None:
        import paho.mqtt.client as mqtt

        client_id = f"{self.settings.mqtt_client_id}-{int(time.time())}"
        # paho-mqtt 2.x defaults to MQTTv5; use VERSION1 callback API for stability
        try:
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )
        except AttributeError:
            # paho-mqtt < 2.0 fallback
            self._client = mqtt.Client(client_id=client_id)

        if self.settings.mqtt_user:
            self._client.username_pw_set(
                self.settings.mqtt_user, self.settings.mqtt_pass or ""
            )

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        try:
            self._client.connect_async(
                self.settings.mqtt_host, self.settings.mqtt_port, keepalive=30
            )
        except Exception as exc:
            log.warning("mqtt.connect_failed", error=str(exc))
        self._client.loop_start()
        log.info(
            "mqtt.started",
            host=self.settings.mqtt_host,
            port=self.settings.mqtt_port,
        )

    def stop(self) -> None:
        self._stopped.set()
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------
    # Paho callbacks (run on the MQTT thread)
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        # paho 2.x signature; older versions pass `rc` only
        rc = reason_code if isinstance(reason_code, int) else getattr(
            reason_code, "value", 0
        )
        if rc == 0:
            self._connected.set()
            log.info("mqtt.connected")
            client.subscribe(f"{TOPIC_CAM_PREFIX}/#", qos=1)
            client.subscribe(f"{TOPIC_CMD_PREFIX}/#", qos=1)
        else:
            log.warning("mqtt.connect_rc", rc=rc)

    def _on_disconnect(self, client, userdata, *args, **kwargs):
        self._connected.clear()
        log.warning("mqtt.disconnected")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = {"_raw": msg.payload[:500].decode("utf-8", errors="replace")}

        # Update heartbeat tracking eagerly on the MQTT thread.
        if msg.topic.startswith(f"{TOPIC_CAM_PREFIX}/") and msg.topic.endswith(
            "/heartbeat"
        ):
            cam_id = self._cam_id_from_topic(msg.topic)
            if cam_id:
                with self._hb_lock:
                    self._heartbeats[cam_id] = time.monotonic()

        item = IncomingMessage(
            topic=msg.topic,
            payload=payload,
            raw=msg.payload,
            received_at=time.time(),
        )
        try:
            self.loop.call_soon_threadsafe(self.inbox.put_nowait, item)
        except RuntimeError:  # pragma: no cover - loop closing
            pass
        except asyncio.QueueFull:  # pragma: no cover - queue is unbounded by default
            log.warning("mqtt.inbox_full", topic=msg.topic)

    @staticmethod
    def _cam_id_from_topic(topic: str) -> Optional[str]:
        # corridor/cam/<side>/<dir>/heartbeat
        parts = topic.split("/")
        if len(parts) >= 4:
            return f"{parts[2]}_{parts[3]}"
        return None

    # ------------------------------------------------------------------
    # Publishing helpers
    # ------------------------------------------------------------------

    def publish(self, topic: str, payload: Dict[str, Any], retain: bool = False,
                qos: int = 1) -> None:
        if self._client is None:
            return
        try:
            data = json.dumps(payload, default=str).encode("utf-8")
            self._client.publish(topic, data, qos=qos, retain=retain)
        except Exception as exc:  # pragma: no cover
            log.warning("mqtt.publish_failed", topic=topic, error=str(exc))

    def publish_state(self, payload: Dict[str, Any]) -> None:
        self.publish(TOPIC_STATE, payload, retain=True)

    def publish_metrics(self, payload: Dict[str, Any]) -> None:
        self.publish(TOPIC_METRICS_TICK, payload, retain=False)

    def publish_alert(self, payload: Dict[str, Any]) -> None:
        self.publish(TOPIC_ALERTS, payload, retain=False)

    # ------------------------------------------------------------------
    # Heartbeat watchdog
    # ------------------------------------------------------------------

    def camera_health(self, timeout_s: float) -> Dict[str, bool]:
        """Return {camera_id: healthy} based on last heartbeat."""
        now = time.monotonic()
        ids = ["A_in", "A_out", "B_in", "B_out"]
        with self._hb_lock:
            return {
                cid: (cid in self._heartbeats and (now - self._heartbeats[cid]) <= timeout_s)
                for cid in ids
            }

    def lost_cameras(self, timeout_s: float) -> Dict[str, float]:
        now = time.monotonic()
        with self._hb_lock:
            out: Dict[str, float] = {}
            for cid in ("A_in", "A_out", "B_in", "B_out"):
                last = self._heartbeats.get(cid)
                if last is None:
                    out[cid] = float("inf")
                elif now - last > timeout_s:
                    out[cid] = now - last
            return out


def parse_cam_topic(topic: str) -> Optional[Dict[str, str]]:
    """Parse `corridor/cam/<side>/<dir>/event|heartbeat` into parts."""
    parts = topic.split("/")
    if len(parts) != 5 or parts[0] != "corridor" or parts[1] != "cam":
        return None
    return {"side": parts[2], "dir": parts[3], "kind": parts[4]}


def parse_cmd_topic(topic: str) -> Optional[str]:
    """Return the command name from `corridor/cmd/<name>` or None."""
    parts = topic.split("/")
    if len(parts) >= 3 and parts[0] == "corridor" and parts[1] == "cmd":
        return parts[2]
    return None
