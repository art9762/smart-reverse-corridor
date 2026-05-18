# Smart Reverse Corridor — Operator Dashboard

React + Vite + TypeScript dashboard for the Smart Reverse Corridor controller.
Single-page operator/viewer cockpit with a live SVG road, phase countdown,
queue and throughput charts, alerts feed, camera health, and override controls.

## Stack

- **React 18 + Vite 5 + TypeScript (strict)**
- **Tailwind 3** for styling — dark theme, FullHD-ready layout
- **zustand** store, fed by `/ws` and (optionally) direct MQTT WebSocket
- **Recharts** for time-series visuals
- **mqtt** for the optional direct mosquitto WS subscription
- **axios** as the only HTTP layer (`src/api/client.ts`)
- **vitest + @testing-library/react** unit tests (jsdom, no browser)

## Quick start

```bash
cd web
npm install
npm run dev   # serves on http://localhost:5173
```

The dev server proxies nothing — it talks directly to the controller endpoints
configured via env vars below. Make sure the controller is up at
`VITE_API_URL` and that `/ws` is reachable.

## Environment

All variables are prefixed with `VITE_` so Vite exposes them to the bundle.

| Variable           | Default                          | Description                                        |
| ------------------ | -------------------------------- | -------------------------------------------------- |
| `VITE_API_URL`     | `http://localhost:8000`          | Base URL for REST (`/state`, `/metrics`, `/override`, `/config`). |
| `VITE_WS_URL`      | `ws://localhost:8000/ws`         | WebSocket relay from the controller.               |
| `VITE_MQTT_WS_URL` | (unset)                          | Optional direct mosquitto WS endpoint for raw MQTT.|

Copy `web/.env.example` to `web/.env.local` to override.

## Scripts

| Script            | Purpose                                                |
| ----------------- | ------------------------------------------------------ |
| `npm run dev`     | Vite dev server with HMR.                              |
| `npm run build`   | Type-check + production bundle to `dist/`.             |
| `npm run preview` | Serve `dist/` locally (port 5173).                     |
| `npm run lint`    | `tsc --noEmit` (no separate eslint to keep deps lean). |
| `npm test`        | Run vitest in jsdom, no browser required.              |

## Production (Docker)

The `Dockerfile` is a multi-stage build (Node → Nginx). The Vite build output
is served by Nginx with SPA fallback, gzip, and aggressive caching for
hashed assets.

```bash
docker build -t corridor-web ./web
docker run --rm -p 8080:80 \
  -e VITE_API_URL=http://controller:8000\
  corridor-web
```

> Note: Vite inlines `import.meta.env.VITE_*` at build time, so to override
> URLs in production rebuild with the desired vars, or proxy through the
> reverse-proxy block in `nginx.conf`.

## Layout

```
web/
├── src/
│   ├── api/           # client.ts (axios), ws.ts (controller /ws), mqtt.ts (mosquitto WS)
│   ├── components/    # RoadView, PhasePanel, charts, AlertsFeed, ControlPanel, CameraHealth
│   ├── lib/format.ts  # time/number formatters
│   ├── __tests__/     # vitest unit tests (store + RoadView)
│   ├── store.ts       # zustand: state, metrics, alerts, queues, cameras
│   ├── types.ts       # MQTT/REST type contracts (mirror docs/MQTT.md)
│   ├── App.tsx        # composition + WS lifecycle
│   ├── main.tsx
│   └── index.css      # tailwind + tokens
├── tailwind.config.js
├── postcss.config.js
├── vite.config.ts
├── tsconfig.json
├── Dockerfile
└── nginx.conf
```

## Dashboard panels

- **PhasePanel** — current FSM phase, big countdown, baseline/adaptive toggle.
- **RoadView** — SVG road with two signals, vehicles inside the zone,
  queue stacks at both ends, color-coded health.
- **QueueChart / ThroughputChart** — Recharts line charts driven by
  `corridor/metrics/tick`.
- **ControlPanel** — operator overrides:
  - Ambulance from A/B (`POST /override` with `priority`).
  - Force GREEN_A / GREEN_B (`POST /override` with `force_phase`).
  - Emergency Stop / Resume.
  - Adaptive weight sliders (`POST /config`).
- **CameraHealth** — four cameras, color-coded by heartbeat.
- **AlertsFeed** — emergency / warning / info filter, dismiss to ack.

## Operator scenarios

- **Symmetric load** — phases alternate, charts hold steady.
- **Asymmetric load** — adaptive mode favors the loaded side; sliders let
  the operator bias toward queue or wait time.
- **Truck convoy** — bump truck weight to extend green for that side.
- **Ambulance** — single click forces priority green from the chosen side
  and surfaces an alert in the feed.
- **Camera lost** — the affected camera dot turns red and pulses; an
  alert tagged `CAMERA_LOST` lands in the feed.
- **Stuck vehicle** — `STUCK_VEHICLE` warning is highlighted; operator can
  Emergency Stop and inspect.
