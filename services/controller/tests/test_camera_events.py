"""Replay and validation regressions for software camera-event ingestion."""

from __future__ import annotations

import sqlite3

import pytest
from app.camera_events import CameraEventGate
from app.config import Settings
from app.engine import Engine


def event(track_id=1, ts=10.0, **extra):
    return {"track_id": track_id, "ts": ts, **extra}


@pytest.fixture
def engine(tmp_path):
    return Engine(Settings(SQLITE_PATH=str(tmp_path / "controller.db"), INFLUX_URL=None))


def test_redelivered_exit_does_not_remove_another_simulated_vehicle(engine):
    engine._handle_cam_event("A", "in", event(1, event_id="enter-1"))
    engine._handle_cam_event("A", "in", event(2, event_id="enter-2"))
    exiting = event(1, ts=20.0, event_id="exit-1")
    engine._handle_cam_event("B", "out", exiting)
    engine._handle_cam_event("B", "out", dict(exiting))

    assert engine.state_payload()["inside_A"] == 1
    assert engine.counters.snapshot()["A"]["exit"] == 1
    assert len(engine._throughput_events["A"]) == 2
    assert len(engine._recent_delays["A"]) == 1
    with sqlite3.connect(engine.settings.sqlite_path) as connection:
        assert connection.execute("SELECT count(*) FROM events WHERE kind = 'cam_event'").fetchone()[0] == 3
    engine.fsm.try_trigger("boot")
    assert not engine.fsm.try_trigger("go_green_b")

    engine._handle_cam_event("B", "out", event(2, ts=21.0, event_id="exit-2"))
    assert engine.counters.is_zone_empty()
    assert engine.fsm.try_trigger("go_green_b")


def test_redelivered_entry_does_not_inflate_occupancy_or_throughput(engine):
    crossing = event(event_id="entry")
    engine._handle_cam_event("B", "in", crossing)
    engine._handle_cam_event("B", "in", dict(crossing))
    engine._compute_rolling_metrics()
    assert engine.counters.inside("B") == 1
    assert engine.state.throughput_5min["B"] == 1


def test_invalid_event_is_rejected_before_counter_or_identity_mutation(engine):
    engine._handle_cam_event("A", "in", event(track_id="bad", event_id="entry"))
    assert engine.counters.is_zone_empty()
    assert not engine._throughput_events["A"]
    engine._handle_cam_event("A", "in", event(track_id=1, event_id="entry"))
    assert engine.counters.inside("A") == 1


def test_legacy_identity_includes_topic_track_and_source_timestamp():
    gate = CameraEventGate()
    assert gate.accept("A", "in", event())
    assert not gate.accept("A", "in", event())
    assert gate.accept("B", "out", event())
    assert gate.accept("A", "in", event(track_id=2))
    assert gate.accept("A", "in", event(ts=11.0))


def test_new_event_ids_allow_track_and_simulation_time_to_restart():
    gate = CameraEventGate()
    assert gate.accept("A", "in", event(event_id="run-1"))
    assert gate.accept("A", "in", event(event_id="run-2"))
    assert not gate.accept("A", "in", event(ts=12.0, event_id="run-1"))


def test_replay_window_uses_receipt_time_and_does_not_extend_on_replays(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.camera_events.time.monotonic", lambda: clock[0])
    gate = CameraEventGate(ttl_s=10)
    assert gate.accept("A", "in", event(ts=0))
    clock[0] = 109.0
    assert not gate.accept("A", "in", event(ts=0))
    clock[0] = 110.0
    assert gate.accept("A", "in", event(ts=0))


def test_replay_cache_evicts_oldest_at_capacity():
    gate = CameraEventGate(max_events=2)
    assert gate.accept("A", "in", event(1))
    assert gate.accept("A", "in", event(2))
    assert gate.accept("A", "in", event(3))
    assert not gate.accept("A", "in", event(2))
    assert gate.accept("A", "in", event(1))
    assert len(gate._seen) == 2


@pytest.mark.asyncio
async def test_explicit_test_reset_clears_replay_history(engine):
    crossing = event(event_id="entry")
    engine._handle_cam_event("A", "in", crossing)
    engine.reset_for_test()
    engine._handle_cam_event("A", "in", crossing)
    assert engine.counters.inside("A") == 1


@pytest.mark.parametrize("payload", [
    None, [], {}, event(track_id=None), event(track_id=True), event(track_id=1.5),
    event(track_id="1"), event(track_id=-1), event(ts=None), event(ts=True),
    event(ts="10"), event(ts=float("nan")), event(ts=float("inf")), event(ts=-1),
    event(ts=10**1000), event(side="B"), event(dir="out"), event(event_id=""),
    event(event_id="  "), event(event_id=[]), event(event_id="x" * 129),
])
def test_invalid_payloads_are_rejected(payload):
    with pytest.raises((TypeError, ValueError)):
        CameraEventGate().accept("A", "in", payload)


@pytest.mark.parametrize("side,direction", [("C", "in"), ("A", "other")])
def test_unknown_topics_are_rejected(side, direction):
    with pytest.raises(ValueError):
        CameraEventGate().accept(side, direction, event())
