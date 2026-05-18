# Роли в команде (рекомендация на 4-5 человек)

| Роль | Что делает | Где живёт код |
|---|---|---|
| Architect / Tech Lead | Архитектура, контракты, презентация | `docs/`, `README.md` |
| Backend / FSM | Контроллер фаз, REST/WS, метрики | `services/controller/` |
| ML / CV | YOLO + ByteTrack, MQTT-публикация событий | `services/ml/` |
| Simulator / QA | Pygame-симулятор, демо-сценарии, тесты | `services/simulator/`, `tests/` |
| Frontend | React-дашборд, графики, визуализация | `web/` |
| DevOps (опционально) | Docker Compose, CI, Grafana | `infra/`, `.github/` |

Если команда меньше — Frontend часто совмещают с Architect, а DevOps уходит к Backend.
