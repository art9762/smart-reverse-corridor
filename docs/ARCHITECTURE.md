# Архитектура

## Сервисы

### 1. `services/ml` — детекция и трекинг
- Вход: видеопотоки от 4 камер (A_in, A_out, B_in, B_out) — файлы или RTSP.
- Алгоритм: YOLOv8n → ByteTrack → виртуальная линия пересечения.
- Выход (MQTT):
  - `corridor/cam/<side>/<dir>/event` — `{ts, track_id, class, side, dir}`
  - `corridor/cam/<side>/<dir>/heartbeat` — раз в 1с (для watchdog)

### 2. `services/controller` — мозг системы
- FSM: `RED_BOTH → GREEN_A → YELLOW_A → ALL_RED(clear) → GREEN_B → YELLOW_B → ALL_RED(clear) → ...`
- Подписан на `corridor/cam/#`. Ведёт счётчики `enter_A`, `exit_A`, `enter_B`, `exit_B`, `inside_A`, `inside_B`.
- Публикует:
  - `corridor/state` — текущее состояние FSM, длительности, оставшееся время.
  - `corridor/metrics/tick` — раз в 1с — очереди, throughput, задержки.
  - `corridor/alerts` — emergency, lost-camera, stuck-vehicle.
- REST API (FastAPI):
  - `GET /state` — текущее состояние.
  - `GET /metrics?from=&to=` — агрегаты для графиков.
  - `POST /override` — ручное переключение / приоритет спецтранспорта.
  - `POST /config` — горячая правка весов/таймингов.
  - `WS /ws` — стрим событий (для UI).
- Хранилище: InfluxDB (метрики), SQLite (события + конфиг).

### 3. `services/simulator` — генератор трафика для демо и тестов
- Pygame-окно: дорога, машины, светофоры.
- Поддерживает baseline (фиксированный таймер) и adaptive (через MQTT).
- Может генерировать MQTT-события **вместо** ML — это режим эмуляции камер для разработки без видео.
- Сценарии: symmetric, asymmetric, truck, ambulance, lost-camera, stuck.

### 4. `web/` — дашборд
- React + Vite + TS.
- Лайв-схема дороги, очереди, состояние FSM, графики throughput/задержки.
- Кнопки: ручное переключение, эмуляция спецтранспорта, переключение baseline/adaptive.
- Подключение к контроллеру: REST + WS (события и метрики).

## MQTT топики

См. [`MQTT.md`](MQTT.md).

## Конечный автомат

См. [`FSM.md`](FSM.md).
