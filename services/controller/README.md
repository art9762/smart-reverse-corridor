# Smart Reverse Corridor — Controller

FastAPI + paho-mqtt + transitions service that drives the corridor's adaptive
phase finite-state machine (FSM).

## What it does

* Subscribes to camera events on `corridor/cam/<side>/<dir>/event` and tracks
  per-side `enter / exit / inside` counters.
* Runs a safety-checked FSM (`INIT → RED_BOTH → GREEN_A → YELLOW_A →
  ALL_RED_AFTER_A → GREEN_B → YELLOW_B → ALL_RED_AFTER_B → ...`) with hard
  guards: a `GREEN_X` state is only entered when **the corridor is empty** and
  `ALL_RED_GUARD_S` has elapsed since the last YELLOW.
* Computes adaptive green durations:
  ```
  T_green = clamp(base + a*queue_side + b*wait_other - c*other_empty,
                  GREEN_MIN_S, GREEN_MAX_S)
  ```
* Publishes `corridor/state` (retain), `corridor/metrics/tick` and
  `corridor/alerts`.
* Exposes a REST + WebSocket API for the dashboard and operators.
* Stores events and config in SQLite. Optional InfluxDB sink for tick metrics —
  if Influx is unreachable, writes degrade to no-ops.

## Endpoints

| Method | Path        | Purpose                                                  |
|-------:|-------------|----------------------------------------------------------|
| GET    | `/health`   | liveness check (used by the docker healthcheck)         |
| GET    | `/state`    | current FSM phase, queues, camera health                |
| GET    | `/metrics`  | last metrics tick + recent alerts                       |
| POST   | `/override` | `force_phase` / `emergency` / `resume` / `mode_switch`  |
| POST   | `/config`   | hot-reload timings & weights                            |
| WS     | `/ws`       | streams `state` and `alert` updates                     |

### Override examples

```bash
curl -X POST localhost:8000/override \
  -H 'content-type: application/json' \
  -d '{"action":"force_phase","phase":"GREEN_B","reason":"ambulance"}'

curl -X POST localhost:8000/override \
  -H 'content-type: application/json' \
  -d '{"action":"mode_switch","mode":"baseline"}'
```

### Config hot-reload

```bash
curl -X POST localhost:8000/config \
  -H 'content-type: application/json' \
  -d '{"green_min_s":20,"prio_w_queue":1.5}'
```

## Run locally

```bash
cd services/controller
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.example .env  # adjust if needed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Run with docker

```bash
docker build -t corridor-controller services/controller
docker run --rm -p 8000:8000 --env-file .env corridor-controller
```

The healthcheck in the image hits `GET /health`.

## Run tests

```bash
cd services/controller
pip install -r requirements.txt
pytest -q
```

## Project layout

```
services/controller/
├── app/
│   ├── api.py          # FastAPI routes + WebSocket
│   ├── config.py       # pydantic-settings ENV
│   ├── counters.py     # per-side enter/exit + watchdog
│   ├── engine.py       # core engine wiring everything together
│   ├── fsm.py          # transitions-based FSM
│   ├── main.py         # FastAPI app + lifespan
│   ├── mqtt_client.py  # paho-mqtt thread + asyncio bridge
│   ├── scheduler.py    # adaptive green-phase calculator
│   └── storage.py      # SQLite + optional InfluxDB writer
├── tests/
│   ├── test_api_smoke.py
│   ├── test_counters.py
│   ├── test_fsm.py
│   └── test_scheduler.py
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Concurrency

Single asyncio event loop. The MQTT client runs in paho's own thread and
forwards messages to an `asyncio.Queue` via `loop.call_soon_threadsafe`. All
timers go through `asyncio.sleep` — no `time.sleep` in the loop.

## Safety properties (covered by tests)

* `GREEN_X` is unreachable while `inside_A != 0 or inside_B != 0`.
* `GREEN_X` is unreachable until `ALL_RED_GUARD_S` after the previous YELLOW.
* `EMERGENCY_STOP` is reachable from every state and only `resume` exits it.
* Loss of both cameras on a side falls back to `RED_BOTH` and raises an alert.
* Adaptive duration is always clamped to `[GREEN_MIN_S, GREEN_MAX_S]`.
