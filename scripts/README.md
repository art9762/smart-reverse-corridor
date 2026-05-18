# Helper scripts

This directory holds developer-facing helpers, not production code.

| Script | What it does |
| --- | --- |
| `bench.py` | Drives a running stack with synthetic traffic, dumps per-mode CSVs into `runs/<timestamp>/`. |
| `plot_results.py` | Renders comparison PNGs (throughput, queue, delay) from a `runs/<timestamp>/` directory. |
| `seed_videos.sh` | Documented NO-OP that prints commands to fetch public test videos for the ML pipeline. Read before running. |

## Typical loop

```bash
# 1) Start mosquitto + controller (e.g. via docker compose).
# 2) Run a 10-minute bench on the asymmetric scenario.
python scripts/bench.py --duration 600 --scenario asymmetric

# 3) Plot.
python scripts/plot_results.py runs/<timestamp>
```

Integration tests for the same flows live in `tests/integration/` and run as
`pytest -m integration` (see `tests/requirements.txt`).
