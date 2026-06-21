#!/usr/bin/env python3
"""Locate the compiled PDF under ./paper/ and report render hints (GR-020).

Compilation success is not enough — the rendered PDF must be visually checked
(SKILL Step 14). This helper finds PDF(s) under `paper/`, reports page count and
size (via `pdfinfo` if available), and tells you how to render pages to images
(via `pdftoppm` if available) for a visual layout check. It writes an aid report
to `outputs/reports/PDF_LAYOUT_SCAN.md` (the human-authored conclusions go in
`PDF_LAYOUT_CHECK.md`).

It does NOT render or commit images and never touches `./paper/`. Stdlib only;
relative paths only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

PAPER_DIR = "paper"
OUTPUT_REL = "outputs/reports/PDF_LAYOUT_SCAN.md"


def find_pdfs() -> list[str]:
    paper_abs = os.path.join(REPO_ROOT, PAPER_DIR)
    found: list[str] = []
    if os.path.isdir(paper_abs):
        for root, _dirs, names in os.walk(paper_abs):
            if ".git" in root.split(os.sep):
                continue
            for name in names:
                if name.lower().endswith(".pdf"):
                    found.append(os.path.join(root, name))
    return sorted(found)


def pdfinfo_pages(pdf_path: str):
    if not shutil.which("pdfinfo"):
        return None
    try:
        out = subprocess.run(
            ["pdfinfo", pdf_path], capture_output=True, text=True, check=True
        ).stdout
        for line in out.splitlines():
            if line.lower().startswith("pages:"):
                return line.split(":", 1)[1].strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return None


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def main() -> int:
    pdfs = find_pdfs()
    have_pdftoppm = bool(shutil.which("pdftoppm"))
    have_pdfinfo = bool(shutil.which("pdfinfo"))
    generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# PDF Layout Scan",
        "",
        f"_Generated: {generated}_",
        "",
        "_Aid for the Rendered PDF Layout Check (GR-020). Compilation success is not "
        "enough — render the pages and look at them._",
        "",
        f"- `pdfinfo` available: {have_pdfinfo}",
        f"- `pdftoppm` available: {have_pdftoppm}",
        "",
    ]
    if not pdfs:
        lines.append(f"No compiled PDF found under `{PAPER_DIR}/`. Build the manuscript "
                     "first (e.g. `latexmk -pdf` inside `paper/`), then re-run.")
    else:
        lines.append(f"Found **{len(pdfs)}** PDF(s):")
        lines.append("")
        lines.append("| PDF | Pages | Size |")
        lines.append("|-----|-------|------|")
        for p in pdfs:
            rel = os.path.relpath(p, REPO_ROOT)
            pages = pdfinfo_pages(p) or "?"
            try:
                size = human_size(os.path.getsize(p))
            except OSError:
                size = "?"
            lines.append(f"| `{rel}` | {pages} | {size} |")
        lines.append("")
        lines.append("### Render pages for the visual check")
        if have_pdftoppm:
            first = os.path.relpath(pdfs[0], REPO_ROOT)
            lines.append("```bash")
            lines.append(f"pdftoppm -png -r 150 '{first}' /tmp/paper_page   # then open the images")
            lines.append("```")
            lines.append("_Render to a scratch/temp location; do NOT commit page images._")
        else:
            lines.append("`pdftoppm` not found — install poppler-utils, or open the PDF in a "
                         "viewer and inspect each page.")
        lines.append("")
        lines.append("Then record findings/fixes in `outputs/reports/PDF_LAYOUT_CHECK.md` "
                     "(overflow, broken tables/figures, `??` refs, captions, fonts, layout).")
    lines.append("")

    out_path = os.path.join(REPO_ROOT, OUTPUT_REL)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"PDF layout scan ({len(pdfs)} PDF(s)) -> {os.path.relpath(out_path, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
