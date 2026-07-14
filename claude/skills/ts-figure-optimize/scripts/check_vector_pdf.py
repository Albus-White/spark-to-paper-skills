#!/usr/bin/env python3
"""Validate declared publication graphics and optional DrawAI reconstruction artifacts."""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

FORBIDDEN = {"script", "style", "filter", "mask", "foreignObject", "textPath", "pattern"}
WHOLE_CANVAS_COVER = 0.85


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _float(value):
    try:
        return float(re.sub(r"[a-z%]+$", "", str(value).strip()))
    except (TypeError, ValueError):
        return None


def _canvas(root) -> tuple[float, float] | None:
    viewbox = root.get("viewBox")
    if viewbox:
        values = re.split(r"[ ,]+", viewbox.strip())
        if len(values) == 4:
            return _float(values[2]), _float(values[3])
    width, height = _float(root.get("width")), _float(root.get("height"))
    return (width, height) if width and height else None


def lint_svg(svg_path: Path, figure_type: str, render_check: bool, mode: str = "full") -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        root = ET.parse(svg_path).getroot()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "errors": [f"svg_parse_error: {exc}"], "warnings": [], "svg": str(svg_path)}

    counts = {"text": 0, "image": 0, "vector": 0}
    max_cover = 0.0
    canvas = _canvas(root)
    width, height = canvas if canvas else (None, None)
    vector_tags = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
    for element in root.iter():
        tag = _local(element.tag)
        if tag in FORBIDDEN:
            errors.append(f"forbidden_element: <{tag}>")
        if tag == "text":
            counts["text"] += 1
        elif tag == "image":
            counts["image"] += 1
            image_width, image_height = _float(element.get("width")), _float(element.get("height"))
            if width and height and image_width and image_height:
                max_cover = max(max_cover, image_width * image_height / (width * height))
        elif tag in vector_tags:
            counts["vector"] += 1

    if mode == "full":
        if counts["text"] == 0:
            errors.append(f"no_editable_text: full reconstruction of '{figure_type}' has no SVG text")
        if counts["vector"] == 0:
            errors.append("no_vector_primitives: full reconstruction contains no editable graphics")
        if max_cover >= WHOLE_CANVAS_COVER:
            errors.append(
                f"whole_canvas_raster: image covers ~{int(max_cover * 100)}% of canvas; "
                "this is a fidelity hybrid, not full reconstruction"
            )
    else:
        if counts["text"] == 0:
            errors.append("hybrid_no_editable_text: fidelity hybrid must overlay editable labels")
        if max_cover < WHOLE_CANVAS_COVER:
            warnings.append("hybrid_without_whole_canvas: confirm this was intentionally exported as hybrid")

    if render_check and not errors:
        try:
            import cairosvg
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                rendered = tmp.name
            try:
                cairosvg.svg2png(url=str(svg_path), write_to=rendered, unsafe=True)
                if os.path.getsize(rendered) < 200:
                    errors.append("render_check: suspiciously empty render")
            finally:
                Path(rendered).unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"render_check_failed: {exc}")

    return {
        "ok": not errors,
        "mode": mode,
        "type": figure_type,
        "errors": errors,
        "warnings": warnings,
        "counts": counts,
        "max_raster_canvas_cover": round(max_cover, 6),
        "svg": str(svg_path),
    }


def pdf_is_vectorized(path: Path) -> tuple[bool, str]:
    data = path.read_bytes()
    images = data.count(b"/Subtype /Image") + data.count(b"/Subtype/Image")
    fonts = b"/Font" in data
    vector_ops = any(token in data for token in (b" m ", b" l ", b" re ", b" c "))
    if images == 0 and (fonts or vector_ops):
        return True, "pure/vector PDF content"
    if fonts or vector_ops:
        return True, f"vector content plus {images} embedded local raster asset(s)"
    return False, f"{images} image(s), no detected fonts/vector operators"


def _manifest(workdir: Path) -> dict[str, dict]:
    path = workdir / "figures" / "figures.manifest.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = payload if isinstance(payload, list) else payload.get("figures", [])
    return {
        str(item.get("figure_id") or item.get("label")): item
        for item in items
        if isinstance(item, dict) and (item.get("figure_id") or item.get("label"))
    }


def _labels_from_tex(workdir: Path) -> set[str]:
    labels: set[str] = set()
    sections = workdir / "sections"
    if not sections.is_dir():
        return labels
    for tex in sections.glob("*.tex"):
        content = tex.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{figures/([^}]+)\}", content):
            labels.add(Path(match.group(1)).stem)
    return labels


def _declared_path(workdir: Path, value: str) -> Path | None:
    if not value:
        return None
    try:
        path = (workdir / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
        path.relative_to(workdir.resolve())
    except (OSError, ValueError):
        return None
    return path


def check_workdir(workdir: Path) -> int:
    figures = workdir / "figures"
    manifest = _manifest(workdir)
    labels = set(manifest) | _labels_from_tex(workdir)
    errors: list[str] = []
    reports: dict[str, dict] = {}

    for label in sorted(labels):
        entry = manifest.get(label, {})
        renderer = str(entry.get("renderer") or entry.get("engine") or "unspecified")
        vector = _declared_path(workdir, str(entry.get("published_vector") or ""))
        raster = _declared_path(workdir, str(entry.get("published_raster") or ""))
        if not entry:
            vector = next((path for path in (figures / f"{label}.pdf", figures / f"{label}.svg") if path.is_file()), None)
            raster = next((path for path in (figures / f"{label}.png", figures / f"{label}.jpg", figures / f"{label}.jpeg") if path.is_file()), None)
        if vector is None and raster is None:
            errors.append(f"{label}: no declared publication vector or raster artifact")
            continue
        report = {"renderer": renderer}
        if vector is not None:
            if not vector.is_file():
                errors.append(f"{label}: published vector missing: {vector}")
            elif vector.suffix.lower() == ".pdf":
                pdf_ok, pdf_note = pdf_is_vectorized(vector)
                report["vector"] = pdf_note
                if not pdf_ok:
                    errors.append(f"{label}: declared vector PDF has no detected vector content ({pdf_note})")
            elif vector.suffix.lower() != ".svg":
                errors.append(f"{label}: unsupported published vector format {vector.suffix}")
        if raster is not None and not raster.is_file():
            errors.append(f"{label}: published raster missing: {raster}")
        reports[label] = report

        # DrawAI-specific editability checks apply only when reconstruction is explicitly declared.
        vectorization = str(entry.get("vectorization") or "")
        if not vectorization:
            continue
        mode = "full" if vectorization == "drawai-full-quality" else "fidelity-hybrid"
        if vectorization not in {"drawai-full-quality", "drawai-fidelity-hybrid"}:
            errors.append(f"{label}: invalid/missing vectorization mode {vectorization!r}")
            continue
        status = str(entry.get("drawai_status") or "")
        allowed_status = {"PASS", "APPROVED_REVIEW_REQUIRED"} if mode == "full" else {"HYBRID_APPROVED"}
        if status not in allowed_status:
            errors.append(f"{label}: drawai_status={status!r}, expected one of {sorted(allowed_status)}")

        svg = figures / f"{label}.svg"
        pptx = figures / f"{label}.pptx"
        receipt = figures / f"{label}.vectorization.json"
        for path in (svg, pptx, receipt, figures / f"{label}.png"):
            if not path.is_file():
                errors.append(f"{label}: missing {path.name}")
        if svg.is_file():
            report = lint_svg(svg, str(entry.get("type") or "schematic"), False, mode)
            reports[label]["drawai_svg"] = report
            errors.extend(f"{label}: {problem}" for problem in report["errors"])

    result = {"ok": not errors, "errors": errors, "reports": reports, "checked": sorted(labels)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="publication graphic and optional DrawAI vector gate")
    sub = parser.add_subparsers(dest="command", required=True)
    lint = sub.add_parser("lint")
    lint.add_argument("--svg", required=True)
    lint.add_argument("--type", default="schematic")
    lint.add_argument("--mode", choices=("full", "fidelity-hybrid"), default="full")
    lint.add_argument("--render-check", action="store_true")
    check = sub.add_parser("check")
    check.add_argument("--workdir", required=True)
    args = parser.parse_args()
    if args.command == "lint":
        report = lint_svg(Path(args.svg), args.type, args.render_check, args.mode)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    return check_workdir(Path(args.workdir))


if __name__ == "__main__":
    raise SystemExit(main())
