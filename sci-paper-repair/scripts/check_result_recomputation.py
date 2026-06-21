#!/usr/bin/env python3
"""Aggregate per-seed raw logs to assist result recomputation (GR-019).

Scans `workspace/experiments/` and `outputs/` for CSV/JSON metric files. When a
`seed` field is present, it groups numeric metrics by seed and reports the
per-metric mean/std across seeds. This is an AID for the Result Provenance Audit
(SKILL Step 5) — it helps confirm that reported table/figure values can be
recomputed from raw logs. It does NOT edit the manuscript and writes only to
`outputs/reports/RESULT_RECOMPUTATION_CHECK.md`.

Stdlib only; relative paths only; robust to missing/malformed files.
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.getcwd()  # workspace root (SKILL.md contract: run from the dir holding paper_config.yaml)

SCAN_DIRS = ["workspace/experiments", "outputs"]
OUTPUT_REL = "outputs/reports/RESULT_RECOMPUTATION_CHECK.md"
SEED_KEYS = ("seed", "Seed", "SEED", "random_seed")


def _is_number(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _seed_of(row: dict):
    for k in SEED_KEYS:
        if k in row:
            return row[k]
    return None


def _rows_from_file(path: str) -> list[dict]:
    """Return a list of flat dict rows from a CSV or JSON file (best effort)."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".csv":
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
                return list(csv.DictReader(fh))
        if ext == ".json":
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
            if isinstance(data, dict):
                # dict of metric->value, or nested {seed: {metric: value}}
                if all(isinstance(v, dict) for v in data.values()) and data:
                    out = []
                    for seed, metrics in data.items():
                        row = {"seed": seed}
                        row.update(metrics)
                        out.append(row)
                    return out
                return [data]
    except (OSError, ValueError):
        return []
    return []


def _aggregate(rows: list[dict]) -> dict:
    """metric -> {n, mean, std, by_seed} for numeric columns."""
    metrics: dict[str, list[float]] = {}
    by_seed: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        seed = _seed_of(row)
        for k, v in row.items():
            if k in SEED_KEYS or not _is_number(v):
                continue
            metrics.setdefault(k, []).append(float(v))
            if seed is not None:
                by_seed.setdefault(str(seed), {}).setdefault(k, []).append(float(v))
    out = {}
    for k, vals in metrics.items():
        out[k] = {
            "n": len(vals),
            "mean": statistics.fmean(vals) if vals else None,
            "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
            "seeds": sorted(by_seed.keys()),
        }
    return out


def main() -> int:
    files: list[str] = []
    for rel in SCAN_DIRS:
        abs_dir = os.path.join(REPO_ROOT, rel)
        if not os.path.isdir(abs_dir):
            continue
        for root, _dirs, names in os.walk(abs_dir):
            for name in names:
                if name.lower().endswith((".csv", ".json")):
                    files.append(os.path.join(root, name))
    files.sort()

    generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Result Recomputation Check",
        "",
        f"_Generated: {generated}_",
        "",
        "_Aid for the Result Provenance Audit (GR-019): per-seed aggregation of raw "
        "logs. Confirm each reported table/figure value matches these recomputed values._",
        "",
    ]
    if not files:
        lines.append("No CSV/JSON metric files found under " + ", ".join(SCAN_DIRS) + ".")
    else:
        lines.append(f"Found **{len(files)}** metric file(s).")
        for path in files:
            rel = os.path.relpath(path, REPO_ROOT)
            rows = _rows_from_file(path)
            agg = _aggregate(rows) if rows else {}
            lines.append("")
            lines.append(f"## `{rel}`")
            if not agg:
                lines.append("- (no numeric metrics detected)")
                continue
            lines.append("")
            lines.append("| Metric | n | mean | std | seeds |")
            lines.append("|--------|---|------|-----|-------|")
            for metric, a in sorted(agg.items()):
                mean = "" if a["mean"] is None else f"{a['mean']:.6g}"
                std = f"{a['std']:.3g}"
                seeds = ",".join(a["seeds"]) if a["seeds"] else "-"
                lines.append(f"| {metric} | {a['n']} | {mean} | {std} | {seeds} |")
    lines.append("")

    out_path = os.path.join(REPO_ROOT, OUTPUT_REL)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"Recomputation aid for {len(files)} file(s) -> {os.path.relpath(out_path, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
