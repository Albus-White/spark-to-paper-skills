#!/usr/bin/env python3
"""Collect result files into an index.

Scans `workspace/experiments/` and `outputs/` for result-like files
(CSV, JSON, TXT, LOG) and writes a Markdown index to
`outputs/reports/RESULT_FILE_INDEX.md`.

Simple and robust: no external dependencies, never fails the whole run on a
single unreadable file.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

# Repository root = three levels up from this script
# (.claude/skills/sci-paper-repair/scripts/collect_results.py)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

SCAN_DIRS = ["workspace/experiments", "outputs"]
RESULT_EXTS = {".csv", ".json", ".txt", ".log"}
OUTPUT_REL = "outputs/reports/RESULT_FILE_INDEX.md"


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}PB"


def find_result_files() -> list[dict]:
    found: list[dict] = []
    for rel_dir in SCAN_DIRS:
        abs_dir = os.path.join(REPO_ROOT, rel_dir)
        if not os.path.isdir(abs_dir):
            continue
        for root, _dirs, files in os.walk(abs_dir):
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext not in RESULT_EXTS:
                    continue
                abs_path = os.path.join(root, name)
                rel_path = os.path.relpath(abs_path, REPO_ROOT)
                try:
                    stat = os.stat(abs_path)
                    size = human_size(stat.st_size)
                    mtime = datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M UTC")
                except OSError:
                    size, mtime = "?", "?"
                found.append(
                    {"path": rel_path, "ext": ext, "size": size, "mtime": mtime}
                )
    found.sort(key=lambda d: d["path"])
    return found


def write_index(files: list[dict]) -> str:
    out_path = os.path.join(REPO_ROOT, OUTPUT_REL)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Result File Index",
        "",
        f"_Generated: {generated}_",
        f"_Scanned: {', '.join(SCAN_DIRS)}_",
        "",
    ]
    if not files:
        lines.append("No result files (.csv, .json, .txt, .log) found yet.")
    else:
        lines.append(f"Found **{len(files)}** result file(s).")
        lines.append("")
        lines.append("| File | Type | Size | Modified |")
        lines.append("|------|------|------|----------|")
        for f in files:
            lines.append(
                f"| `{f['path']}` | {f['ext']} | {f['size']} | {f['mtime']} |"
            )
    lines.append("")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return out_path


def main() -> int:
    files = find_result_files()
    out_path = write_index(files)
    rel_out = os.path.relpath(out_path, REPO_ROOT)
    print(f"Indexed {len(files)} result file(s) -> {rel_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
