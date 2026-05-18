#!/usr/bin/env python3
"""Plot baseline vs adaptive metrics produced by ``scripts/bench.py``.

Reads every ``*.csv`` inside a run directory and emits side-by-side PNGs:
  * throughput vs time
  * queue length vs time
  * average delay vs time
  * a single bar chart of mean throughput per mode

Usage
-----

.. code-block:: bash

    python scripts/plot_results.py runs/20260518T120000Z
    python scripts/plot_results.py runs/20260518T120000Z --out figures/
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

try:
    import matplotlib  # type: ignore

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise SystemExit("matplotlib is required (pip install matplotlib)") from exc


def _read(csv_path: Path) -> list[dict[str, Any]]:
    with csv_path.open() as fh:
        return [
            {k: (float(v) if v not in ("", None) and k not in ("mode", "scenario", "phase") else v) for k, v in row.items()}
            for row in csv.DictReader(fh)
        ]


def _series(rows: list[dict[str, Any]], key: str) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    if not rows:
        return xs, ys
    t0 = float(rows[0]["ts"])
    for r in rows:
        v = r.get(key)
        if isinstance(v, (int, float)):
            xs.append(float(r["ts"]) - t0)
            ys.append(float(v))
    return xs, ys


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def plot_run(run_dir: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csvs = sorted(run_dir.glob("*.csv"))
    if not csvs:
        raise SystemExit(f"no CSVs in {run_dir}")

    by_scenario: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for path in csvs:
        try:
            scenario, mode = path.stem.split("__", 1)
        except ValueError:
            continue
        rows = _read(path)
        by_scenario.setdefault(scenario, {})[mode] = rows

    written: list[Path] = []
    summary_means: dict[str, dict[str, float]] = {}

    for scenario, modes in by_scenario.items():
        # One figure per metric, two lines (baseline, adaptive)
        for metric, ylabel in [
            ("throughput", "throughput (veh/5min)"),
            ("queue", "queue length"),
            ("avg_delay", "avg delay (s)"),
        ]:
            fig, ax = plt.subplots(figsize=(8, 4.5))
            for mode, rows in modes.items():
                # Sum A+B for the headline view.
                xs_a, ys_a = _series(rows, f"{metric}_A")
                _xs_b, ys_b = _series(rows, f"{metric}_B")
                if not xs_a:
                    continue
                if len(ys_b) == len(ys_a):
                    combined = [a + b for a, b in zip(ys_a, ys_b)]
                else:
                    combined = ys_a
                ax.plot(xs_a, combined, label=mode, linewidth=1.6)
                if metric == "throughput":
                    summary_means.setdefault(scenario, {})[mode] = _mean(combined)
            ax.set_title(f"{scenario}: {metric.replace('_', ' ')}")
            ax.set_xlabel("time since start (s)")
            ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.3)
            ax.legend()
            out_path = out_dir / f"{scenario}_{metric}.png"
            fig.tight_layout()
            fig.savefig(out_path, dpi=120)
            plt.close(fig)
            written.append(out_path)

    # Headline bar chart
    if summary_means:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        scenarios = sorted(summary_means)
        modes = sorted({m for d in summary_means.values() for m in d})
        width = 0.35
        for i, mode in enumerate(modes):
            xs = [j + (i - (len(modes) - 1) / 2) * width for j in range(len(scenarios))]
            ys = [summary_means[s].get(mode, 0.0) for s in scenarios]
            ax.bar(xs, ys, width=width, label=mode)
        ax.set_xticks(range(len(scenarios)))
        ax.set_xticklabels(scenarios, rotation=15)
        ax.set_ylabel("mean total throughput (veh/5min)")
        ax.set_title("Mean throughput by mode")
        ax.grid(True, axis="y", alpha=0.3)
        ax.legend()
        out_path = out_dir / "summary_throughput.png"
        fig.tight_layout()
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        written.append(out_path)

    return written


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_dir", type=Path)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    if not args.run_dir.is_dir():
        raise SystemExit(f"not a directory: {args.run_dir}")
    out_dir = args.out or (args.run_dir / "figures")
    written = plot_run(args.run_dir, out_dir)
    for w in written:
        print(w)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
