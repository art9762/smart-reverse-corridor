# services/ml — CV-сервис коридора 🚦📷

YOLOv8n + ByteTrack-lite детект и трекинг ТС на 4 камерах коридора, счёт пересечений виртуальной линии и публикация событий в MQTT.

## Что делает

Каждая из 4 камер (`A_in`, `A_out`, `B_in`, `B_out`) обрабатывается отдельным потоком:

1. `cv2.VideoCapture` читает кадр (MP4 или RTSP).
2. `Detector` (YOLOv8n) отдаёт только классы транспорта: `car`, `motorcycle`, `bus`, `truck`. Опционально HSV-эвристика помечает кадры с синей/красной мигалкой как `emergency`.
3. `ByteTracker` назначает устойчивый `track_id`.
4. `LineCrossingDetector` считает пересечение виртуальной линии (из `app/calibration.json`).
5. `MqttPublisher` публикует событие в `corridor/cam/<side>/<dir>/event` (qos=1) и heartbeat в `corridor/cam/<side>/<dir>/heartbeat` (retain=true, ~1 Hz).

Контракт топиков и payload — строго по `docs/MQTT.md` корня репозитория.

## Структура

```
services/ml/
├── Dockerfile
├── requirements.txt
├── pytest.ini
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py              # точка входа (4 worker-thread)
│   ├── config.py            # ENV → pydantic-settings
│   ├── detector.py          # YOLOv8 wrapper + emergency HSV
│   ├── tracker.py           # ByteTrack-lite (IoU greedy)
│   ├── line_crossing.py     # cross-product side detector
│   ├── publisher.py         # paho-mqtt publisher (event + heartbeat)
│   ├── camera_worker.py     # per-camera thread
│   └── calibration.json     # пример калибровки 4 камер
└── tests/
    ├── test_line_crossing.py
    └── test_detector_smoke.py
```

## Конфиг (ENV)

См. корневой `.env.example`, секция `# === ML/CV ===`. Все переменные опциональны (есть дефолты).

| Переменная | По умолчанию | Что делает |
|---|---|---|
| `ML_MODEL` | `yolov8n.pt` | путь до весов (в Docker `/models/yolov8n.pt`) |
| `ML_CONF` | `0.35` | порог уверенности |
| `ML_IOU` | `0.5` | NMS IoU |
| `ML_DEVICE` | `cpu` | `cpu` или `cuda:0` |
| `ML_IMGSZ` | `640` | размер инференса |
| `ML_VIDEO_A_IN` … | `/data/cam_*.mp4` | путь к видео или RTSP url |
| `ML_LOOP_VIDEO` | `true` | зацикливать MP4 (с reset trackera) |
| `ML_HEARTBEAT_INTERVAL_S` | `1.0` | интервал heartbeat |
| `ML_EMERGENCY_HSV` | `false` | включить HSV-эвристику мигалок |
| `ML_CALIBRATION_PATH` | `/app/app/calibration.json` | калибровка |
| `MQTT_HOST/PORT/USER/PASS` | `mosquitto:1883` | брокер |

## Запуск

### Локально

```bash
cd services/ml
pip install -r requirements.txt
# Тесты (без модели и без видео — мокается)
pytest -q
# Сервис (нужны видео-файлы и MQTT-брокер)
ML_VIDEO_A_IN=./samples/a_in.mp4 \
ML_VIDEO_A_OUT=./samples/a_out.mp4 \
ML_VIDEO_B_IN=./samples/b_in.mp4 \
ML_VIDEO_B_OUT=./samples/b_out.mp4 \
MQTT_HOST=localhost \
ML_CALIBRATION_PATH=./app/calibration.json \
python -m app.main
```

### Docker

```bash
# из корня репозитория
docker build -t corridor-ml services/ml
docker run --rm \
  -e MQTT_HOST=host.docker.internal \
  -e ML_DEVICE=cpu \
  -v $PWD/data:/data \
  corridor-ml
```

В корневом `docker-compose.yml` сервис должен называться `ml` и зависеть от `mosquitto`.

### Калибровка линии

Открой кадр в любом просмотрщике, выбери две точки виртуальной линии. Заполни `app/calibration.json`:

```jsonc
{
  "A_in": {
    "side": "A",
    "dir": "in",
    "line": [[100, 360], [1180, 360]],
    "expected_dir": 1   // +1 если "в зону" = пересечь линию вниз/вправо
  },
  ...
}
```

Знак `expected_dir` определяет, какое пересечение публикуется как `dir=in`, а какое как `dir=out`. Для `*_out` камер логику можно инвертировать.

## Тесты

```bash
cd services/ml
pytest -v
```

Сейчас в наборе:

- `test_line_crossing.py` — 9 тестов на детектор пересечения линии (в обе стороны, диагональная линия, мульти-треки, reset, propagation класса `emergency`).
- `test_detector_smoke.py` — 5 smoke-тестов для `Detector` без реальной модели (мокается `ultralytics.YOLO`).

## Известные ограничения / TODO

- Нужны реальные видеосэмплы 4 камер для интеграционного теста — сейчас тесты не зависят от файлов.
- Эвристика `emergency` по HSV-цвету мигалки очень грубая. Лучше дообучить лёгкий классификатор по краю kit'а или взять сегментацию по полигону. Пока — TODO.
- Трекер — собственный ByteTrack-lite (IoU + greedy). Для сильно перекрывающегося трафика стоит переключить на полный ByteTrack/StrongSort.
- При reset на закольцованном видео `track_id` сдвигается через offset — это безопасно для уникальности, но цифры будут расти (нужно учитывать при долгой работе).
- Пока нет авто-калибровки линии — задаётся вручную через `calibration.json`.
- Метрики (latency, dropped_frames) шлются только косвенно через `fps` в heartbeat.
