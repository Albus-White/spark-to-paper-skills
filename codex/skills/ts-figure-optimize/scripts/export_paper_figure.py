#!/usr/bin/env python3
"""Export a finished DrawAI run into the ts-paper figure contract.

Full reconstruction is the default. It consumes final/semantic.svg,
final/publication_figure.pdf, and final/editable.pptx and refuses a non-PASS run unless the
caller explicitly records approval with --accept-review-required. Fidelity-hybrid artifacts are
accepted only with --mode fidelity-hybrid; they are never auto-selected.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import shutil
from pathlib import Path


def inline_images(svg_path: Path) -> str:
    """Return SVG with local image hrefs rewritten to data URIs."""
    svg = svg_path.read_text(encoding="utf-8")
    base = svg_path.parent

    def repl(match: re.Match[str]) -> str:
        attr, href = match.group(1), match.group(2)
        if href.startswith(("data:", "http://", "https://")):
            return match.group(0)
        path = (base / href).resolve()
        if not path.is_file():
            return match.group(0)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f'{attr}="data:{mime};base64,{encoded}"'

    return re.sub(r'(xlink:href|href)="([^"]+)"', repl, svg)


def _status(run: Path) -> str:
    path = run / "status.json"
    if not path.is_file():
        return "UNKNOWN"
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("status") or "UNKNOWN")
    except (OSError, ValueError):
        return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--figures-dir", required=True)
    parser.add_argument("--mode", choices=("full", "fidelity-hybrid"), default="full")
    parser.add_argument(
        "--accept-review-required",
        action="store_true",
        help="Export a REVIEW_REQUIRED full reconstruction after explicit human approval",
    )
    args = parser.parse_args()

    run = Path(args.run_dir).resolve()
    final = run / "final"
    figures = Path(args.figures_dir).resolve()
    figures.mkdir(parents=True, exist_ok=True)

    if args.mode == "full":
        status = _status(run)
        allowed = status == "PASS" or (status == "REVIEW_REQUIRED" and args.accept_review_required)
        if not allowed:
            raise SystemExit(
                f"FATAL: full DrawAI run status is {status}; export needs PASS, or explicit "
                "--accept-review-required after human approval"
            )
        svg = final / "semantic.svg"
        pdf = final / "publication_figure.pdf"
        pptx = final / "editable.pptx"
        vectorization = "drawai-full-quality"
    else:
        svg = final / "editable_hybrid.svg"
        pdf = final / "editable_hybrid.pdf"
        pptx = final / "editable_hybrid.pptx"
        vectorization = "drawai-fidelity-hybrid"

    for path in (svg, pdf, pptx):
        if not path.is_file():
            raise SystemExit(f"FATAL: missing {path} for mode={args.mode}")

    (figures / f"{args.label}.svg").write_text(inline_images(svg), encoding="utf-8")
    shutil.copy2(pdf, figures / f"{args.label}.pdf")
    shutil.copy2(pptx, figures / f"{args.label}.pptx")
    source = run / "source" / "source.png"
    if source.is_file():
        shutil.copy2(source, figures / f"{args.label}.png")

    exported_status = _status(run) if args.mode == "full" else "HYBRID_APPROVED"
    if exported_status == "REVIEW_REQUIRED" and args.accept_review_required:
        exported_status = "APPROVED_REVIEW_REQUIRED"
    receipt = {
        "schema": "ts.figure.vector_export.v1",
        "label": args.label,
        "vectorization": vectorization,
        "drawai_status": exported_status,
        "run_dir": str(run),
        "outputs": {
            "svg": str(figures / f"{args.label}.svg"),
            "pdf": str(figures / f"{args.label}.pdf"),
            "pptx": str(figures / f"{args.label}.pptx"),
            "png": str(figures / f"{args.label}.png"),
        },
    }
    receipt_path = figures / f"{args.label}.vectorization.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "receipt": str(receipt_path), **receipt}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
