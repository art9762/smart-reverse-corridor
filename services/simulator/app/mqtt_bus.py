"""MQTT bridge — wraps paho-mqtt for the simulator.

Tiny indirection so tests can swap a `_NoopBus` in without touching the rest
of the code. The bridge exposes a single `publish(topic, payload, qos, retain)`
method that matches the signature expected by `cameras.CameraBus`.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)


class _NoopBus:
    """Drop-everything bus, used in headless tests / when host=='-'."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict, int, bool]] = []
        self._handlers: dict[str, list[Callable[[dict], None]]] = {}

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def publish(self, topic: str, payload: dict, qos: int = 1, retain: bool = False) -> None:
        self.published.append((topic, payload, qos, retain))

    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    def deliver(self, topic: str, payload: dict) -> None:
        """Test helper: fan-out a fake incoming message."""
        for h in self._handlers.get(topic, []):
            h(payload)


class MqttBus:
    """Real MQTT bus backed by paho-mqtt."""

    def __init__(self, host: str, port: int, client_id: str, user: str = "", password: str = "") -> None:
        import paho.mqtt.client as mqtt

        self._mqtt = mqtt
        self._client = mqtt.Client(client_id=client_id, clean_session=True)
        if user:
            self._client.username_pw_set(user, password)
        self._client.on_message = self._on_message
        self._client.on_connect = self._on_connect
        self._handlers: dict[str, list[Callable[[dict], None]]] = {}
        self._lock = threading.Lock()
        self.host = host
        self.port = port

    # ---------------------------------------------------------- lifecycle
    def connect(self) -> None:
        log.info("mqtt: connecting to %s:%s", self.host, self.port)
        self._client.connect(self.host, self.port, keepalive=30)
        self._client.loop_start()

    def disconnect(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # noqa: BLE001
            log.exception("mqtt: disconnect failed")

    # ------------------------------------------------------------- pub/sub
    def publish(self, topic: str, payload: dict, qos: int = 1, retain: bool = False) -> None:
        body = json.dumps(payload, separators=(",", ":"))
        self._client.publish(topic, body, qos=qos, retain=retain)

    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None:
        with self._lock:
            self._handlers.setdefault(topic, []).append(handler)
        self._client.subscribe(topic, qos=1)

    # ------------------------------------------------------------- callbacks
    def _on_connect(self, client, userdata, flags, rc):  # noqa: ANN001
        log.info("mqtt: connected rc=%s", rc)
        with self._lock:
            for topic in self._handlers:
                client.subscribe(topic, qos=1)

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            log.exception("mqtt: bad payload on %s", msg.topic)
            return
        for handler in self._handlers.get(msg.topic, []):
            try:
                handler(payload)
            except Exception:  # noqa: BLE001
                log.exception("mqtt: handler for %s raised", msg.topic)


__all__ = ["MqttBus", "_NoopBus"]
