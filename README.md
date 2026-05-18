# Умный реверсивный коридор 🚦

> Адаптивное управление фазами светофоров на основе сквозного контроля транспортного потока.
>
> Кейс ИТ-чемпионата **«Цифровая Эра Транспорта» 2026** (школьники).

## TL;DR

На двухполосной дороге одна полоса перекрыта на 0.5–2 км. Светофоры по краям пускают трафик «то туда, то обратно».
Классика — фиксированный таймер «3 минуты в каждую сторону». Минусы: лобовые ДТП при преждевременной смене фазы, очереди в час пик, простой пустой полосы, длинные фуры не успевают.

**Наше решение:**
1. CV-камеры на въезде/выезде каждой стороны считают и трекают каждое ТС (YOLO + ByteTrack).
2. Конечный автомат разрешает смену фазы **только когда зона ремонта пуста** (`enter_A == exit_A` и `enter_B == exit_B`).
3. Длительность зелёного — адаптивная, по приоритету: длина очереди + время красного + наличие фуры/спецтранспорта.
4. Аварийные режимы: застревание ТС > 30 с, потеря камеры (fallback на детектор/таймер), ручной приоритет для скорой.
5. Веб-дашборд + симулятор для демо «до/после».

## Архитектура (кратко)

```
[ Камеры/видео ] -> [ ML/CV сервис (YOLO+ByteTrack) ] --MQTT--> [ Контроллер фаз (FSM) ] --REST/WS--> [ Web UI ]
                                                                       |
                                                              [ InfluxDB / SQLite ]
                                                                       |
                                                                  [ Grafana ]

[ Симулятор трафика (Pygame/SUMO-bridge) ] --MQTT (тот же топик)--> контроллер
```

Подробно — [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Стек

| Слой | Технологии |
|---|---|
| ML/CV | Python 3.11, PyTorch, Ultralytics YOLOv8n, ByteTrack, OpenCV |
| Backend / FSM | Python 3.11, FastAPI, paho-mqtt, transitions (FSM), SQLAlchemy |
| Брокер | Eclipse Mosquitto (MQTT) |
| Хранилище метрик | InfluxDB 2 + SQLite (события) |
| Симулятор | Python + Pygame, опционально SUMO/TraCI |
| Frontend | React + Vite + TypeScript, Tailwind, Recharts, MQTT.js (через WS) |
| DevOps | Docker Compose, GitHub Actions, Makefile |

## Быстрый старт

```bash
git clone https://github.com/art9762/smart-reverse-corridor.git
cd smart-reverse-corridor
cp .env.example .env
make up        # поднимает mosquitto, influxdb, controller, ml, web
make demo      # запускает симулятор и открывает дашборд
```

Открой: <http://localhost:5173>.

## Структура репозитория

```
smart-reverse-corridor/
├── docs/                  # ARCHITECTURE, FSM, MQTT topics, Demo script
├── services/
│   ├── controller/        # FSM, адаптивный планировщик, REST/WS API
│   ├── ml/                # YOLO + ByteTrack, MQTT-publisher
│   └── simulator/         # Pygame-симулятор дороги
├── web/                   # React-дашборд
├── infra/                 # docker-compose, mosquitto.conf, grafana, influx
├── scripts/               # demo, генерация датасета, утилиты
├── tests/                 # юнит + интеграционные
└── .github/workflows/     # CI: lint, test, build
```

## Метрики «до/после»

- Средняя задержка на сторону (с)
- Максимальная длина очереди (авто)
- Throughput (авто/час)
- Количество преждевременных смен фазы (потенциальные ДТП)
- Время реакции на спецтранспорт

## Демо-сценарии

1. **Симметричный поток** (baseline vs adaptive).
2. **Асимметричный поток** (час пик с одной стороны).
3. **Фура внутри зоны** (длинное ТС не успевает за фиксированный таймер).
4. **Скорая помощь** (приоритет, мгновенное переключение).
5. **Потеря связи с камерой** (fallback на безопасный таймер).
6. **Застревание ТС** (emergency stop, вызов оператора).

## Команда и роли

См. [`docs/ROLES.md`](docs/ROLES.md).

## Лицензия

MIT (для хакатона).
