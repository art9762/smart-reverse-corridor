# MQTT топики (контракт между сервисами)

QoS=1, retain — где указано.

## Камеры → Контроллер

### `corridor/cam/<side>/<dir>/event`
`side` ∈ {A, B}, `dir` ∈ {in, out}

```json
{
  "event_id": "82567ef097864d8ebc58664ddf5084a1a",
  "ts": 1715789123.456,
  "track_id": 42,
  "class": "car|truck|bus|motorcycle|emergency",
  "side": "A",
  "dir": "in",
  "confidence": 0.91,
  "plate": null
}
```

`event_id` — уникальный идентификатор одного пересечения линии. Симулятор и ML publisher
создают UUID для каждого нового события; при повторной отправке того же события нужно сохранить
этот ID (в ML publisher можно передать `event_id=`). Не используйте один ID для разных пересечений,
даже если `track_id` и время симуляции совпали после перезапуска.

Контроллер отбрасывает повторные доставки QoS=1 до изменения счётчиков, метрик и журнала.
Ключ включает сторону камеры, направление и `event_id`. Для старых отправителей без `event_id`
используется комбинация темы, `track_id` и `ts`; повторное использование всей этой комбинации
после перезапуска старого отправителя может быть принято за повторную доставку.

`track_id` должен быть целым числом ≥ 0, `ts` — конечным числом ≥ 0. Если payload содержит
`side`/`dir`, они должны совпадать с темой. Некорректное событие не изменяет состояние и попадает
в диагностический лог. Пустой или слишком длинный `event_id` (более 128 символов) отклоняется.

Память повторов ограничена 10 минутами с момента первого получения и 10 000 событиями; она
очищается при перезапуске контроллера и `/test/reset`. Это защита программного прототипа от
недавних повторов, а не гарантия exactly-once, восстановления после сбоев или пригодности для
реального управления дорожным движением.

### `corridor/cam/<side>/<dir>/heartbeat` (retain=true, каждую 1с)
```json
{"ts": 1715789123.0, "camera_id": "A_in", "fps": 24.7, "healthy": true}
```

## Симулятор → UI (live world snapshot)

### `corridor/sim/world` (qos=0, 10–20 Hz, не retain)
Источник картинки для `web/`. Контроллер этот топик НЕ читает (он принимает решения только по CV-событиям).

```json
{
  "ts": 1715789123.456,
  "zone_length_m": 800,
  "phase": "GREEN_A",
  "vehicles": [
    {"id": 42, "side": "A", "type": "car",   "x": 0.31, "y": 0.0, "speed": 13.4, "len_m": 4.5, "emergency": false},
    {"id": 43, "side": "A", "type": "truck", "x": 0.18, "y": 0.0, "speed": 9.8,  "len_m": 12.0, "emergency": false},
    {"id": 44, "side": "B", "type": "car",   "x": 0.92, "y": 0.0, "speed": 0.0,  "len_m": 4.5, "emergency": false}
  ],
  "queues": {"A": 7, "B": 12}
}
```

- `x` — нормализованная позиция в зоне коридора [0..1]; 0 — въезд со стороны A, 1 — въезд со стороны B.
- `y` — оффсет от центра полосы (резерв, для будущих manuevers).
- `side` — направление движения (A→B или B→A).

## Контроллер → UI/Grafana

### `corridor/state` (retain=true)
```json
{
  "phase": "GREEN_A",
  "phase_started_at": 1715789120.0,
  "phase_planned_end_at": 1715789200.0,
  "inside_A": 3,
  "inside_B": 0,
  "queue_A": 7,
  "queue_B": 12,
  "mode": "adaptive",
  "camera_health": {"A_in": true, "A_out": true, "B_in": true, "B_out": false}
}
```

### `corridor/metrics/tick` (1 Hz)
```json
{
  "ts": 1715789123.0,
  "throughput_5min": {"A": 412, "B": 388},
  "avg_delay_5min": {"A": 18.4, "B": 23.1},
  "queue": {"A": 7, "B": 12},
  "max_queue_today": {"A": 24, "B": 31}
}
```

### `corridor/alerts`
```json
{"ts":0, "level":"emergency|warning|info", "code":"STUCK_VEHICLE|CAMERA_LOST|EMERGENCY_OVERRIDE", "detail":"..."}
```

## UI/оператор → Контроллер

### `corridor/cmd/override`
```json
{"action": "force_phase", "phase": "GREEN_B", "reason": "ambulance", "by": "operator-1"}
```
