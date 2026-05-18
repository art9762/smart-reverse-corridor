# Reverse Corridor Simulator

Pygame-driven traffic simulator for the **smart-reverse-corridor** project.
The simulator publishes the same MQTT events as the real ML/CV service, so
the controller cannot tell the two apart.

* Domain: two-lane road with a closed work zone in the middle.
* Vehicles spawn on both ends via Poisson processes (configurable λ).
* Virtual cameras emit events on the contract topics from
  [`docs/MQTT.md`](../../docs/MQTT.md).
* Lights either run an internal 3/3-min baseline timer or follow the
  controller's `corridor/state` (adaptive mode).
* Six demo scenarios cover symmetric flow, asymmetric peaks, truck jams,
  ambulance pre-emption, lost camera, and a stuck vehicle.

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
  --duration 600 \
  --headless
```

| Flag | Default | Notes |
|---|---|---|
| `--scenario` | `symmetric` | One of the six presets (aliases supported). |
| `--mode` | `baseline` | `baseline` runs an internal fixed timer; `adaptive` follows `corridor/state`. |
| `--duration` | `600` | Sim seconds. |
| `--headless / --gui` | `--gui` | Headless skips the display window — required for CI/Docker. |
| `--mqtt-host` | `mosquitto` | Use `-` to disable MQTT entirely (in-process noop bus). |
| `--realtime / --fast` | `--realtime` | `--fast` runs as fast as the CPU allows. |
| `--seed` | `42` | RNG seed for repeatable runs. |

## Headless quickstart

```bash
# Symmetric baseline against a real broker (default mqtt host).
SDL_VIDEODRIVER=dummy python -m app.main --scenario symmetric --mode baseline --duration 600 --headless

# Asymmetric peak in adaptive mode (controller drives phases).
SDL_VIDEODRIVER=dummy python -m app.main --scenario asymmetric --mode adaptive --duration 600 --headless

# Truck jam — long vehicles overflow the 3-minute baseline window.
SDL_VIDEODRIVER=dummy python -m app.main --scenario truck --mode baseline --duration 600 --headless

# Emergency vehicle pre-emption.
SDL_VIDEODRIVER=dummy python -m app.main --scenario ambulance --mode adaptive --duration 600 --headless

# Camera failure — B_in goes dark for 30s starting at t=90.
SDL_VIDEODRIVER=dummy python -m app.main --scenario lost-camera --mode adaptive --duration 300 --headless

# Vehicle breakdown inside the zone.
SDL_VIDEODRIVER=dummy python -m app.main --scenario stuck --mode adaptive --duration 300 --headless

# Same, no MQTT broker required (handy for smoke tests):
SDL_VIDEODRIVER=dummy python -m app.main --scenario symmetric --headless --mqtt-host - --duration 30 --fast
```

## Docker

```bash
docker build -t reverse-corridor-sim services/simulator
docker run --rm \
  -e MQTT_HOST=mosquitto \
  reverse-corridor-sim --scenario symmetric --mode baseline --duration 600 --headless
```

The image ships with `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy`,
runs as a non-root user, and uses `python -m app.main` as its entrypoint.

## Tests

```bash
cd services/simulator
SDL_VIDEODRIVER=dummy pytest -q
```

Tests cover the world model, the Poisson spawner, and the MQTT camera
contract. They never open a display.

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

The simulator only acts as **camera/ML** in the system architecture, so it
publishes:

* `corridor/cam/<side>/<dir>/event` — vehicle crossings.
* `corridor/cam/<side>/<dir>/heartbeat` — 1 Hz, `retain=true`.

In adaptive mode it subscribes to `corridor/state` (also retained) and
mirrors `phase`. It never publishes `corridor/state`, `corridor/metrics/tick`,
or `corridor/alerts` — those belong to the controller.
