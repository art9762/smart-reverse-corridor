# Инструкция: сборка и проверка демо-продукта

Полное руководство по запуску всех компонентов Smart Reverse Corridor в связке, проверке соответствия кейсу и подготовке к демонстрации.

---

## Содержание

1. [Требования к окружению](#1-требования-к-окружению)
2. [Быстрый старт (5 минут)](#2-быстрый-старт)
3. [Полная сборка всех сервисов](#3-полная-сборка-всех-сервисов)
4. [Проверка ML-пайплайна на видео](#4-проверка-ml-пайплайна-на-видео)
5. [Интеграционная проверка (ML → MQTT → Controller → Web)](#5-интеграционная-проверка)
6. [Чек-лист соответствия кейсу](#6-чек-лист-соответствия-кейсу)
7. [Сценарии демонстрации](#7-сценарии-демонстрации)
8. [Устранение проблем](#8-устранение-проблем)

---

## 1. Требования к окружению

### Обязательно

| Компонент | Версия | Проверка |
|-----------|--------|----------|
| Docker Desktop | 4.x+ | `docker --version` |
| Docker Compose | v2+ | `docker compose version` |
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| Git | 2.x | `git --version` |

### Для ML-демо (локально, без Docker)

```bash
pip install -r requirements-demo.txt
```

Это установит: `ultralytics`, `opencv-python`, `numpy`, `paho-mqtt`, `pydantic-settings`, `structlog`.

### Для GPU-ускорения (опционально)

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

---

## 2. Быстрый старт

Минимальный запуск для проверки что всё работает:

```bash
# 1. Скопировать конфиг
cp .env.example .env

# 2. Поднять стек (mosquitto + influxdb + controller + web + grafana)
make up

# 3. Проверить что сервисы живы
docker compose ps
curl http://localhost:8000/health
# Ожидаемый ответ: {"status":"ok","fsm_phase":"RED_BOTH","mode":"adaptive"}

# 4. Открыть дашборд
# http://localhost:5173
```

### Проверка связности

```bash
# MQTT брокер
mosquitto_sub -h 127.0.0.1 -p 1883 -t "corridor/#" -v &

# Controller API
curl http://localhost:8000/state

# Web UI
curl -s http://localhost:5173 | head -5

# Grafana
curl http://localhost:3001/api/health
```

---

## 3. Полная сборка всех сервисов

### 3.1. Core stack + Simulator (без ML)

```bash
# Поднять всё + симулятор с адаптивным режимом
make demo
```

Это запустит:
- **mosquitto** — MQTT-брокер (порт 1883, WS 9001)
- **influxdb** — хранение метрик (порт 8086)
- **controller** — FSM + адаптивный планировщик (порт 8000)
- **web** — React-дашборд (порт 5173)
- **grafana** — графики (порт 3001)
- **simulator** — генератор трафика (сценарий `asymmetric`)

### 3.2. Core stack + ML-сервис (с видео)

```bash
# Положить видео в services/ml/data/
cp "4K Video of Highway Traffic!.mp4" services/ml/data/cam_A_in.mp4

# Поднять с ML-профилем
docker compose --profile ml up -d --build
```

### 3.3. Всё вместе (core + sim + ml)

```bash
make up-all
```

---

## 4. Проверка ML-пайплайна на видео

### 4.1. Визуальный демо (с GUI)

```bash
python scripts/demo_video_pipeline.py --video "4K Video of Highway Traffic!.mp4"
```

Что проверить:
- [ ] Окно OpenCV открывается
- [ ] Зелёные рамки вокруг машин (car, truck, bus, motorcycle)
- [ ] Жёлтая линия пересечения по центру кадра
- [ ] Счётчики IN/OUT увеличиваются при пересечении линии
- [ ] FPS > 5 на CPU (> 25 на GPU)

Управление: `Q` — выход, `SPACE` — пауза, `R` — сброс счётчиков.

### 4.2. Headless-режим (JSON-отчёт)

```bash
python scripts/run_ml_headless.py \
  --video "4K Video of Highway Traffic!.mp4" \
  --max-frames 500 \
  --skip 2
```

Результат в `results/`:
- `ml_report.json` — сводка (FPS, количество пересечений, классы)
- `crossings.csv` — каждое событие с таймстемпом
- `stats.json` — разбивка по классам

### 4.3. Скриншоты для презентации

```bash
python scripts/generate_snapshots.py \
  --video "4K Video of Highway Traffic!.mp4" \
  --count 5
```

Результат: `results/snapshots/snapshot_01_frame*.jpg` — кадры с детекциями.

### 4.4. Проверка на GPU (если есть)

```bash
python scripts/demo_video_pipeline.py \
  --video "4K Video of Highway Traffic!.mp4" \
  --device cuda:0 \
  --conf 0.4
```

---

## 5. Интеграционная проверка

### 5.1. ML → MQTT → Controller (полная цепочка)

```bash
# Терминал 1: поднять инфраструктуру
docker compose up -d mosquitto controller influxdb web grafana

# Терминал 2: подписаться на MQTT (наблюдение)
mosquitto_sub -h 127.0.0.1 -p 1883 -t "corridor/#" -v

# Терминал 3: запустить ML с публикацией
python scripts/demo_video_pipeline.py \
  --video "4K Video of Highway Traffic!.mp4" \
  --publish \
  --mqtt-host 127.0.0.1 \
  --loop
```

Что проверить:
- [ ] В терминале 2 появляются сообщения `corridor/cam/A/in/event`
- [ ] Controller меняет фазу: `curl http://localhost:8000/state` показывает `phase: GREEN_A`
- [ ] Web-дашборд (http://localhost:5173) отображает счётчики и фазу
- [ ] Grafana (http://localhost:3001) показывает графики throughput

### 5.2. Автоматические интеграционные тесты

```bash
# Поднять стек
docker compose up -d

# Запустить тесты
cd tests/integration
pytest -v
```

Тесты проверяют:
- `test_basic_flow.py` — базовый цикл FSM
- `test_safety_clear_zone.py` — зона не переключается пока не пуста
- `test_emergency_override.py` — приоритет спецтранспорта
- `test_camera_lost.py` — fallback при потере камеры
- `test_baseline_vs_adaptive.py` — adaptive лучше baseline

### 5.3. Unit-тесты сервисов

```bash
make test
# или по отдельности:
cd services/controller && pytest -q
cd services/ml && pytest -q
cd services/simulator && pytest -q
cd web && npm test -- --run
```

---

## 6. Чек-лист соответствия кейсу

### Основные требования кейса

| # | Требование | Реализация | Как проверить |
|---|-----------|-----------|---------------|
| 1 | Детекция транспорта на видео | YOLOv8n, классы: car, motorcycle, bus, truck | `python scripts/demo_video_pipeline.py --video ...` |
| 2 | Подсчёт машин (вход/выход из зоны) | ByteTrack + virtual line crossing | Счётчики IN/OUT в GUI и `results/ml_report.json` |
| 3 | Адаптивное управление светофором | FSM с приоритетной формулой | `make demo` → переключить mode → очередь рассасывается |
| 4 | Безопасность: зона не пуста → не переключать | `inside_A + inside_B > 0` блокирует переход | Сценарий `stuck_vehicle` / тест `test_safety_clear_zone.py` |
| 5 | Приоритет спецтранспорта | Emergency override через MQTT/API | Кнопка в UI / тест `test_emergency_override.py` |
| 6 | Fallback при потере камеры | Heartbeat timeout → RED_BOTH + alert | Сценарий `lost_camera` / тест `test_camera_lost.py` |
| 7 | Дашборд оператора | React + WebSocket + MQTT-over-WS | http://localhost:5173 |
| 8 | Метрики и аналитика | InfluxDB + Grafana | http://localhost:3001 |
| 9 | Сравнение baseline vs adaptive | Бенчмарк-скрипт | `make bench` или `python scripts/bench.py` |
| 10 | ML работает на реальном видео | YOLOv8 + OpenCV на mp4/RTSP | Демо-скрипты в `scripts/` |

### Архитектурные требования

| # | Требование | Статус | Где смотреть |
|---|-----------|--------|-------------|
| 1 | Микросервисная архитектура | 4 сервиса + брокер | `docker-compose.yml` |
| 2 | Асинхронная связь через MQTT | QoS=1, retain | `docs/MQTT.md` |
| 3 | REST API контроллера | FastAPI + WebSocket | `services/controller/app/api.py` |
| 4 | Контейнеризация | Docker + Compose | `services/*/Dockerfile` |
| 5 | Тесты (unit + integration) | pytest + vitest | `make test` |
| 6 | Документация | docs/, MQTT.md, FSM.md, ARCHITECTURE.md | `docs/` |

### Демонстрационные сценарии

| Сценарий | Файл | Что показывает |
|----------|------|---------------|
| Асимметричный поток | `scenarios/asymmetric_peak.py` | Adaptive удлиняет зелёный для перегруженной стороны |
| Застрявшая фура | `scenarios/stuck_vehicle.py` | Система не переключает фазу, alert оператору |
| Скорая помощь | `scenarios/ambulance.py` | Мгновенный приоритет через YELLOW → ALL_RED → GREEN |
| Потеря камеры | `scenarios/lost_camera.py` | Fallback на безопасный режим |
| Showcase (все вместе) | `scenarios/showcase.py` | Полный прогон для жюри |
| Пробка из фур | `scenarios/truck_jam.py` | Учёт длины ТС в планировании |

---

## 7. Сценарии демонстрации

### Сценарий A: Полный демо (5-7 минут, для жюри)

```bash
# 1. Поднять стек
make up

# 2. Запустить showcase-сценарий
make demo-showcase

# 3. Открыть дашборд на проекторе
# http://localhost:5173

# 4. Параллельно показать ML на видео (второй экран)
python scripts/demo_video_pipeline.py \
  --video "4K Video of Highway Traffic!.mp4" \
  --publish --loop --skip 2
```

Порядок демонстрации (см. `docs/DEMO.md`):
1. Baseline — показать проблему (очередь растёт)
2. Adaptive — переключить, очередь рассасывается
3. Безопасность — фура застряла, система не переключает
4. Спецтранспорт — кнопка приоритета
5. ML — показать детекцию на реальном видео

### Сценарий B: Быстрый демо (2-3 минуты)

```bash
make demo-quick
# Открыть http://localhost:5173
# Переключить mode baseline → adaptive
# Показать разницу на графиках
```

### Сценарий C: Только ML (для технических вопросов)

```bash
# Визуальный
python scripts/demo_video_pipeline.py --video "4K Video of Highway Traffic!.mp4"

# Или headless с отчётом
python scripts/run_ml_headless.py --video "4K Video of Highway Traffic!.mp4" --max-frames 300
cat results/ml_report.json
```

### Сценарий D: Без GUI (серверная демонстрация)

```bash
# Всё в Docker
docker compose --profile sim --profile ml up -d --build

# Наблюдение через API
watch -n1 'curl -s http://localhost:8000/state | python -m json.tool'

# Метрики
curl http://localhost:8000/metrics | python -m json.tool
```

---

## 8. Устранение проблем

### Docker не стартует

```bash
# Проверить что Docker Desktop запущен
docker info

# Пересобрать с нуля
make clean
make up
```

### Порт занят

```bash
# Изменить порты в .env
echo "WEB_PORT=5174" >> .env
echo "CONTROLLER_PORT_HOST=8001" >> .env
make restart
```

### ML-модель не скачивается

```bash
# Скачать вручную
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
# Файл появится в текущей директории
```

### MQTT не подключается

```bash
# Проверить брокер
docker compose logs mosquitto

# Запустить локально без Docker
mosquitto -c infra/mosquitto/mosquitto.conf -v
```

### Видео не открывается

```bash
# Проверить что OpenCV видит файл
python -c "import cv2; cap=cv2.VideoCapture('4K Video of Highway Traffic!.mp4'); print(f'OK: {cap.isOpened()}, frames={int(cap.get(5))}')"
```

### Controller не реагирует на ML-события

```bash
# Проверить что события доходят до MQTT
mosquitto_sub -h 127.0.0.1 -t "corridor/cam/#" -v

# Проверить что controller подписан
docker compose logs controller | grep mqtt

# Проверить состояние
curl http://localhost:8000/state
```

### Web-дашборд пустой

```bash
# Проверить CORS
curl -v http://localhost:8000/state

# Проверить WebSocket
# В браузере: DevTools → Network → WS → ws://localhost:8000/ws

# Пересобрать web
docker compose build web
docker compose up -d web
```

### Тесты падают

```bash
# Проверить что стек поднят для интеграционных тестов
docker compose up -d

# Запустить с verbose
pytest tests/integration/ -v --tb=short

# Только unit-тесты (не требуют Docker)
cd services/controller && pytest -q
```

---

## Финальный чек-лист перед демо

- [ ] `make up` — все контейнеры `healthy`
- [ ] http://localhost:5173 — дашборд открывается, данные идут
- [ ] http://localhost:8000/health — `{"status":"ok"}`
- [ ] http://localhost:3001 — Grafana с графиками
- [ ] `make demo-showcase` — сценарий проигрывается, фазы переключаются
- [ ] ML-скрипт запускается: `python scripts/demo_video_pipeline.py --video ...`
- [ ] ML + MQTT: события доходят до controller (проверить `/state`)
- [ ] Кнопка «Скорая» в UI работает
- [ ] Переключение baseline/adaptive видно на графиках
- [ ] `make test` — все тесты зелёные
- [ ] Видео в .gitignore (не коммитится)
- [ ] `.env` создан из `.env.example`
- [ ] Запасной план: `docs/demo_fallback.mp4` готов (см. `docs/RISKS.md`)
