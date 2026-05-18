# Архитектура

## Сервисы

### 1. `services/ml` — детекция и трекинг
- Вход: видеопотоки от 4 камер (A_in, A_out, B_in, B_out) — файлы или RTSP.
- Алгоритм: YOLOv8n → ByteTrack → виртуальная линия пересечения.
- Выход (MQTT):
  - `corridor/cam/<side>/<dir>/event`
  - `corridor/cam/<side>/<dir>/heartbeat`

### 2. `services/controller` — мозг системы
- FSM, адаптивный планировщик, REST/WS API.
- Слушает только CV-события и команды.
- НЕ читает `corridor/sim/world` — это только для визуализации.

### 3. `services/simulator` — headless-генератор трафика
- По умолчанию без GUI.
- Публикует:
  - `corridor/cam/...` — роль «железных камер» для контроллера.
  - `corridor/sim/world` — живой слепок мира для UI (10–20 Hz).
- Pygame-окно — опциональный debug-флаг (`--render-debug`), не основной путь.

### 4. `web/` — дашборд и визуализация
- React + Vite + TS.
- Основная визуализация живёт здесь (canvas/SVG по слепку из `corridor/sim/world`).
- Карты/графики/кнопки оператора.
- Подписка: REST + WS к контроллеру + MQTT-over-WS на mosquitto (для «world» напрямую).

## MQTT топики

См. [`MQTT.md`](MQTT.md).

## Конечный автомат

См. [`FSM.md`](FSM.md).
