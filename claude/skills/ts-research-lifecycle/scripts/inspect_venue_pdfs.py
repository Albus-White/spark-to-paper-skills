#!/usr/bin/env python3
"""Extract auditable PDF observations without making scientific classifications."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


def command(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=180, check=False)
    except FileNotFoundError as exc:
        raise ValueError(f"required executable is unavailable: {args[0]}") from exc
    if result.returncode != 0:
        raise ValueError(f"{' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_numbers(pattern: str, text: str) -> list[str]:
    return sorted(set(re.findall(pattern, text, flags=re.IGNORECASE)), key=lambda value: [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)])


def inspect(pdf: Path) -> dict:
    if not pdf.is_file():
        raise ValueError(f"missing PDF: {pdf}")
    info = command(["pdfinfo", str(pdf)])
    pages_match = re.search(r"^Pages:\s+(\d+)", info, flags=re.MULTILINE)
    if not pages_match:
        raise ValueError(f"pdfinfo did not report pages for {pdf}")
    with tempfile.TemporaryDirectory() as temp:
        text_path = Path(temp) / "paper.txt"
        command(["pdftotext", "-layout", str(pdf), str(text_path)])
        text = text_path.read_text(encoding="utf-8", errors="replace")
    figure_labels = unique_numbers(r"(?:Figure|Fig\.)\s+([A-Z]?\d+[A-Za-z]?)", text)
    table_labels = unique_numbers(r"Table\s+([A-Z]?\d+[A-Za-z]?)", text)
    reference_heading = list(re.finditer(r"^\s*(?:REFERENCES|References|Bibliography)\s*$", text, flags=re.MULTILINE))
    reference_text = text[reference_heading[-1].end():] if reference_heading else ""
    numbered = unique_numbers(r"^\s*\[(\d+)\]\s+", reference_text)
    return {
        "path": str(pdf.resolve()),
        "sha256": sha256(pdf),
        "auto_observations": {
            "page_count": int(pages_match.group(1)),
            "figure_labels": figure_labels,
            "observed_total_figure_labels": len(figure_labels),
            "table_labels": table_labels,
            "observed_table_labels": len(table_labels),
            "numbered_reference_labels": numbered,
            "observed_numbered_reference_count": len(numbered),
        },
        "requires_model_review": [
            "confirm article-only page range and exclude supplements when required",
            "confirm unique cited-reference count under the venue's bibliography style",
            "confirm total figure count, including multi-panel and supplementary policy",
            "classify each figure by its actual scientific role using domain-appropriate labels",
            "count the paper's evaluation units and classify their domain-appropriate kinds",
            "extract evidence dimensions and explain evaluation difficulty from the full paper",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", nargs="+")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        report = {"papers": [inspect(Path(value).resolve()) for value in args.pdf]}
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    rendered = json.dumps({"ok": True, **report}, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
