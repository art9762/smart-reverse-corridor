# Infra

Эта папка содержит инфраструктурные конфиги для локального dev-стека и точки расширения для prod.

## Сервисы и порты (по умолчанию)

| Сервис      | Контейнер           | Внутр. порты | Хост-порты         | Назначение                              |
|-------------|---------------------|--------------|--------------------|------------------------------------------|
| mosquitto   | `eclipse-mosquitto:2` | 1883, 9001  | 1883, 9001         | MQTT broker (TCP + WebSocket)            |
| influxdb    | `influxdb:2`        | 8086         | 8086               | TSDB для метрик                          |
| controller  | `services/controller` | 8000       | 8000               | FastAPI + FSM + MQTT-клиент              |
| ml          | `services/ml`       | -            | -                  | Детекция/трекинг (профиль `ml`)          |
| simulator   | `services/simulator`| -            | -                  | Генератор трафика (профиль `sim`)        |
| web         | `web/`              | 5173         | 5173               | React/Vite дашборд                       |
| grafana     | `grafana/grafana`   | 3000         | 3001               | Графики, дашборд `corridor.json`         |

Внутри контейнеров все сервисы слушают на `0.0.0.0`. Наружу (на хост) пробрасываем минимум:
`web 5173`, `controller 8000`, `grafana 3001`, `influxdb 8086`, `mosquitto 1883/9001`.

## Compose-профили

```bash
docker compose up -d                    # core: mosquitto, influxdb, controller, web, grafana
docker compose --profile sim up -d      # +simulator
docker compose --profile ml up -d       # +ml (CV-сервис)
docker compose --profile sim --profile ml up -d   # все сразу
```

Или через Makefile: `make up`, `make demo`, `make logs`, `make down`, `make clean`.

## Mosquitto

Конфиг: `infra/mosquitto/mosquitto.conf`. По умолчанию **анонимный** — это только для dev. Для prod:

1. Создайте файл паролей:
   ```bash
   docker run --rm -it -v $(pwd)/infra/mosquitto:/m eclipse-mosquitto:2 \
     mosquitto_passwd -c /m/passwd corridor
   ```
2. В `mosquitto.conf` поменяйте:
   ```
   allow_anonymous false
   password_file /mosquitto/config/passwd
   ```
   и смонтируйте `passwd` в compose (см. volumes).
3. Включите ACL: `acl_file /mosquitto/config/acl`.

## TLS для MQTT

Для включения TLS на порту 8883:

1. Положите сертификаты в `infra/mosquitto/certs/` (`ca.crt`, `server.crt`, `server.key`).
2. Добавьте в `mosquitto.conf`:
   ```
   listener 8883 0.0.0.0
   protocol mqtt
   cafile   /mosquitto/config/certs/ca.crt
   certfile /mosquitto/config/certs/server.crt
   keyfile  /mosquitto/config/certs/server.key
   require_certificate false
   ```
3. Прокиньте `8883:8883` в compose, обновите `MQTT_PORT=8883` в `.env`.
4. Для WebSocket-TLS — аналогично на `9002` (`protocol websockets` + cert/key).

## Grafana

- Datasource: `infra/grafana/provisioning/datasources/influxdb.yml` подхватывается на старте.
- Dashboards: `infra/grafana/provisioning/dashboards/dashboard.yml` указывает Grafana грузить JSON из `/etc/grafana/dashboards` (смонтировано из `infra/grafana/dashboards/`).
- Логин/пароль по умолчанию: `admin / ${GRAFANA_ADMIN_PASSWORD:-admin}` (см. `.env`).

## InfluxDB

Авто-сетап на первом старте (env `DOCKER_INFLUXDB_INIT_*`) создаёт:
- org: `${INFLUX_ORG}` (default `cet`)
- bucket: `${INFLUX_BUCKET}` (default `corridor`)
- admin token: `${INFLUX_TOKEN}` (поставьте свой в `.env`).

UI: http://localhost:8086.

## Миграция с Mosquitto на NATS

Если в будущем понадобится более серьёзная шина (cluster, JetStream, request/reply, queue groups):

1. Замените сервис в `docker-compose.yml`:
   ```yaml
   nats:
     image: nats:2-alpine
     command: ["-js", "-m", "8222"]
     ports: ["4222:4222", "8222:8222"]
   ```
2. В `services/controller` и `services/ml` подмените MQTT-клиент на `nats-py` / `nats.js`. Топики переезжают как есть (точки → точки), `corridor/cam/A/in/event` → `corridor.cam.A.in.event`.
3. Для браузера используйте `nats.ws` (WebSocket) — у NATS он встроенный, отдельный listener в Mosquitto-стиле не нужен.
4. `corridor/state` (retained) → JetStream stream с `MaxMsgsPerSubject=1` или KV-bucket.
5. Снимите Mosquitto из compose, обновите `.env` (`NATS_URL=nats://nats:4222`).

## Масштабирование

Локальный compose-стек — single-node. Что менять в проде:

- **MQTT**: вместо одиночного Mosquitto — кластер EMQX/HiveMQ или NATS (см. выше).
- **InfluxDB**: для нагрузки — InfluxDB Cloud / Enterprise или TimescaleDB.
- **Controller**: stateless по REST — за reverse-proxy (nginx/traefik) можно масштабировать горизонтально, FSM держать в одном инстансе (leader election через NATS KV / Redis).
- **ML**: один контейнер на одну камеру (или GPU). Запускать на GPU-нодах через k8s + nvidia-device-plugin. Видео можно тянуть из RTSP, метаданные публиковать в шину.
- **Web**: статика — выгрузить в CDN/S3 + CloudFront, либо отдавать через nginx-контейнер.
- **Grafana**: вынести в managed (Grafana Cloud) или standalone, datasource поднять на read-only token.

## Деплой

Для k8s — отдельная папка `infra/k8s/` (TBD): helm-чарты или kustomize. Для `compose up` на staging-VM — добавьте `docker-compose.prod.yml` с TLS, ограничением по IP и без анонимного MQTT.
