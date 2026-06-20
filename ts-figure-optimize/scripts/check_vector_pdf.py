#!/usr/bin/env python3
"""check_vector_pdf.py — ts-figure-optimize's editable-vector GATE (replaces ts-paper-vector's
svg_tools.py as the suite gate now that ts-figure-optimize is the sole redraw engine).

Two jobs, both stdlib (+ optional cairosvg for --render-check):
  lint  --svg S --type T [--render-check]   structural/editability gate on ONE SVG: a VECTOR type
        (anything except photo/qualitative) must be a real REDRAW — real <text>, NOT a whole-canvas
        raster, no editability-breaking elements. RASTER-OK types (photo/qualitative) are exempt.
  check --workdir W                          DoD gate: for every figure in figures/figures.manifest.json
        assert figures/<label>.pdf exists AND is genuinely VECTORIZED (not a single full-page raster),
        and every VECTOR-type figures/<label>.svg passes the redraw lint.

Prints a JSON status; exits nonzero on any failure (so run_gates.py stops on a red gate).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
FORBIDDEN = {"script", "style", "filter", "mask", "clipPath", "foreignObject", "textPath", "pattern"}
RASTER_OK_TYPES = {"photo", "qualitative"}        # only these may be a whole-canvas raster
WHOLE_CANVAS_COVER = 0.85


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _f(v):
    try:
        return float(re.sub(r"[a-z%]+$", "", str(v).strip()))
    except (TypeError, ValueError):
        return None


def _canvas(root) -> tuple[float, float] | None:
    vb = root.get("viewBox")
    if vb:
        p = re.split(r"[ ,]+", vb.strip())
        if len(p) == 4:
            return _f(p[2]), _f(p[3])
    w, h = _f(root.get("width")), _f(root.get("height"))
    return (w, h) if w and h else None


def lint_svg(svg_path: Path, ftype: str, render_check: bool) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    raster_ok = (ftype or "").lower() in RASTER_OK_TYPES
    try:
        root = ET.parse(svg_path).getroot()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "errors": [f"svg_parse_error: {exc}"], "warnings": [], "svg": str(svg_path)}

    texts = images = 0
    max_cover = 0.0
    canvas = _canvas(root)
    cw, ch = canvas if canvas else (None, None)
    for el in root.iter():
        tag = _local(el.tag)
        if tag in FORBIDDEN:
            errors.append(f"forbidden_element: <{tag}> breaks editability/render-parity")
        if tag == "text":
            texts += 1
        if tag == "image":
            images += 1
            iw, ih = _f(el.get("width")), _f(el.get("height"))
            if cw and ch and iw and ih:
                max_cover = max(max_cover, (iw * ih) / (cw * ch))

    if not raster_ok:
        if images and max_cover >= WHOLE_CANVAS_COVER:
            errors.append(f"whole_figure_raster: an <image> covers ~{int(max_cover*100)}% of the canvas — "
                          f"a '{ftype}' figure must be REDRAWN; the raster escape hatch is for SUB-regions only")
        if texts == 0:
            errors.append(f"no_text: a '{ftype}' figure has no <text> — labels must be editable <text>, not rasterized")
    if images and not raster_ok:
        warnings.append(f"has_image: {images} <image> sub-region(s) — keep raster minimal; vectorize what you can")

    if render_check and not errors:
        try:
            import cairosvg
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
                tmp = t.name
            cairosvg.svg2png(url=str(svg_path), write_to=tmp, unsafe=True)
            if os.path.getsize(tmp) < 200:
                errors.append("render_check: rendered PNG is suspiciously empty")
            os.unlink(tmp)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"render_check_failed: {exc}")

    return {"ok": not errors, "type": ftype, "errors": errors, "warnings": warnings,
            "text_count": texts, "image_count": images, "svg": str(svg_path)}


def pdf_is_vectorized(pdf_path: Path) -> tuple[bool, str]:
    """A vector figure PDF has embedded fonts and/or pure vector ops; a 'rasterized' PDF is a single
    full-page image with no fonts. Heuristic on the raw bytes (stdlib only)."""
    d = pdf_path.read_bytes()
    images = d.count(b"/Subtype /Image") + d.count(b"/Subtype/Image")
    has_fonts = b"/Font" in d
    if images == 0:
        return True, "no embedded raster (pure vector)"
    if has_fonts:
        return True, f"vector text + {images} embedded sub-region raster(s)"
    return False, f"{images} embedded image(s) and NO fonts — looks like a rasterized (non-vector) PDF"


def _manifest(workdir: Path) -> dict:
    p = workdir / "figures" / "figures.manifest.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    items = data if isinstance(data, list) else data.get("figures", [])
    for it in items:
        if isinstance(it, dict) and it.get("label"):
            out[str(it["label"])] = {"type": it.get("type", "schematic"), "engine": it.get("engine", "")}
    return out


def cmd_check(workdir: Path) -> int:
    figdir = workdir / "figures"
    manifest = _manifest(workdir)
    missing_pdf, raster_pdf, not_redrawn = [], [], []
    # figures referenced in the LaTeX OR present in the manifest
    labels = set(manifest)
    for tex in (workdir / "sections").glob("*.tex") if (workdir / "sections").is_dir() else []:
        for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{figures/([^}]+)\}", tex.read_text(encoding="utf-8", errors="ignore")):
            labels.add(Path(m.group(1)).stem)
    for label in sorted(labels):
        pdf = figdir / f"{label}.pdf"
        if not pdf.exists():
            missing_pdf.append(f"figures/{label}.pdf"); continue
        ok_vec, why = pdf_is_vectorized(pdf)
        if not ok_vec:
            raster_pdf.append({"figure": label, "reason": why})
        ftype = manifest.get(label, {}).get("type", "schematic")
        if ftype.lower() not in RASTER_OK_TYPES:
            svg = figdir / f"{label}.svg"
            if not svg.exists():
                not_redrawn.append({"figure": label, "errors": ["missing .svg redraw source"]})
            else:
                rep = lint_svg(svg, ftype, render_check=False)
                if not rep["ok"]:
                    not_redrawn.append({"figure": label, "errors": rep["errors"]})
    ok = not missing_pdf and not raster_pdf and not not_redrawn
    print(json.dumps({"ok": ok, "missing_pdf": missing_pdf, "rasterized_pdf": raster_pdf,
                      "not_redrawn": not_redrawn, "manifest_present": bool(manifest),
                      "checked": sorted(labels)}, indent=2))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="ts-figure-optimize editable-vector gate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("lint"); pl.add_argument("--svg", required=True); pl.add_argument("--type", default="schematic")
    pl.add_argument("--render-check", action="store_true")
    pc = sub.add_parser("check"); pc.add_argument("--workdir", required=True)
    a = ap.parse_args()
    if a.cmd == "lint":
        rep = lint_svg(Path(a.svg), a.type, a.render_check)
        print(json.dumps(rep, indent=2))
        return 0 if rep["ok"] else 1
    return cmd_check(Path(a.workdir))


if __name__ == "__main__":
    raise SystemExit(main())
