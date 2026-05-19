#!/usr/bin/env python3
"""Benchmark runner for baseline vs adaptive controllers.

Reads scenarios from ``services/simulator/scenarios/`` (or a YAML/JSON file
you pass on the command line), drives the running stack via MQTT, collects
metric ticks, and writes per-mode CSV files into ``runs/<timestamp>/``.

Usage
-----

.. code-block:: bash

    # Default: 5 minutes per mode on the asymmetric scenario.
    python scripts/bench.py --duration 300 --scenario asymmetric

    # Multiple scenarios, custom output dir.
    python scripts/bench.py --scenario symmetric --scenario asymmetric \
        --duration 180 --out runs/

The controller and an MQTT broker must already be running. Configure the
broker via ``--mqtt-host`` / ``--mqtt-port`` or env ``MQTT_HOST``/``MQTT_PORT``.
Controller HTTP via ``--controller-url`` / env ``CONTROLLER_URL``.

This script does **not** start any services. Use ``make demo`` for that.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import queue
import random
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "paho-mqtt is required (pip install paho-mqtt)"
    ) from exc

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise SystemExit("httpx is required (pip install httpx)") from exc

LOG = logging.getLogger("bench")

METRIC_FIELDS = [
    "ts",
    "mode",
    "scenario",
    "phase",
    "throughput_A",
    "throughput_B",
    "queue_A",
    "queue_B",
    "avg_delay_A",
    "avg_delay_B",
    "max_queue_today_A",
    "max_queue_today_B",
]


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    name: str
    rate_a: float  # arrivals per second from A side
    rate_b: float
    truck_prob: float = 0.0  # chance an arrival is a truck
    description: str = ""


BUILTIN_SCENARIOS: dict[str, Scenario] = {
    "symmetric": Scenario("symmetric", 1.0, 1.0, 0.05, "Even traffic both ways"),
    "asymmetric": Scenario("asymmetric", 1.5, 0.4, 0.05, "Rush hour from A"),
    "truck-heavy": Scenario("truck-heavy", 0.8, 0.8, 0.30, "Long vehicles dominate"),
    "low-load": Scenario("low-load", 0.2, 0.2, 0.0, "Off-peak"),
}


def load_scenarios(names: Iterable[str], scenarios_file: Path | None) -> list[Scenario]:
    if scenarios_file and scenarios_file.exists():
        try:
            data = json.loads(scenarios_file.read_text())
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"failed to read {scenarios_file}: {exc}")
        loaded = {
            row["name"]: Scenario(
                name=row["name"],
                rate_a=float(row["rate_a"]),
                rate_b=float(row["rate_b"]),
                truck_prob=float(row.get("truck_prob", 0)),
                description=str(row.get("description", "")),
            )
            for row in data
        }
    else:
        loaded = dict(BUILTIN_SCENARIOS)

    out: list[Scenario] = []
    for n in names:
        if n not in loaded:
            raise SystemExit(f"unknown scenario: {n}. Have: {sorted(loaded)}")
        out.append(loaded[n])
    return out


# ---------------------------------------------------------------------------
# MQTT helper
# ---------------------------------------------------------------------------

class Bus:
    def __init__(self, host: str, port: int) -> None:
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=f"bench-{os.getpid()}"
        )
        self.q: "queue.Queue[tuple[str, dict[str, Any]]]" = queue.Queue()
        self.client.on_message = self._on_message
        self.client.connect(host, port, keepalive=30)
        self.client.loop_start()
        self.client.subscribe("corridor/state", qos=1)
        self.client.subscribe("corridor/metrics/tick", qos=1)

    def _on_message(self, _c, _u, msg) -> None:  # type: ignore[no-untyped-def]
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return
        self.q.put((msg.topic, payload))

    def publish(self, topic: str, payload: dict[str, Any], retain: bool = False) -> None:
        info = self.client.publish(topic, json.dumps(payload), qos=1, retain=retain)
        info.wait_for_publish(timeout=2)

    def drain(self) -> list[tuple[str, dict[str, Any]]]:
        out: list[tuple[str, dict[str, Any]]] = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                break
        return out

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


# ---------------------------------------------------------------------------
# Traffic generator
# ---------------------------------------------------------------------------

@dataclass
class Generator:
    bus: Bus
    scenario: Scenario
    transit_s: float = 1.5
    rng: random.Random = field(default_factory=lambda: random.Random(0xC0FFEE))
    next_track_id: int = 1
    pending: list[tuple[str, int, float]] = field(default_factory=list)

    def _emit_in(self, side: str, now: float) -> None:
        cls = "truck" if self.rng.random() < self.scenario.truck_prob else "car"
        tid = self.next_track_id
        self.next_track_id += 1
        self.bus.publish(
            f"corridor/cam/{side}/in/event",
            {
                "ts": now,
                "track_id": tid,
                "class": cls,
                "side": side,
                "dir": "in",
                "confidence": 0.92,
                "plate": None,
            },
        )
        # Trucks linger longer.
        delay = self.transit_s * (1.6 if cls == "truck" else 1.0)
        self.pending.append((side, tid, now + delay))

    def _flush_exits(self, now: float) -> None:
        still: list[tuple[str, int, float]] = []
        for side, tid, due in self.pending:
            if now >= due:
                self.bus.publish(
                    f"corridor/cam/{side}/out/event",
                    {
                        "ts": now,
                        "track_id": tid,
                        "class": "car",
                        "side": side,
                        "dir": "out",
                        "confidence": 0.92,
                        "plate": None,
                    },
                )
            else:
                still.append((side, tid, due))
        self.pending = still

    def heartbeats(self) -> None:
        now = time.time()
        for side in ("A", "B"):
            for direction in ("in", "out"):
                self.bus.publish(
                    f"corridor/cam/{side}/{direction}/heartbeat",
                    {
                        "ts": now,
                        "camera_id": f"{side}_{direction}",
                        "fps": 24.0,
                        "healthy": True,
                    },
                    retain=True,
                )

    def run(self, duration_s: float) -> None:
        end = time.monotonic() + duration_s
        next_a = time.monotonic()
        next_b = time.monotonic()
        last_hb = 0.0
        while time.monotonic() < end:
            now = time.monotonic()
            if now - last_hb > 1.0:
                self.heartbeats()
                last_hb = now
            if now >= next_a:
                self._emit_in("A", time.time())
                next_a += 1.0 / max(self.scenario.rate_a, 1e-3)
            if now >= next_b:
                self._emit_in("B", time.time())
                next_b += 1.0 / max(self.scenario.rate_b, 1e-3)
            self._flush_exits(time.time())
            time.sleep(0.05)
        # Final drain so the zone clears.
        deadline = time.monotonic() + 5.0
        while self.pending and time.monotonic() < deadline:
            self._flush_exits(time.time())
            time.sleep(0.1)


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

def collect_to_csv(
    bus: Bus,
    out_path: Path,
    mode: str,
    scenario: str,
    stop: threading.Event,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        last_state: dict[str, Any] = {}
        while not stop.is_set():
            try:
                topic, payload = bus.q.get(timeout=0.5)
            except queue.Empty:
                continue
            if topic == "corridor/state":
                last_state = payload
            elif topic == "corridor/metrics/tick":
                tp = payload.get("throughput_5min") or {}
                qq = payload.get("queue") or {}
                dl = payload.get("avg_delay_5min") or {}
                mq = payload.get("max_queue_today") or {}
                writer.writerow(
                    {
                        "ts": payload.get("ts", time.time()),
                        "mode": mode,
                        "scenario": scenario,
                        "phase": last_state.get("phase", ""),
                        "throughput_A": tp.get("A", ""),
                        "throughput_B": tp.get("B", ""),
                        "queue_A": qq.get("A", ""),
                        "queue_B": qq.get("B", ""),
                        "avg_delay_A": dl.get("A", ""),
                        "avg_delay_B": dl.get("B", ""),
                        "max_queue_today_A": mq.get("A", ""),
                        "max_queue_today_B": mq.get("B", ""),
                    }
                )
                fh.flush()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def set_mode(controller_url: str, mode: str) -> None:
    with httpx.Client(base_url=controller_url, timeout=5.0) as c:
        r = c.post(
            "/override",
            json={"action": "mode_switch", "mode": mode, "by": "bench"},
        )
        r.raise_for_status()


def run_one(
    bus: Bus,
    controller_url: str,
    scenario: Scenario,
    mode: str,
    duration_s: float,
    out_dir: Path,
) -> Path:
    LOG.info("== %s / %s for %.0fs ==", scenario.name, mode, duration_s)
    set_mode(controller_url, mode)
    bus.drain()
    csv_path = out_dir / f"{scenario.name}__{mode}.csv"
    stop = threading.Event()
    t = threading.Thread(
        target=collect_to_csv,
        args=(bus, csv_path, mode, scenario.name, stop),
        daemon=True,
    )
    t.start()
    try:
        Generator(bus=bus, scenario=scenario).run(duration_s)
    finally:
        # Let one or two more ticks flush before we stop.
        time.sleep(2.0)
        stop.set()
        t.join(timeout=5)
    return csv_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mqtt-host", default=os.environ.get("MQTT_HOST", "127.0.0.1"))
    p.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_PORT", 1883)))
    p.add_argument(
        "--controller-url",
        default=os.environ.get("CONTROLLER_URL", "http://127.0.0.1:8000"),
    )
    p.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Scenario name (repeat for multiple). Defaults to asymmetric.",
    )
    p.add_argument("--scenarios-file", type=Path, default=None)
    p.add_argument("--duration", type=float, default=120.0, help="Seconds per mode")
    p.add_argument(
        "--mode",
        action="append",
        default=[],
        choices=["baseline", "adaptive"],
        help="Modes to run (default: both)",
    )
    p.add_argument("--out", type=Path, default=Path("runs"))
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    scenarios = load_scenarios(
        args.scenario or ["asymmetric"], args.scenarios_file
    )
    modes = args.mode or ["baseline", "adaptive"]

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    LOG.info("writing CSVs to %s", out_dir)

    bus = Bus(args.mqtt_host, args.mqtt_port)

    def _bye(*_a: Any) -> None:
        LOG.warning("signal received, shutting down")
        bus.close()
        sys.exit(130)

    signal.signal(signal.SIGINT, _bye)
    signal.signal(signal.SIGTERM, _bye)

    summary: list[dict[str, Any]] = []
    try:
        for scenario in scenarios:
            for mode in modes:
                path = run_one(
                    bus=bus,
                    controller_url=args.controller_url,
                    scenario=scenario,
                    mode=mode,
                    duration_s=args.duration,
                    out_dir=out_dir,
                )
                summary.append(
                    {
                        "scenario": scenario.name,
                        "mode": mode,
                        "csv": str(path.relative_to(out_dir)),
                        "duration_s": args.duration,
                    }
                )
    finally:
        bus.close()

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    LOG.info("done. summary at %s", out_dir / "summary.json")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
