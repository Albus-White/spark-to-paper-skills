#!/usr/bin/env python3
"""Scan the manuscript for risky terms.

A simple, line-based text scanner (NOT a semantic checker). It searches the
manuscript for risky words/phrases that often signal overclaiming, and writes
warnings to `outputs/reports/RISKY_CLAIM_SCAN.md`.

The manuscript source of truth is `./paper/`. With no argument, this scans every
`.tex` file under `./paper/`. You may also pass an explicit file path.

Usage:
    python consistency_check.py [path/to/file.tex]
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

PAPER_DIR = "paper"
OUTPUT_REL = "outputs/reports/RISKY_CLAIM_SCAN.md"

# Risky terms -> why they are risky.
RISKY_TERMS = {
    "significant": "Implies statistical significance; requires a statistical test (GR-006).",
    "significantly": "Requires statistical testing or repeated-run evidence (GR-006).",
    "robust": "Requires robustness evidence (GR-005).",
    "generalize": "Requires cross-dataset / external-test evidence (GR-005).",
    "generalizes": "Requires cross-dataset / external-test evidence (GR-005).",
    "prove": "Experiments support, they rarely prove. Use cautious wording.",
    "proves": "Experiments support, they rarely prove. Use cautious wording.",
    "state-of-the-art": "Needs a fair, scoped comparison to current best methods.",
    "universally": "Absolute claim; scope to tested conditions.",
    "extensive experiments": "Avoid if experiments are limited.",
}


def resolve_targets(argv: list[str]) -> list[str]:
    """Return the list of files to scan (absolute paths)."""
    if len(argv) > 1:
        cand = argv[1]
        cand = cand if os.path.isabs(cand) else os.path.join(REPO_ROOT, cand)
        return [cand] if os.path.isfile(cand) else []
    # Default: every .tex file under ./paper/ (the manuscript source of truth).
    paper_abs = os.path.join(REPO_ROOT, PAPER_DIR)
    found: list[str] = []
    if os.path.isdir(paper_abs):
        for root, _dirs, files in os.walk(paper_abs):
            if ".git" in root.split(os.sep):
                continue
            for name in files:
                if name.lower().endswith(".tex"):
                    found.append(os.path.join(root, name))
    return sorted(found)


def scan(path: str) -> list[dict]:
    hits: list[dict] = []
    # Build one regex per term (word-ish boundaries, case-insensitive).
    patterns = {
        term: re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", re.IGNORECASE)
        for term in RISKY_TERMS
    }
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, start=1):
            for term, pat in patterns.items():
                if pat.search(line):
                    hits.append(
                        {
                            "file": os.path.relpath(path, REPO_ROOT),
                            "line": lineno,
                            "term": term,
                            "reason": RISKY_TERMS[term],
                            "text": line.strip(),
                        }
                    )
    return hits


def write_report(targets: list[str], hits: list[dict]) -> str:
    out_path = os.path.join(REPO_ROOT, OUTPUT_REL)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = ["# Risky Claim Scan", "", f"_Generated: {generated}_", ""]
    lines.append(
        "_This is a simple keyword warning tool, not a semantic checker. "
        "Each hit is a prompt to verify the claim against evidence, not proof of error._"
    )
    lines.append("")

    if not targets:
        lines.append(
            "**No manuscript files found.** Looked for `.tex` files under "
            f"`{PAPER_DIR}/` (or pass an explicit file path)."
        )
        lines.append("")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        return out_path

    scanned = ", ".join(f"`{os.path.relpath(t, REPO_ROOT)}`" for t in targets)
    lines.append(f"_Scanned {len(targets)} file(s): {scanned}_")
    lines.append("")

    if not hits:
        lines.append("No risky terms found.")
    else:
        lines.append(f"Found **{len(hits)}** risky-term occurrence(s).")
        lines.append("")
        lines.append("| File | Line | Term | Why risky | Context |")
        lines.append("|------|------|------|-----------|---------|")
        for h in hits:
            ctx = h["text"].replace("|", "\\|")
            if len(ctx) > 120:
                ctx = ctx[:117] + "..."
            lines.append(
                f"| `{h['file']}` | {h['line']} | `{h['term']}` | {h['reason']} | {ctx} |"
            )
    lines.append("")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return out_path


def main(argv: list[str]) -> int:
    targets = resolve_targets(argv)
    hits: list[dict] = []
    for t in targets:
        hits.extend(scan(t))
    out_path = write_report(targets, hits)
    rel_out = os.path.relpath(out_path, REPO_ROOT)
    if not targets:
        print(f"No manuscript files found under {PAPER_DIR}/. Wrote notice -> {rel_out}")
    else:
        print(f"Scanned {len(targets)} file(s): {len(hits)} risky-term hit(s) -> {rel_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
