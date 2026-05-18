"""Integration-test fixtures.

Goals:
  * Start an MQTT broker (mosquitto) so the controller and tests can talk.
  * Start the controller service so we exercise the real wiring.
  * Hand the test a clean MQTT client + HTTP client + WS URL.

We try testcontainers-python first (preferred). If it isn't available or
Docker isn't reachable, we fall back to ``docker compose up -d mosquitto
controller`` driven by ``infra/docker-compose.yml`` (see RISKS.md).

All fixtures are session-scoped where it's safe; per-test cleanup is done in
``mqtt_client`` / ``reset_state``.
"""
from __future__ import annotations

import contextlib
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx
import paho.mqtt.client as mqtt
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "infra" / "docker-compose.yml"

MQTT_HOST_ENV = "TEST_MQTT_HOST"
MQTT_PORT_ENV = "TEST_MQTT_PORT"
CONTROLLER_URL_ENV = "TEST_CONTROLLER_URL"
CONTROLLER_WS_ENV = "TEST_CONTROLLER_WS"

DEFAULT_HTTP_TIMEOUT = 5.0
BOOT_TIMEOUT_S = 30.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_tcp(host: str, port: int, timeout: float = BOOT_TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError as exc:  # noqa: PERF203
            last_err = exc
            time.sleep(0.25)
    raise TimeoutError(f"timed out waiting for {host}:{port}: {last_err}")


def _wait_http_ok(url: str, timeout: float = BOOT_TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=1.5)
            if r.status_code < 500:
                return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(0.5)
    raise TimeoutError(f"controller {url} not ready: {last_err}")


# ---------------------------------------------------------------------------
# Broker fixture: testcontainers preferred, docker-compose fallback
# ---------------------------------------------------------------------------

@dataclass
class _BrokerHandle:
    host: str
    port: int
    stop: Callable[[], None]


def _try_testcontainers_broker() -> _BrokerHandle | None:
    try:
        from testcontainers.core.container import DockerContainer  # type: ignore
        from testcontainers.core.waiting_utils import wait_for_logs  # type: ignore
    except Exception:
        return None

    cfg = (
        "listener 1883 0.0.0.0\n"
        "allow_anonymous true\n"
        "persistence false\n"
    )
    cfg_dir = Path("/tmp") / f"mosq-{uuid.uuid4().hex[:8]}"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "mosquitto.conf").write_text(cfg)

    try:
        container = (
            DockerContainer("eclipse-mosquitto:2.0")
            .with_exposed_ports(1883)
            .with_volume_mapping(str(cfg_dir), "/mosquitto/config", "ro")
        )
        container.start()
        wait_for_logs(container, "mosquitto version", timeout=20)
    except Exception as exc:  # docker not reachable / image pull failed
        sys.stderr.write(f"[conftest] testcontainers unavailable: {exc}\n")
        with contextlib.suppress(Exception):
            shutil.rmtree(cfg_dir, ignore_errors=True)
        return None

    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(1883))

    def _stop() -> None:
        with contextlib.suppress(Exception):
            container.stop()
        shutil.rmtree(cfg_dir, ignore_errors=True)

    return _BrokerHandle(host=host, port=port, stop=_stop)


def _try_compose_broker() -> _BrokerHandle | None:
    if not COMPOSE_FILE.exists():
        return None
    if not shutil.which("docker"):
        return None
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "mosquitto"],
            check=True,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[conftest] docker compose mosquitto failed: {exc}\n")
        return None

    host = os.environ.get(MQTT_HOST_ENV, "127.0.0.1")
    port = int(os.environ.get(MQTT_PORT_ENV, "1883"))
    try:
        _wait_tcp(host, port, timeout=BOOT_TIMEOUT_S)
    except TimeoutError as exc:
        sys.stderr.write(f"[conftest] mosquitto not reachable: {exc}\n")
        return None

    def _stop() -> None:
        with contextlib.suppress(Exception):
            subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "stop", "mosquitto"],
                cwd=str(REPO_ROOT),
                check=False,
                timeout=30,
            )

    return _BrokerHandle(host=host, port=port, stop=_stop)


@pytest.fixture(scope="session")
def mqtt_broker() -> Iterator[_BrokerHandle]:
    # If the operator already pointed us at an external broker, just use it.
    env_host = os.environ.get(MQTT_HOST_ENV)
    env_port = os.environ.get(MQTT_PORT_ENV)
    if env_host and env_port:
        _wait_tcp(env_host, int(env_port), timeout=BOOT_TIMEOUT_S)
        yield _BrokerHandle(env_host, int(env_port), stop=lambda: None)
        return

    handle = _try_testcontainers_broker() or _try_compose_broker()
    if handle is None:
        pytest.skip(
            "No MQTT broker available (testcontainers + docker compose both "
            "unavailable). Set TEST_MQTT_HOST/TEST_MQTT_PORT to use an external one."
        )
        return
    try:
        yield handle
    finally:
        handle.stop()


# ---------------------------------------------------------------------------
# Controller fixture: subprocess preferred, docker-compose fallback
# ---------------------------------------------------------------------------

@dataclass
class _ControllerHandle:
    base_url: str
    ws_url: str
    stop: Callable[[], None]


def _try_subprocess_controller(broker: _BrokerHandle) -> _ControllerHandle | None:
    controller_dir = REPO_ROOT / "services" / "controller"
    main_py = controller_dir / "main.py"
    if not main_py.exists():
        return None

    port = 18080
    env = os.environ.copy()
    env.update(
        {
            "MQTT_HOST": broker.host,
            "MQTT_PORT": str(broker.port),
            "CONTROLLER_HTTP_PORT": str(port),
            "CONTROLLER_LOG_LEVEL": "INFO",
            "CONTROLLER_MODE": "adaptive",
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-u", str(main_py)],
        cwd=str(controller_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    ws = f"ws://127.0.0.1:{port}/ws"
    try:
        _wait_http_ok(f"{base}/state", timeout=BOOT_TIMEOUT_S)
    except TimeoutError as exc:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)
        sys.stderr.write(f"[conftest] subprocess controller failed: {exc}\n")
        return None

    def _stop() -> None:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)
        if proc.poll() is None:
            proc.kill()

    return _ControllerHandle(base_url=base, ws_url=ws, stop=_stop)


def _try_compose_controller(broker: _BrokerHandle) -> _ControllerHandle | None:
    if not COMPOSE_FILE.exists() or not shutil.which("docker"):
        return None
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "controller"],
            check=True,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[conftest] docker compose controller failed: {exc}\n")
        return None

    base = os.environ.get(CONTROLLER_URL_ENV, "http://127.0.0.1:8080")
    ws = os.environ.get(CONTROLLER_WS_ENV, base.replace("http", "ws") + "/ws")
    try:
        _wait_http_ok(f"{base}/state", timeout=BOOT_TIMEOUT_S)
    except TimeoutError as exc:
        sys.stderr.write(f"[conftest] controller not ready: {exc}\n")
        return None

    def _stop() -> None:
        with contextlib.suppress(Exception):
            subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "stop", "controller"],
                cwd=str(REPO_ROOT),
                check=False,
                timeout=30,
            )

    return _ControllerHandle(base_url=base, ws_url=ws, stop=_stop)


@pytest.fixture(scope="session")
def controller(mqtt_broker: _BrokerHandle) -> Iterator[_ControllerHandle]:
    env_url = os.environ.get(CONTROLLER_URL_ENV)
    if env_url:
        ws = os.environ.get(CONTROLLER_WS_ENV, env_url.replace("http", "ws") + "/ws")
        _wait_http_ok(f"{env_url}/state", timeout=BOOT_TIMEOUT_S)
        yield _ControllerHandle(env_url, ws, stop=lambda: None)
        return

    handle = (
        _try_subprocess_controller(mqtt_broker)
        or _try_compose_controller(mqtt_broker)
    )
    if handle is None:
        pytest.skip(
            "Controller service not runnable in this environment. Build it first "
            "or set TEST_CONTROLLER_URL."
        )
        return
    try:
        yield handle
    finally:
        handle.stop()


# ---------------------------------------------------------------------------
# MQTT client + HTTP client fixtures
# ---------------------------------------------------------------------------

class MqttBus:
    """Thin wrapper around paho-mqtt with helpers for tests.

    Each test gets its own client so subscriptions don't bleed across tests.
    """

    def __init__(self, host: str, port: int) -> None:
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"itest-{uuid.uuid4().hex[:8]}",
        )
        self._messages: "queue.Queue[tuple[str, dict[str, Any]]]" = queue.Queue()
        self._client.on_message = self._on_message
        self._client.connect(host, port, keepalive=30)
        self._client.loop_start()

    def _on_message(self, _c: Any, _u: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:  # noqa: BLE001
            payload = {"_raw": msg.payload.decode("utf-8", errors="replace")}
        self._messages.put((msg.topic, payload))

    def subscribe(self, topic: str, qos: int = 1) -> None:
        self._client.subscribe(topic, qos=qos)

    def publish(self, topic: str, payload: dict[str, Any], qos: int = 1, retain: bool = False) -> None:
        info = self._client.publish(topic, json.dumps(payload), qos=qos, retain=retain)
        info.wait_for_publish(timeout=2)

    def wait_for(
        self,
        predicate: Callable[[str, dict[str, Any]], bool],
        timeout: float = 10.0,
    ) -> tuple[str, dict[str, Any]]:
        deadline = time.monotonic() + timeout
        seen: list[tuple[str, dict[str, Any]]] = []
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                topic, payload = self._messages.get(timeout=remaining)
            except queue.Empty:
                break
            seen.append((topic, payload))
            if predicate(topic, payload):
                return topic, payload
        raise AssertionError(
            f"predicate not met within {timeout}s. Seen messages: {seen[-10:]}"
        )

    def drain(self, max_items: int = 1024) -> list[tuple[str, dict[str, Any]]]:
        out: list[tuple[str, dict[str, Any]]] = []
        for _ in range(max_items):
            try:
                out.append(self._messages.get_nowait())
            except queue.Empty:
                break
        return out

    def close(self) -> None:
        self._client.loop_stop()
        with contextlib.suppress(Exception):
            self._client.disconnect()


@pytest.fixture
def mqtt_client(mqtt_broker: _BrokerHandle) -> Iterator[MqttBus]:
    bus = MqttBus(mqtt_broker.host, mqtt_broker.port)
    bus.subscribe("corridor/#", qos=1)
    try:
        yield bus
    finally:
        bus.close()


@pytest.fixture
def http(controller: _ControllerHandle) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=controller.base_url, timeout=DEFAULT_HTTP_TIMEOUT) as c:
        yield c


@pytest.fixture
def ws_url(controller: _ControllerHandle) -> str:
    return controller.ws_url


# ---------------------------------------------------------------------------
# Per-test reset hook
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_state(http: httpx.Client) -> Iterator[None]:
    """Best-effort reset between tests.

    The controller is expected to expose POST /test/reset for integration mode.
    If it doesn't, we soldier on; tests should be tolerant of warm state via
    explicit waits on phase transitions.
    """
    with contextlib.suppress(Exception):
        http.post("/test/reset")
    yield


# ---------------------------------------------------------------------------
# Convenience helpers used by multiple tests
# ---------------------------------------------------------------------------

@dataclass
class _CamPublisher:
    bus: MqttBus
    next_track: int = 1

    def event(
        self,
        side: str,
        direction: str,
        cls: str = "car",
        confidence: float = 0.95,
        track_id: int | None = None,
        ts: float | None = None,
    ) -> int:
        tid = track_id if track_id is not None else self.next_track
        if track_id is None:
            self.next_track += 1
        payload = {
            "ts": ts if ts is not None else time.time(),
            "track_id": tid,
            "class": cls,
            "side": side,
            "dir": direction,
            "confidence": confidence,
            "plate": None,
        }
        self.bus.publish(f"corridor/cam/{side}/{direction}/event", payload, qos=1)
        return tid

    def heartbeat(self, side: str, direction: str, healthy: bool = True, fps: float = 24.7) -> None:
        payload = {
            "ts": time.time(),
            "camera_id": f"{side}_{direction}",
            "fps": fps,
            "healthy": healthy,
        }
        self.bus.publish(
            f"corridor/cam/{side}/{direction}/heartbeat",
            payload,
            qos=1,
            retain=True,
        )

    def heartbeat_all(self, healthy: bool = True) -> None:
        for side in ("A", "B"):
            for direction in ("in", "out"):
                self.heartbeat(side, direction, healthy=healthy)


@pytest.fixture
def cam(mqtt_client: MqttBus) -> _CamPublisher:
    pub = _CamPublisher(bus=mqtt_client)
    # Establish health so the controller doesn't immediately fall back.
    pub.heartbeat_all(healthy=True)
    return pub
