# Конечный автомат контроллера фаз

## Состояния

- `INIT` — старт
- `RED_BOTH` — обе стороны красный (страховой режим / ночь / авария)
- `GREEN_A` — зелёный для стороны A, красный для B
- `YELLOW_A` — жёлтый A, красный B
- `ALL_RED_AFTER_A` — обе красные, ждём, пока зона освободится (`inside_A == 0` и `inside_B == 0`) + `ALL_RED_GUARD_S`
- `GREEN_B` — зеркально
- `YELLOW_B`
- `ALL_RED_AFTER_B`
- `EMERGENCY_STOP` — застревание/потеря камер/manual stop

## Переходы

```
INIT --> RED_BOTH --> GREEN_A
GREEN_A --[planned end OR queue_A==0 too long]--> YELLOW_A --[YELLOW_S]--> ALL_RED_AFTER_A
ALL_RED_AFTER_A --[zone empty + ALL_RED_GUARD_S elapsed]--> GREEN_B
GREEN_B --> YELLOW_B --> ALL_RED_AFTER_B --> GREEN_A
any --[STUCK / CAMERA_LOST_BOTH / manual]--> EMERGENCY_STOP
EMERGENCY_STOP --[operator resume]--> RED_BOTH
```

## Расчёт длительности зелёного

```
T_green = clamp(
  base + a * queue_side + b * wait_other - c * (1 if other_side_empty else 0),
  GREEN_MIN_S, GREEN_MAX_S
)
```

## Безопасность переключения

Из `YELLOW_*` в `GREEN_*` переход возможен **только** если:
1. `inside_A == 0 AND inside_B == 0` (счётчики на основе CV-событий).
2. Прошло не меньше `ALL_RED_GUARD_S` секунд после жёлтого.
3. Если за `CLEAR_TIMEOUT_S` зона не очистилась — `EMERGENCY_STOP` + alert.

## Аварийные режимы

- **STUCK_VEHICLE:** разница `enter - exit` на стороне держится > `STUCK_THRESHOLD_S` секунд → emergency.
- **CAMERA_LOST:** нет heartbeat от камеры > 5с. Если потеряна одна — fallback на парную; если обе на одной стороне — `RED_BOTH` + alert.
- **EMERGENCY_OVERRIDE:** оператор нажал «скорая со стороны A» → форсированно `YELLOW_other → ALL_RED → GREEN_A`.
