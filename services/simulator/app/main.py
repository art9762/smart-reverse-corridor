"""CLI entrypoint for the reverse-corridor simulator.

Wires together world, spawner, lights, camera bus, MQTT bridge, the world
snapshot publisher (`corridor/sim/world`), and the optional pygame debug
renderer behind a single `python -m app.main` command.

The simulator is **headless by default** — the live picture is rendered by
the web dashboard from `corridor/sim/world`. Pygame stays available behind
`--render-debug` for sim development.

Usage examples are listed in `README.md`.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from typing import Optional

import click
import structlog

from .cameras import CameraBus
from .config import SimulatorSettings, get_settings
from .lights import Lights
from .metrics_local import LocalMetrics
from .mqtt_bus import MqttBus, _NoopBus
from .scenarios import Scenario, ScheduledEvent, get_scenario
from .spawner import Spawner
from .world import Phase, Side, VehicleType, World
from .world_publisher import WorldPublisher


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), stream=sys.stderr, format="%(message)s")
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        )
    )


@click.command(context_settings={"show_default": True})
@click.option(
    "--scenario",
    type=click.Choice(
        [
            "symmetric",
            "asymmetric",
            "asymmetric_peak",
            "truck",
            "truck_jam",
            "ambulance",
            "lost-camera",
            "lost_camera",
            "stuck",
            "stuck_vehicle",
        ]
    ),
    default="symmetric",
    help="Scenario preset.",
)
@click.option(
    "--mode",
    type=click.Choice(["baseline", "adaptive"]),
    default="baseline",
    help="baseline = fixed 3/3 min cycle; adaptive = mirror corridor/state.",
)
@click.option(
    "--duration",
    type=float,
    default=600.0,
    help="Simulation length in seconds (real or sim time).",
)
@click.option(
    "--render-debug/--no-render-debug",
    default=False,
    help=(
        "Open a pygame window for sim development. The web dashboard is the "
        "primary visualisation; this flag is for sim devs only."
    ),
)
@click.option(
    "--headless/--gui",
    default=True,
    help=(
        "Deprecated alias. Headless is the default; pass --render-debug to "
        "open a pygame window. --gui still flips the renderer on for legacy "
        "compatibility."
    ),
)
@click.option("--seed", type=int, default=42)
@click.option(
    "--mqtt-host",
    default=None,
    help="MQTT broker host. Use '-' to disable MQTT (no-op bus).",
)
@click.option("--mqtt-port", type=int, default=None)
@click.option(
    "--world-hz",
    type=float,
    default=15.0,
    help="World snapshot publish rate (Hz) on corridor/sim/world. Set 0 to disable.",
)
@click.option(
    "--realtime/--fast",
    default=True,
    help="realtime sleeps between ticks; fast runs as fast as possible.",
)
@click.option("--log-level", default="INFO")
def main(
    scenario: str,
    mode: str,
    duration: float,
    render_debug: bool,
    headless: bool,
    seed: int,
    mqtt_host: Optional[str],
    mqtt_port: Optional[int],
    world_hz: float,
    realtime: bool,
    log_level: str,
) -> None:
    """Run the reverse-corridor simulator."""
    _setup_logging(log_level)
    settings = get_settings()

    # Resolve renderer preference. Headless (no pygame) is the default; the
    # legacy --gui flag still flips it on for backwards compatibility.
    enable_pygame = render_debug or (not headless)

    world = World(
        approach_m=settings.approach_length_m,
        zone_m=settings.zone_length_m,
    )
    sc = get_scenario(scenario, seed=seed)
    spawner = Spawner(world, sc.spawner, settings=settings)
    for at, side, type_ in sc.scripted_spawns:
        spawner.script(at, side, type_)
    lights = Lights(settings=settings, mode=mode)
    metrics = LocalMetrics()

    bus = _build_bus(mqtt_host, mqtt_port, settings)
    cameras = CameraBus(publish=bus.publish)
    bus.connect()
    if mode == "adaptive":
        bus.subscribe("corridor/state", lambda payload: lights.apply_state(payload, time.time()))

    world_pub: Optional[WorldPublisher] = None
    if world_hz > 0:
        world_pub = WorldPublisher(publish=bus.publish, hz=world_hz)

    renderer = None
    if enable_pygame or os.environ.get("FORCE_RENDER") == "1":
        try:
            from .render import Renderer

            # When --render-debug is on we open a real window; the legacy
            # --gui path also lands here.
            renderer = Renderer(settings=settings, headless=False)
        except Exception:  # noqa: BLE001
            logging.exception("render unavailable, continuing headless")

    pending_events = list(sc.events)
    pending_events.sort(key=lambda e: e.at)
    # Side -> sim-time at which the next entrant should be frozen until.
    pending_stick: dict[Side, float] = {}

    sim_t = 0.0
    dt = 1.0 / settings.fps
    events_published_total = 0
    next_metrics_at = 0.0
    started = time.time()

    try:
        while sim_t < duration:
            now = sim_t
            # Apply scheduled scenario events.
            while pending_events and pending_events[0].at <= now:
                evt = pending_events.pop(0)
                _apply_scheduled(evt, world, cameras, now, pending_stick)

            spawner.tick(now)
            phase = lights.tick(now)
            world.step(dt, phase, now)
            crossings = world.detect_crossings()
            events_published_total += cameras.emit_events(crossings, now)
            cameras.emit_heartbeats(now)
            for v, cam_side, direction in crossings:
                if direction == "out":
                    metrics.record_exit(v, cam_side, now)
                if direction == "in" and v.side in pending_stick:
                    v.stuck_until = pending_stick.pop(v.side)
                    logging.info(
                        "stuck vehicle: id=%d side=%s stuck_until=%.1f",
                        v.id,
                        v.side.value,
                        v.stuck_until,
                    )
            metrics.update_queues(world)

            # Stream world snapshot for the web UI (does not affect the
            # controller — it only reads CV events).
            if world_pub is not None:
                world_pub.maybe_emit(world, phase, now)

            # Publish metrics at 1 Hz only if no real controller is around;
            # the real one publishes its own corridor/metrics/tick. The
            # simulator only pretends to be the ML/CV service, so we don't
            # emit corridor/metrics/tick here.
            snap = metrics.snapshot(world, now)
            if renderer is not None:
                if not renderer.pump():
                    break
                renderer.draw(world, phase, mode, scenario, snap, events_published_total)
            elif now >= next_metrics_at:
                # Periodic structured log so headless runs are observable.
                logging.info(
                    "t=%6.1fs phase=%s queue=A%d/B%d inside=A%d/B%d "
                    "thr_A=%d thr_B=%d events=%d",
                    now,
                    phase.value,
                    snap["queue"]["A"],
                    snap["queue"]["B"],
                    world.inside_counts()[0],
                    world.inside_counts()[1],
                    snap["throughput_5min"]["A"],
                    snap["throughput_5min"]["B"],
                    events_published_total,
                )
                next_metrics_at = now + 5.0

            sim_t += dt
            if realtime:
                # Sleep enough to keep wall-clock pace.
                target = started + sim_t
                slack = target - time.time()
                if slack > 0:
                    time.sleep(slack)
    finally:
        if renderer is not None:
            renderer.quit()
        bus.disconnect()


def _apply_scheduled(
    evt: ScheduledEvent,
    world: World,
    cameras: CameraBus,
    now: float,
    pending_stick: dict[Side, float],
) -> None:
    if evt.kind == "camera_lost":
        cam = evt.payload["camera"]
        duration = evt.payload.get("duration")
        until = now + duration if duration else None
        cameras.set_lost(cam, until)
    elif evt.kind == "camera_restored":
        cameras.restore(evt.payload["camera"])
    elif evt.kind == "stick_next_inside":
        side = Side(evt.payload["side"])
        duration = evt.payload.get("duration", 60.0)
        candidates = world.inside_a if side is Side.A else world.inside_b
        if candidates:
            candidates[0].stuck_until = now + duration
        else:
            # Latch: the next vehicle entering that side will be frozen.
            pending_stick[side] = now + duration
    else:
        logging.warning("unknown scheduled event kind: %s", evt.kind)


def _build_bus(host: Optional[str], port: Optional[int], settings: SimulatorSettings):
    if host == "-":
        return _NoopBus()
    return MqttBus(
        host=host or settings.mqtt_host,
        port=port or settings.mqtt_port,
        client_id=settings.mqtt_client_id,
        user=settings.mqtt_user,
        password=settings.mqtt_pass,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
