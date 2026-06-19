#!/usr/bin/env python3
"""svg_tools.py — the ONLY irreducible code for ts-paper-vector.

Claude does all the reasoning: decompose the approved raster figure, author the SVG, and
judge fidelity with its own vision. This script does only what Claude cannot do by reasoning:
rasterize / convert / structurally-lint an SVG, sample pixel colours, and crop a raster.

Subcommands
  render   SVG -> PNG (cairosvg)             produce the raster for the vision-compare loop
  topdf    SVG -> PDF (cairosvg)             the embedded editable vector for LaTeX
  lint     structural / safety / editability gate (stdlib XML)   no quality judgement
  check    assert every \\includegraphics{figures/<label>} in a workdir has a sibling .pdf
  sample   print the hex colour at given points of a PNG (palette aid)
  crop     crop a PNG box (the raster-embed escape hatch)

stdlib + cairosvg only. cwd-independent (every path is resolved). Prints a JSON status object
to stdout. Exits nonzero on any failure or hard lint error. NO lossy rasteriser fallback:
if cairosvg is missing, fail loud with a `pip install cairosvg` hint (never silently degrade).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Editable-SVG profile (distilled from DrawAI scientific_svg_profile.py). Elements that break
# editability and/or make cairosvg-render diverge from the final PDF.
FORBIDDEN_ELEMENTS = {
    "script", "style", "filter", "mask", "clipPath", "foreignObject", "textPath", "pattern",
}
# href-bearing / ref attributes to scan for external or absolute targets.
_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)")

# Figure-TYPE drives how editable a figure MUST be (restores DrawAI's whole_slide_image / no-text
# HARD violations, which we had weakened to warnings). A schematic of a VECTOR type must be redrawn
# as editable primitives + real <text>; a whole-canvas raster or zero-text SVG is a HARD ERROR for
# these. Only genuinely un-vectorizable RASTER-OK types may use a whole-canvas raster.
VECTOR_TYPES = {"architecture", "pipeline", "framework", "concept", "schematic",
                "overview", "flow", "diagram"}
RASTER_OK_TYPES = {"photo", "qualitative"}


# --------------------------------------------------------------------------- helpers

def _resolve(p: str) -> Path:
    return Path(p).expanduser().resolve()


def _emit(obj: dict, ok: bool) -> "NoReturn":  # type: ignore[name-defined]
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(0 if ok else 1)


def _fail(msg: str, extra: dict | None = None) -> "NoReturn":  # type: ignore[name-defined]
    out = {"ok": False, "error": msg}
    if extra:
        out.update(extra)
    _emit(out, ok=False)


def _require_cairosvg():
    try:
        import cairosvg  # noqa: F401
        return cairosvg
    except Exception:  # noqa: BLE001
        _fail(
            "cairosvg is not available — it is the required SVG renderer for ts-paper-vector. "
            "Install it: `pip install cairosvg` (pure-python; no system inkscape needed).",
            {"hint": "pip install cairosvg"},
        )


def _local(tag) -> str:
    if isinstance(tag, str) and "}" in tag:
        return tag.split("}", 1)[1]
    return tag if isinstance(tag, str) else ""


def _is_external_or_absolute(ref: str) -> bool:
    """http(s)://, file://, protocol-relative //, absolute POSIX/UNC/Windows path."""
    r = ref.strip()
    if not r:
        return False
    low = r.lower()
    if low.startswith(("http://", "https://", "file://", "ftp://")):
        return True
    if r.startswith("//") or r.startswith("/") or r.startswith("\\\\"):
        return True
    if re.match(r"^[a-zA-Z]:[\\/]", r):  # C:\ or C:/
        return True
    return False


# --------------------------------------------------------------------------- render / topdf

def cmd_render(args) -> None:
    svg = _resolve(args.svg)
    out = _resolve(args.png_out)
    if not svg.exists():
        _fail(f"svg not found: {svg}")
    cairosvg = _require_cairosvg()
    out.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"url": str(svg), "write_to": str(out), "unsafe": False,
              "background_color": args.background}
    if args.width:
        kwargs["output_width"] = int(args.width)
    if args.height:
        kwargs["output_height"] = int(args.height)
    try:
        cairosvg.svg2png(**kwargs)
    except Exception as exc:  # noqa: BLE001
        _fail(f"cairosvg svg2png failed: {type(exc).__name__}: {exc}")
    if not out.exists() or out.stat().st_size == 0:
        _fail("render produced no/empty PNG")
    _emit({"ok": True, "out": str(out), "bytes": out.stat().st_size}, ok=True)


def cmd_topdf(args) -> None:
    svg = _resolve(args.svg)
    out = _resolve(args.pdf_out)
    if not svg.exists():
        _fail(f"svg not found: {svg}")
    cairosvg = _require_cairosvg()
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        cairosvg.svg2pdf(url=str(svg), write_to=str(out), unsafe=False)
    except Exception as exc:  # noqa: BLE001
        _fail(f"cairosvg svg2pdf failed: {type(exc).__name__}: {exc}")
    if not out.exists() or out.stat().st_size == 0:
        _fail("conversion produced no/empty PDF")
    _emit({"ok": True, "out": str(out), "bytes": out.stat().st_size}, ok=True)


# --------------------------------------------------------------------------- lint

def _aspect(w: float, h: float) -> float:
    return (w / h) if h else 0.0


def _lint_svg(svg: Path, canvas: str | None = None, ftype: str = "", render_check: bool = False):
    """Structural/editability lint. Returns (errors, warnings). `ftype` (FIGURE-SPEC type) drives
    severity: for a VECTOR type a whole-canvas raster or zero-<text> SVG is a hard error (it was
    not redrawn); for RASTER-OK / unknown types those stay advisory warnings."""
    raw = svg.read_bytes()
    errors: list[str] = []
    warnings: list[str] = []

    # Raw-byte prescan (before parse) — reject DTD / entity declarations.
    if b"<!DOCTYPE" in raw:
        errors.append("doctype: <!DOCTYPE present (forbidden)")
    if b"<!ENTITY" in raw:
        errors.append("entity: <!ENTITY present (forbidden)")

    root = None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        errors.append(f"not_wellformed: {exc}")

    canvas_area = None
    if root is not None:
        if _local(root.tag) != "svg":
            errors.append(f"root_not_svg: <{_local(root.tag)}>")
        viewbox = root.get("viewBox") or root.get("viewbox")
        if not viewbox:
            errors.append("missing_viewbox: <svg> has no viewBox")
        else:
            try:
                parts = [float(x) for x in re.split(r"[\s,]+", viewbox.strip()) if x]
                vb_w, vb_h = parts[2], parts[3]
                canvas_area = vb_w * vb_h
                if canvas:
                    cw, ch = (float(v) for v in canvas.lower().split("x"))
                    if abs(_aspect(vb_w, vb_h) - _aspect(cw, ch)) > 0.01:
                        errors.append(
                            f"viewbox_aspect_mismatch: viewBox {vb_w}x{vb_h} vs canvas {cw}x{ch}")
            except Exception:  # noqa: BLE001
                warnings.append(f"viewbox_unparsed: {viewbox!r}")

        text_count = path_count = image_count = 0
        max_image_cover = 0.0
        for el in root.iter():
            name = _local(el.tag)
            if not name:
                continue
            if name == "text":
                text_count += 1
            elif name == "path":
                path_count += 1
            elif name == "image":
                image_count += 1
            if name in FORBIDDEN_ELEMENTS:
                errors.append("script_element" if name == "script" else f"forbidden_element:{name}")
            if name == "image":
                # The raster-embed escape hatch MUST be a self-contained data: URI — that is the only
                # <image> form the safe renderer (unsafe=False) actually draws; relative/file/external
                # refs are silently dropped (→ a blank hole). Enforce data:-only here.
                href = (el.get("href") or el.get(f"{{{XLINK_NS}}}href") or el.get("src") or "").strip()
                if href and not href.lower().startswith("data:"):
                    if _is_external_or_absolute(href):
                        errors.append(f"external_href:{href}")
                    else:
                        errors.append(f"image_href_not_data:{href} — an <image> must embed a data: URI "
                                      "(use `svg_tools.py crop`); relative/file refs render blank")
                if canvas_area:
                    try:
                        iw = float(re.sub(r"[a-z%]+$", "", (el.get("width") or "0").strip()))
                        ih = float(re.sub(r"[a-z%]+$", "", (el.get("height") or "0").strip()))
                        if iw and ih:
                            max_image_cover = max(max_image_cover, (iw * ih) / canvas_area)
                    except Exception:  # noqa: BLE001
                        pass
            # ref attributes on any element (href/src handled above for <image>)
            for key, val in el.attrib.items():
                k = _local(key)
                if k in ("href", "src"):
                    if name != "image" and _is_external_or_absolute(val):
                        errors.append(f"external_href:{val}")
                elif k == "style":
                    if "@import" in val:
                        errors.append("external_href:@import in style")
                    for m in _URL_RE.findall(val):
                        if not m.startswith("#") and (_is_external_or_absolute(m) or m.lower().startswith("data:")):
                            errors.append(f"external_href:{m}")
                else:
                    for m in _URL_RE.findall(val):
                        if not m.startswith("#") and _is_external_or_absolute(m):
                            errors.append(f"external_href:{m}")

        ft = (ftype or "").strip().lower()
        # DEFAULT-DENY: anything that is not EXPLICITLY a raster-OK type (photo/qualitative) is held to
        # the redraw bar. So a typo'd, unknown, or empty type can NOT bypass the whole-raster/no-text
        # errors — the only way to ship a whole-canvas raster is to declare type=photo|qualitative.
        is_vector_type = ft not in RASTER_OK_TYPES
        if ft and ft not in VECTOR_TYPES and ft not in RASTER_OK_TYPES:
            warnings.append(f"unknown_figure_type: '{ft}' — treated as a vector type (redraw required); "
                            f"known vector types are {sorted(VECTOR_TYPES)}")
        # no_text: a vector-type schematic with no editable <text> was NOT redrawn -> HARD error
        # (DrawAI made no-editable-text a violation). photo/qualitative/unknown stays advisory.
        if text_count == 0:
            if is_vector_type:
                errors.append(f"no_text: a vector figure (type={ft}) has NO <text> — schematic labels must be "
                              "redrawn as editable <text>, never rasterized")
            elif image_count == 0:
                errors.append("no_text: no <text> element (labels must be editable text, not outlined paths)")
            else:
                warnings.append("no_text: no <text> element — acceptable ONLY for a genuinely raster/photo figure "
                                "(escape hatch); a schematic must have editable <text> labels")
        # whole_figure_raster: one <image> covering ~the whole canvas = the escape-hatch-as-default
        # failure. HARD error for a vector type (DrawAI whole_slide_image); advisory otherwise.
        if max_image_cover >= 0.85:
            base = f"whole_figure_raster: an <image> covers ~{int(max_image_cover * 100)}% of the canvas"
            if is_vector_type:
                errors.append(base + f" — a vector figure (type={ft}) must be REDRAWN as primitives, not wrapped "
                                     "as one raster; the escape hatch is for SUB-regions only")
            else:
                warnings.append(base + " — only acceptable for a genuinely photographic figure; a schematic "
                                       "must be redrawn as vector")
        if image_count and max_image_cover < 0.85:
            warnings.append(f"has_image: {image_count} data:-URI <image> sub-region(s) — keep raster minimal; "
                            "vectorize whatever you can (the escape hatch is only for un-vectorizable detail)")
        if path_count >= 8 and text_count <= 2 and image_count == 0:
            warnings.append(f"possible_text_as_paths: {path_count} <path> vs {text_count} <text> — "
                            "verify labels are real <text>, not outlined")
        if not ft:
            warnings.append("type_not_given: no --type provided; enforcing vector rules by default "
                            "(only an explicit --type photo|qualitative may be a whole-canvas raster)")

    # Optional non-blank render check (needs cairosvg; off by default).
    if render_check and not errors:
        cairosvg = _require_cairosvg()
        try:
            import io
            from PIL import Image  # noqa
            png_bytes = cairosvg.svg2png(bytestring=raw, unsafe=False, background_color="white")
            im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            px = im.getdata()
            nonwhite = sum(1 for r, g, b in px if (r, g, b) != (255, 255, 255))
            if nonwhite == 0:
                errors.append("blank_render: render is all white (figure drew nothing)")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"render_check_skipped: {type(exc).__name__}: {exc}")

    return errors, warnings


def cmd_lint(args) -> None:
    svg = _resolve(args.svg)
    if not svg.exists():
        _fail(f"svg not found: {svg}")
    errors, warnings = _lint_svg(svg, canvas=args.canvas, ftype=getattr(args, "type", "") or "",
                                 render_check=args.render_check)
    ok = len(errors) == 0
    _emit({"ok": ok, "errors": errors, "warnings": warnings, "svg": str(svg)}, ok=ok)


# --------------------------------------------------------------------------- check

_INCLUDE_RE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")


def _strip_tex_comments(text: str) -> str:
    """Drop everything from an unescaped % to end-of-line (so a commented-out
    \\includegraphics is not treated as a live figure reference)."""
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in text.splitlines())


def _load_fig_manifest(workdir: Path) -> dict:
    """label -> {'type','engine'} from figures/figures.manifest.json (written by ts-paper-figure)."""
    p = workdir / "figures" / "figures.manifest.json"
    out: dict = {}
    if p.exists():
        try:
            data = json.loads(p.read_text())
            rows = data.get("figures", data) if isinstance(data, dict) else data
            for f in rows or []:
                lbl = f.get("label")
                if lbl:
                    # 'type' drives the gate; 'engine' (matplotlib|image-model) is trace-only context.
                    out[lbl] = {"type": (f.get("type") or "").strip().lower(),
                                "engine": (f.get("engine") or "").strip().lower()}
        except Exception:  # noqa: BLE001
            pass
    return out


def cmd_check(args) -> None:
    workdir = _resolve(args.workdir)
    sections = sorted((workdir / "sections").glob("*.tex"))
    if not sections:
        # also allow a flat main.tex
        sections = sorted(workdir.glob("*.tex"))
    figdir = workdir / "figures"
    missing: list[str] = []
    checked: list[str] = []
    for tex in sections:
        try:
            text = _strip_tex_comments(tex.read_text(encoding="utf-8", errors="ignore"))
        except Exception:  # noqa: BLE001
            continue
        for m in _INCLUDE_RE.findall(text):
            target = m.strip()
            if "figures/" not in target.replace("\\", "/"):
                continue
            label = Path(target).name
            stem = label.rsplit(".", 1)[0] if "." in label else label
            pdf = figdir / f"{stem}.pdf"
            checked.append(f"{stem}")
            if not pdf.exists():
                missing.append(f"figures/{stem}.pdf (referenced in {tex.name})")

    # VECTOR-NESS gate (the real "no silent raster" check, not just .pdf existence). Only image-model
    # figures emit a .svg (matplotlib figures are born-vector PDFs with no .svg, so they are skipped).
    # A .svg of a VECTOR type that is a whole-canvas raster / has no <text> = NOT redrawn -> hard fail.
    manifest = _load_fig_manifest(workdir)
    raster_not_vector: list[dict] = []
    for svg in (sorted(figdir.glob("*.svg")) if figdir.is_dir() else []):
        info = manifest.get(svg.stem, {})
        ftype = info.get("type") or "schematic"   # default: enforce vector unless manifest says photo/qualitative
        if ftype in RASTER_OK_TYPES:
            continue
        errs, _w = _lint_svg(svg, ftype=ftype)
        if errs:
            raster_not_vector.append({"figure": svg.stem, "type": ftype, "errors": errs})

    ok = not missing and not raster_not_vector
    _emit({"ok": ok, "figures_checked": sorted(set(checked)), "missing_pdf": missing,
           "raster_not_vector": raster_not_vector, "manifest_present": bool(manifest),
           "workdir": str(workdir)}, ok=ok)


# --------------------------------------------------------------------------- sample / crop

def cmd_sample(args) -> None:
    png = _resolve(args.png)
    if not png.exists():
        _fail(f"png not found: {png}")
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        _fail("Pillow (PIL) is required for `sample`: pip install pillow")
    im = Image.open(png).convert("RGB")
    w, h = im.size
    out = []
    for pair in args.points.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        try:
            x, y = (int(round(float(v))) for v in pair.split(","))
        except Exception as exc:  # noqa: BLE001
            _fail(f"bad point {pair!r} (expected 'x,y'): {exc}")
        x = max(0, min(w - 1, x))
        y = max(0, min(h - 1, y))
        r, g, b = im.getpixel((x, y))
        out.append({"x": x, "y": y, "hex": f"#{r:02x}{g:02x}{b:02x}"})
    _emit({"ok": True, "size": [w, h], "points": out}, ok=True)


def cmd_crop(args) -> None:
    import base64
    import io as _io
    png = _resolve(args.png)
    out = _resolve(args.out)
    if not png.exists():
        _fail(f"png not found: {png}")
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        _fail("Pillow (PIL) is required for `crop`: pip install pillow")
    try:
        x, y, bw, bh = (int(round(float(v))) for v in args.box.split(","))
    except Exception as exc:  # noqa: BLE001
        _fail(f"bad --box {args.box!r} (expected 'x,y,w,h'): {exc}")
    crop = Image.open(png).convert("RGBA").crop((x, y, x + bw, y + bh))
    out.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out)
    # also emit a self-contained data: URI — the ONLY <image> form the safe renderer draws.
    buf = _io.BytesIO()
    crop.save(buf, "PNG")
    data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    _emit({"ok": True, "out": str(out), "box": [x, y, bw, bh], "data_uri": data_uri,
           "image_element": f'<image href="{data_uri}" x="{x}" y="{y}" width="{bw}" height="{bh}"/>'},
          ok=True)


# --------------------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="ts-paper-vector irreducible SVG/raster tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="SVG -> PNG (cairosvg)")
    r.add_argument("--svg", required=True)
    r.add_argument("--png-out", required=True, dest="png_out")
    r.add_argument("--width", type=int, default=None, help="output width px (match the approved PNG)")
    r.add_argument("--height", type=int, default=None)
    r.add_argument("--background", default="white")
    r.set_defaults(func=cmd_render)

    d = sub.add_parser("topdf", help="SVG -> PDF (cairosvg)")
    d.add_argument("--svg", required=True)
    d.add_argument("--pdf-out", required=True, dest="pdf_out")
    d.set_defaults(func=cmd_topdf)

    l = sub.add_parser("lint", help="structural/safety/editability gate")
    l.add_argument("--svg", required=True)
    l.add_argument("--canvas", default=None, help="WxH of the approved PNG, to check viewBox aspect")
    l.add_argument("--type", default="", help="FIGURE-SPEC type (architecture/pipeline/concept/... or photo/qualitative); "
                                              "vector types make whole-figure-raster + no-text HARD errors")
    l.add_argument("--render-check", action="store_true", help="also assert the render is non-blank")
    l.set_defaults(func=cmd_lint)

    c = sub.add_parser("check", help="assert every figure has a sibling .pdf AND every vector-type .svg is truly redrawn (not a raster)")
    c.add_argument("--workdir", required=True)
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("sample", help="hex colour at points of a PNG")
    s.add_argument("--png", required=True)
    s.add_argument("--points", required=True, help='"x1,y1;x2,y2;..."')
    s.set_defaults(func=cmd_sample)

    cr = sub.add_parser("crop", help="crop a PNG box (raster-embed escape hatch)")
    cr.add_argument("--png", required=True)
    cr.add_argument("--box", required=True, help='"x,y,w,h"')
    cr.add_argument("--out", required=True)
    cr.set_defaults(func=cmd_crop)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
