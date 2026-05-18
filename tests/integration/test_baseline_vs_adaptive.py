"""Smoke comparison: adaptive throughput should be >= baseline on a
synthetic asymmetric load.

This is a coarse, end-to-end check, not a benchmark. The real benchmark
lives in `scripts/bench.py` and writes CSVs.
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

from .conftest import MqttBus, _CamPublisher

pytestmark = [pytest.mark.integration, pytest.mark.slow]

DURATION_S = float(os.environ.get("TEST_DURATION_S", "120"))
ARRIVALS_PER_S_A = 1.5
ARRIVALS_PER_S_B = 0.5


def _set_mode(http: httpx.Client, mode: str) -> None:
    r = http.post("/config", json={"mode": mode})
    # Some controllers expose mode toggle via /override; accept either.
    if r.status_code >= 400:
        r = http.post(
            "/override", json={"action": "set_mode", "mode": mode, "by": "itest"}
        )
    assert r.status_code < 400, r.text


def _drive_traffic(
    cam: _CamPublisher,
    duration_s: float,
    rate_a: float,
    rate_b: float,
) -> None:
    """Generate IN/OUT events at given rates. Each IN gets a matching OUT
    after a short, jittered delay so the zone clears properly."""
    end = time.monotonic() + duration_s
    next_a = time.monotonic()
    next_b = time.monotonic()
    pending: list[tuple[str, int, float]] = []
    while time.monotonic() < end:
        now = time.monotonic()
        if now >= next_a:
            tid = cam.event("A", "in")
            pending.append(("A", tid, now + 1.5))
            next_a += 1.0 / rate_a
        if now >= next_b:
            tid = cam.event("B", "in")
            pending.append(("B", tid, now + 1.5))
            next_b += 1.0 / rate_b
        # Flush exits whose deadline has passed.
        still = []
        for side, tid, due in pending:
            if now >= due:
                cam.event(side, "out", track_id=tid)
            else:
                still.append((side, tid, due))
        pending = still
        time.sleep(0.05)
    # Drain remaining exits.
    for side, tid, _ in pending:
        cam.event(side, "out", track_id=tid)


def _collect_throughput(mqtt_client: MqttBus, duration_s: float) -> dict:
    """Collect metric ticks for ``duration_s`` and return last seen sample."""
    end = time.monotonic() + duration_s
    last: dict = {}
    while time.monotonic() < end:
        try:
            topic, payload = mqtt_client.wait_for(
                lambda t, _p: t == "corridor/metrics/tick",
                timeout=max(0.1, end - time.monotonic()),
            )
        except AssertionError:
            break
        last = payload
    return last


def _total_throughput(metrics: dict) -> float:
    tp = metrics.get("throughput_5min") or {}
    return float(tp.get("A", 0)) + float(tp.get("B", 0))


def test_adaptive_at_least_as_good_as_baseline(
    mqtt_client: MqttBus, cam: _CamPublisher, http: httpx.Client
) -> None:
    half = DURATION_S / 2.0

    # --- baseline ---
    _set_mode(http, "baseline")
    cam.heartbeat_all(healthy=True)
    _drive_traffic(cam, half, ARRIVALS_PER_S_A, ARRIVALS_PER_S_B)
    baseline_metrics = _collect_throughput(mqtt_client, 2.0)
    baseline_tp = _total_throughput(baseline_metrics)

    # --- adaptive ---
    _set_mode(http, "adaptive")
    cam.heartbeat_all(healthy=True)
    _drive_traffic(cam, half, ARRIVALS_PER_S_A, ARRIVALS_PER_S_B)
    adaptive_metrics = _collect_throughput(mqtt_client, 2.0)
    adaptive_tp = _total_throughput(adaptive_metrics)

    # Sanity: we got numbers in both runs.
    assert baseline_tp > 0, baseline_metrics
    assert adaptive_tp > 0, adaptive_metrics

    # Allow a small slack to absorb scheduler jitter on synthetic data.
    slack = 0.95
    assert adaptive_tp >= baseline_tp * slack, (
        f"adaptive={adaptive_tp:.1f} < baseline={baseline_tp:.1f} (slack {slack})\n"
        f"baseline_metrics={baseline_metrics}\nadaptive_metrics={adaptive_metrics}"
    )
