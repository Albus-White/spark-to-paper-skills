#!/usr/bin/env python3
"""PPTX editability gate. Reuses DrawAI's pptx_inspector when importable; falls back to a
self-contained zip+XML inspector so the skill works even outside the DrawAI source tree.

Usage: python verify_pptx_editability.py <editable.pptx> --out pptx_editability.json
Exit 0 if gate passes, 5 if it fails (screenshot-like / text-in-raster / single image).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path


def _count(xml: str, tag: str) -> int:
    return len(re.findall(r"<" + re.escape(tag) + r"[ >/]", xml))


def inspect(pptx: Path) -> dict:
    # Prefer DrawAI's inspector for parity with its export gate. Portable: env DRAWAI_REPO else an
    # upward search for src/drawai; falls back to the self-contained inspector below otherwise.
    try:
        import os
        cands = []
        if os.environ.get("DRAWAI_REPO"):
            cands.append(Path(os.environ["DRAWAI_REPO"]) / "src")
        cands += [p / "src" for p in Path(__file__).resolve().parents]
        for repo_src in cands:
            if (repo_src / "drawai" / "pptx_inspector.py").exists():
                sys.path.insert(0, str(repo_src))
                from drawai.pptx_inspector import inspect_pptx_structure
                return inspect_pptx_structure(pptx)
    except Exception:  # noqa: BLE001
        pass
    with zipfile.ZipFile(pptx) as zf:
        names = zf.namelist()
        slides = [n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
        media = [n for n in names if n.startswith("ppt/media/")]
        xml = "\n".join(zf.read(n).decode("utf-8", "replace") for n in slides)
    shape = _count(xml, "p:sp")
    pic = _count(xml, "p:pic")
    conn = _count(xml, "p:cxnSp")
    runs = _count(xml, "a:t")
    svg_media = sum(1 for m in media if m.lower().endswith((".svg", ".svgz")))
    return {
        "slide_count": len(slides), "media_count": len(media), "svg_media_count": svg_media,
        "shape_tag_count": shape, "picture_tag_count": pic, "connector_tag_count": conn,
        "text_run_count": runs,
        "is_single_screenshot_like": pic == 1 and shape <= 2 and svg_media == 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-shapes", type=int, default=10)
    ap.add_argument("--min-text-runs", type=int, default=5)
    args = ap.parse_args()

    info = inspect(Path(args.pptx))
    failures = []
    if info.get("is_single_screenshot_like"):
        failures.append("slide is a single flattened screenshot")
    if info.get("picture_tag_count", 0) >= 1 and info.get("shape_tag_count", 0) <= 2 and info.get("text_run_count", 0) == 0:
        failures.append("figure appears to be one full-slide image with no native content")
    if info.get("shape_tag_count", 0) < args.min_shapes:
        failures.append(f"too few native shapes ({info.get('shape_tag_count')} < {args.min_shapes})")
    if info.get("text_run_count", 0) < args.min_text_runs:
        failures.append(f"too few native text runs ({info.get('text_run_count')} < {args.min_text_runs}); text may be rasterized")

    result = {
        "structure": info,
        "gate_pass": len(failures) == 0,
        "failures": failures,
        "editable": info.get("shape_tag_count", 0) >= args.min_shapes and info.get("text_run_count", 0) >= args.min_text_runs,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"pptx editable={result['editable']} shapes={info.get('shape_tag_count')} "
          f"text_runs={info.get('text_run_count')} pics={info.get('picture_tag_count')} "
          f"screenshot_like={info.get('is_single_screenshot_like')}")
    return 0 if result["gate_pass"] else 5


if __name__ == "__main__":
    raise SystemExit(main())
