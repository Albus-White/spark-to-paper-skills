#!/usr/bin/env python3
"""Scan the project's code for expected artifact types (reproducibility aid).

Heuristically scans `input/code/` (and `code/` if present) for the artifact
categories a reproducible paper should have: preprocessing, feature extraction,
model definitions, baseline definitions, training, evaluation, table/figure
generation, and config/commands. Writes
`outputs/reports/CODE_PAPER_CONSISTENCY_SCAN.md`.

This is an AID for the Code-Paper Consistency / Code Artifact Completeness audits
(SKILL Step 5). It does NOT judge semantic correctness and never edits anything
outside `outputs/reports/`. Stdlib only; relative paths only.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.getcwd()  # workspace root (SKILL.md contract: run from the dir holding paper_config.yaml)

CODE_DIRS = ["input/code", "code"]
OUTPUT_REL = "outputs/reports/CODE_PAPER_CONSISTENCY_SCAN.md"

# category -> keywords matched against the lowercased relative path
CATEGORIES = {
    "preprocessing": ("preprocess", "prepare", "data_prep", "prep_", "clean"),
    "feature extraction": ("feature", "extract", "embed", "encode"),
    "model definitions": ("model", "net", "arch", "module"),
    "baseline definitions": ("baseline", "ref_", "reference_model"),
    "training script": ("train", "fit", "optimize"),
    "evaluation script": ("eval", "evaluate", "test", "metric", "score"),
    "table/figure generation": ("table", "figure", "plot", "viz", "make_fig", "report"),
    "config / commands": ("config", ".yaml", ".yml", ".toml", ".cfg", "args", "readme", "makefile", ".sh"),
}

CODE_EXTS = (".py", ".ipynb", ".r", ".m", ".sh", ".yaml", ".yml", ".toml",
             ".cfg", ".json", ".md", ".txt", ".lua", ".jl", ".cpp", ".java")


def collect_code_files() -> tuple[str, list[str]]:
    for rel in CODE_DIRS:
        abs_dir = os.path.join(REPO_ROOT, rel)
        if not os.path.isdir(abs_dir):
            continue
        found: list[str] = []
        for root, _dirs, names in os.walk(abs_dir):
            if ".git" in root.split(os.sep):
                continue
            for name in names:
                if name == ".gitkeep":
                    continue
                if name.lower().endswith(CODE_EXTS) or os.path.splitext(name)[1] == "":
                    found.append(os.path.relpath(os.path.join(root, name), REPO_ROOT))
        return rel, sorted(found)
    return CODE_DIRS[0], []


def categorize(files: list[str]) -> dict:
    result = {cat: [] for cat in CATEGORIES}
    for f in files:
        low = f.lower()
        for cat, keys in CATEGORIES.items():
            if any(k in low for k in keys):
                result[cat].append(f)
    return result


def main() -> int:
    code_dir, files = collect_code_files()
    cats = categorize(files)
    generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Code-Paper Consistency Scan",
        "",
        f"_Generated: {generated}_",
        f"_Scanned: `{code_dir}/`_",
        "",
        "_Filename-heuristic aid for the Code-Paper Consistency and Code Artifact "
        "Completeness audits. Presence is necessary, not sufficient — confirm by reading "
        "the code that each paper-described component is actually implemented._",
        "",
    ]
    if not files:
        lines.append(f"No code files found under `{code_dir}/`.")
    else:
        lines.append(f"Found **{len(files)}** code file(s).")
        lines.append("")
        lines.append("| Artifact category | Present? | Matching files |")
        lines.append("|-------------------|----------|----------------|")
        for cat in CATEGORIES:
            hits = cats[cat]
            present = "yes" if hits else "**MISSING?**"
            shown = ", ".join(f"`{h}`" for h in hits[:5])
            if len(hits) > 5:
                shown += f", … (+{len(hits) - 5})"
            lines.append(f"| {cat} | {present} | {shown} |")
        missing = [c for c in CATEGORIES if not cats[c]]
        lines.append("")
        if missing:
            lines.append("**Potential reproducibility gaps (no filename match):** "
                         + ", ".join(missing) + ". Verify manually.")
        else:
            lines.append("All artifact categories have at least one filename match (verify contents).")
    lines.append("")

    out_path = os.path.join(REPO_ROOT, OUTPUT_REL)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"Code scan ({len(files)} file(s)) -> {os.path.relpath(out_path, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
