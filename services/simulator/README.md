# Reverse Corridor Simulator

Headless traffic simulator for the **smart-reverse-corridor** project.
The simulator publishes the same MQTT events as the real ML/CV service, so
the controller cannot tell the two apart, and additionally streams a live
world snapshot on `corridor/sim/world` for the web dashboard to render.

* Domain: two-lane road with a closed work zone in the middle.
* Vehicles spawn on both ends via Poisson processes (configurable λ).
* Virtual cameras emit events on the contract topics from
  [`docs/MQTT.md`](../../docs/MQTT.md).
* Lights either run an internal 3/3-min baseline timer or follow the
  controller's `corridor/state` (adaptive mode).
* Six demo scenarios cover symmetric flow, asymmetric peaks, truck jams,
  ambulance pre-emption, lost camera, and a stuck vehicle.
* World snapshots (vehicle positions, phases, queues) are published at
  ~15 Hz on `corridor/sim/world` — the web UI draws the road from this
  stream.

The pygame visualisation is **dev-only** and lives behind `--render-debug`.
The primary picture for demos and operators lives in `web/`.

## Install

```bash
cd services/simulator
pip install -r requirements.txt
```

## CLI

```text
python -m app.main \
  --scenario {symmetric|asymmetric|truck|ambulance|lost-camera|stuck} \
  --mode    {baseline|adaptive} \
  --duration 600
```

| Flag | Default | Notes |
|---|---|---|
| `--scenario` | `symmetric` | One of the six presets (aliases supported). |
| `--mode` | `baseline` | `baseline` runs an internal fixed timer; `adaptive` follows `corridor/state`. |
| `--duration` | `600` | Sim seconds. |
| `--render-debug / --no-render-debug` | `--no-render-debug` | Opens a pygame window for sim development. Off by default. |
| `--world-hz` | `15` | Snapshot publish rate (Hz) on `corridor/sim/world`. Set `0` to disable. |
| `--mqtt-host` | `mosquitto` | Use `-` to disable MQTT entirely (in-process noop bus). |
| `--realtime / --fast` | `--realtime` | `--fast` runs as fast as the CPU allows. |
| `--seed` | `42` | RNG seed for repeatable runs. |
| `--headless / --gui` | `--headless` | Deprecated alias; prefer `--render-debug` to enable a window. |

## Quickstart

```bash
# Symmetric baseline against a real broker (default mqtt host); the web
# dashboard subscribes to corridor/sim/world for the live road view.
python -m app.main --scenario symmetric --mode baseline --duration 600

# Asymmetric peak in adaptive mode (controller drives phases).
python -m app.main --scenario asymmetric --mode adaptive --duration 600

# Truck jam — long vehicles overflow the 3-minute baseline window.
python -m app.main --scenario truck --mode baseline --duration 600

# Emergency vehicle pre-emption.
python -m app.main --scenario ambulance --mode adaptive --duration 600

# Camera failure — B_in goes dark for 30s starting at t=90.
python -m app.main --scenario lost-camera --mode adaptive --duration 300

# Vehicle breakdown inside the zone.
python -m app.main --scenario stuck --mode adaptive --duration 300

# Smoke test, no MQTT broker required:
python -m app.main --scenario symmetric --mqtt-host - --duration 30 --fast
```

## Debug rendering

Sim developers can open a pygame window for direct visual debugging. This
is **not** part of the demo flow — operators get the live picture from the
web dashboard via `corridor/sim/world`.

```bash
# Local development with a real X server.
python -m app.main --scenario symmetric --render-debug --duration 60 --fast

# Or via the legacy alias (deprecated, prefer --render-debug):
python -m app.main --scenario symmetric --gui --duration 60 --fast
```

No `SDL_VIDEODRIVER=dummy` workaround is needed for normal headless runs;
pygame is not initialised at all unless `--render-debug` (or `--gui`) is
passed.

## Docker

```bash
docker build -t reverse-corridor-sim services/simulator
docker run --rm \
  -e MQTT_HOST=mosquitto \
  reverse-corridor-sim --scenario symmetric --mode baseline --duration 600
```

The image runs as a non-root user and uses `python -m app.main` as its
entrypoint. Inside the container the simulator is always headless.

## Tests

```bash
cd services/simulator
SDL_VIDEODRIVER=dummy pytest -q
```

Tests cover the world model, the Poisson spawner, the MQTT camera contract,
and the world snapshot publisher. They never open a display.

## Scenarios

| Name | Aliases | What it does |
|---|---|---|
| `symmetric` | — | Baseline reference: equal Poisson load on both sides. |
| `asymmetric_peak` | `asymmetric` | Side A heavy, side B light. |
| `truck_jam` | `truck` | 45% trucks plus a scripted burst at t=60s. |
| `ambulance` | — | Scripted emergency vehicle on side B at t=120s. |
| `lost_camera` | `lost-camera` | Camera B_in down 90s → 120s. |
| `stuck_vehicle` | `stuck` | Next vehicle entering side A freezes for 60s. |

## MQTT topics

The simulator plays the **camera/ML** role for the controller and the
**world streamer** role for the web UI:

* `corridor/cam/<side>/<dir>/event` — vehicle crossings (qos=1).
* `corridor/cam/<side>/<dir>/heartbeat` — 1 Hz, `retain=true`.
* `corridor/sim/world` — live world snapshot, ~15 Hz, `qos=0`, no retain.

In adaptive mode it subscribes to `corridor/state` (also retained) and
mirrors `phase`. It never publishes `corridor/state`,
`corridor/metrics/tick`, or `corridor/alerts` — those belong to the
controller.
