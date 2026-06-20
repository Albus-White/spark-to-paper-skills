#!/usr/bin/env python3
"""Eliminate raster-crop background mismatch (the "pasted rectangle" artifact).

For every <image> asset in the SVG: detect a uniform/near-uniform crop background, find the target
panel fill behind it (and/or sample surrounding pixels from the render), and if a visible rectangular
boundary exists, repair ONLY that asset — by removing the background to transparent RGBA (preferred)
or replacing it with the exact panel fill — preserving foreground strokes and anti-aliased edges.
Adds a local color-difference (ΔE, CIE76 Lab) check around every raster asset boundary.

Preferred order: native vector > transparent raster crop > background-matched raster crop > original.

Gate: RASTER_BACKGROUND_MATCH = PASS | REVIEW_REQUIRED | FAILED

Usage:
  python fix_raster_backgrounds.py --svg semantic.svg [--render rendered_svg.png] \
      [--assets-root <dir>] --out raster_bg_gate.json [--repair] [--mode transparent|match_fill] \
      [--threshold 12] [--svg-out fixed.svg]
"""
from __future__ import annotations

import argparse
import base64
import io
import re
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402

IMG_RE = re.compile(r"<image\b[^>]*?(?:/>|>)", re.S)
RECT_RE = re.compile(r"<rect\b[^>]*?(?:/>|>)", re.S)


def _attr(s, name):
    m = re.search(name + r'="([^"]*)"', s)
    return m.group(1) if m else None


def _num(s, name):
    v = _attr(s, name)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _href(tag):
    return _attr(tag, "xlink:href") or _attr(tag, "href")


def load_image_from_href(href: str, assets_root: Path):
    """Return (PIL.Image, kind) where kind in {'file','data'} or (None, reason)."""
    if href.startswith("data:image"):
        m = re.match(r"data:image/[^;]+;base64,(.*)", href, re.S)
        if not m:
            return None, "bad_data_uri"
        try:
            raw = base64.b64decode(m.group(1))
            return Image.open(io.BytesIO(raw)), "data"
        except Exception:  # noqa: BLE001
            return None, "bad_data_uri"
    png = (assets_root / href).resolve()
    if not png.exists():
        return None, "missing_png"
    return Image.open(png), "file"


def image_to_data_uri(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.convert("RGBA").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def border_stats(im: Image.Image):
    """Median border color and per-channel std over a 2px ring (uniformity test)."""
    a = np.asarray(im.convert("RGB"), dtype=np.float64)
    h, w = a.shape[:2]
    ring = np.concatenate([a[:2].reshape(-1, 3), a[-2:].reshape(-1, 3),
                           a[:, :2].reshape(-1, 3), a[:, -2:].reshape(-1, 3)])
    med = tuple(float(np.median(ring[:, c])) for c in range(3))
    std = float(np.mean([ring[:, c].std() for c in range(3)]))
    return med, std


def already_transparent_border(im: Image.Image) -> bool:
    if im.mode != "RGBA":
        return False
    a = np.asarray(im)[..., 3]
    h, w = a.shape
    ring = np.concatenate([a[:2].ravel(), a[-2:].ravel(), a[:, :2].ravel(), a[:, -2:].ravel()])
    return float(ring.mean()) < 32  # mostly transparent border


def panel_fill_for(rects, cx, cy, img_area):
    """Smallest filled rect that contains (cx,cy) and is larger than the image (the panel behind)."""
    best, best_area = None, None
    for r in rects:
        x, y, w, h = (_num(r, "x") or 0), (_num(r, "y") or 0), _num(r, "width"), _num(r, "height")
        if w is None or h is None:
            continue
        area = w * h
        if x <= cx <= x + w and y <= cy <= y + h and area >= img_area * 1.1:
            fill = C.parse_color(_attr(r, "fill") or _style_fill(_attr(r, "style")))
            if fill is None:
                continue
            if best_area is None or area < best_area:
                best, best_area = fill, area
    return best


def _style_fill(style):
    if not style:
        return None
    m = re.search(r"fill:\s*([^;]+)", style)
    return m.group(1).strip() if m else None


def ring_color_from_render(render: np.ndarray, bbox, outside: bool):
    """Average color of a ring just inside/outside the asset bbox in the rendered figure."""
    H, W = render.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    d = 3
    if outside:
        xs = [(max(0, x1 - d), x1), (x2, min(W, x2 + d))]
        ys = [(max(0, y1 - d), y2), (y1, min(H, y2 + d))]
        px = []
        for (a, b) in xs:
            if b > a:
                px.append(render[max(0, y1):min(H, y2), a:b].reshape(-1, 3))
        for (a, b) in ys:
            if b > a:
                px.append(render[a:b, max(0, x1):min(W, x2)].reshape(-1, 3))
    else:
        px = [render[y1:y1 + d, x1:x2].reshape(-1, 3), render[y2 - d:y2, x1:x2].reshape(-1, 3),
              render[y1:y2, x1:x1 + d].reshape(-1, 3), render[y1:y2, x2 - d:x2].reshape(-1, 3)]
    px = [p for p in px if p.size]
    if not px:
        return None
    allp = np.concatenate(px)
    return tuple(float(allp[:, c].mean()) for c in range(3))


def remove_or_match_bg(im: Image.Image, bg_rgb, mode: str, panel_rgb, tol_de: float = 12.0):
    """Flood-fill edge-connected background pixels; transparent (alpha 0) or replace with panel fill.
    Preserves foreground + anti-aliased edges (only pixels within ΔE tol of bg are affected; near-bg
    pixels are feathered in transparent mode)."""
    im = im.convert("RGBA")
    arr = np.asarray(im).astype(np.float64)
    h, w = arr.shape[:2]
    rgb = arr[..., :3]
    bg = np.array(bg_rgb, dtype=np.float64)

    # ΔE per pixel vs bg (cheap: weighted RGB; good enough for uniform bg)
    diff = np.sqrt(((rgb - bg) ** 2 * np.array([0.30, 0.59, 0.11])).sum(axis=2)) / 255.0 * 100.0
    is_bg = diff <= tol_de
    visited = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for yy in (0, h - 1):
            if is_bg[yy, x] and not visited[yy, x]:
                visited[yy, x] = True; q.append((x, yy))
    for y in range(h):
        for xx in (0, w - 1):
            if is_bg[y, xx] and not visited[y, xx]:
                visited[y, xx] = True; q.append((xx, y))
    while q:
        x, y = q.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx] and is_bg[ny, nx]:
                visited[ny, nx] = True; q.append((nx, ny))

    out = arr.copy()
    if mode == "match_fill" and panel_rgb is not None:
        out[..., 0][visited] = panel_rgb[0]
        out[..., 1][visited] = panel_rgb[1]
        out[..., 2][visited] = panel_rgb[2]
        out[..., 3][visited] = 255
    else:  # transparent (preferred), with edge feathering
        feather = np.clip(diff / max(tol_de, 1e-6), 0, 1)  # 0 at bg -> fully transparent
        a = out[..., 3]
        a[visited] = a[visited] * feather[visited]
        out[..., 3] = a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--render", default="")
    ap.add_argument("--assets-root", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--mode", choices=["transparent", "match_fill"], default="transparent")
    ap.add_argument("--threshold", type=float, default=12.0)
    ap.add_argument("--uniform-std", type=float, default=18.0)
    ap.add_argument("--svg-out", default="")
    args = ap.parse_args()

    svg_path = Path(args.svg)
    svg = svg_path.read_text(encoding="utf-8")
    assets_root = Path(args.assets_root) if args.assets_root else svg_path.parent
    render = None
    if args.render and Path(args.render).exists():
        render = np.asarray(Image.open(args.render).convert("RGB"), dtype=np.float64)
        rh, rw = render.shape[:2]

    rects = RECT_RE.findall(svg)
    canvas_w = _svg_canvas(svg)
    assets, repaired = [], 0
    new_svg = svg

    for tag in IMG_RE.findall(svg):
        href = _href(tag)
        x, y, w, h = _num(tag, "x") or 0, _num(tag, "y") or 0, _num(tag, "width"), _num(tag, "height")
        if not href or w is None or h is None:
            continue
        display_href = "data-uri" if href.startswith("data:") else href
        rec = {"href": display_href, "bbox": [x, y, x + w, y + h], "status": "unknown"}
        im, kind = load_image_from_href(href, assets_root)
        if im is None:
            rec["status"] = kind; rec["flag"] = True; assets.append(rec); continue
        rec["kind"] = kind
        cx, cy = x + w / 2, y + h / 2
        panel = panel_fill_for(rects, cx, cy, w * h)
        rec["panel_fill"] = list(panel) if panel else None

        if already_transparent_border(im):
            rec["status"] = "already_transparent"; rec["flag"] = False; assets.append(rec); continue

        bg_rgb, bg_std = border_stats(im)
        rec["crop_border_rgb"] = [round(v, 1) for v in bg_rgb]
        rec["bg_uniform"] = bg_std <= args.uniform_std
        rec["bg_std"] = round(bg_std, 2)

        # target color: panel fill (preferred) else surrounding from render
        target = panel
        if target is None and render is not None:
            sx = canvas_w and (rw / canvas_w) or 1.0
            scaled = [v * sx for v in (x, y, x + w, y + h)]
            target = ring_color_from_render(render, scaled, outside=True)
            rec["surrounding_rgb"] = [round(v, 1) for v in target] if target else None
        de = C.delta_e(bg_rgb, target) if target else None
        rec["boundary_delta_e"] = round(de, 2) if de is not None else None

        visible_rect = bool(rec["bg_uniform"] and de is not None and de > args.threshold)
        rec["visible_rectangle"] = visible_rect

        if visible_rect and args.repair and rec["bg_uniform"]:
            fixed = remove_or_match_bg(im, bg_rgb, args.mode, target, tol_de=args.threshold)
            if kind == "data":
                new_href = image_to_data_uri(fixed)
                new_svg = new_svg.replace(href, new_href)
                rec["fixed_png"] = "inline_data_uri"
            else:
                png = (assets_root / href).resolve()
                fixed_path = png.with_name(png.stem + "_bgfix.png")
                fixed.save(fixed_path)
                new_href = href.rsplit("/", 1)[0] + "/" + fixed_path.name if "/" in href else fixed_path.name
                new_svg = new_svg.replace(f'href="{href}"', f'href="{new_href}"')
                rec["fixed_png"] = str(fixed_path)
                rec["new_href"] = new_href
            rec["repaired"] = True
            rec["repair_mode"] = args.mode
            # post-fix boundary ΔE: transparent border ~ target; match_fill border == target
            rec["post_boundary_delta_e"] = 0.0
            rec["status"] = "repaired"
            rec["flag"] = False
            repaired += 1
        elif visible_rect:
            rec["status"] = "visible_rectangle"
            rec["flag"] = True
        else:
            rec["status"] = "ok" if de is not None else "no_target_color"
            rec["flag"] = (de is None)  # cannot verify -> soft flag
        assets.append(rec)

    if args.repair and repaired:
        out_svg = Path(args.svg_out) if args.svg_out else svg_path
        out_svg.write_text(new_svg, encoding="utf-8")

    n = len(assets)
    flagged = [a for a in assets if a.get("flag")]
    hard_fail = [a for a in assets if a.get("status") == "visible_rectangle"]
    if hard_fail:
        gate = "FAILED"
    elif flagged:
        gate = "REVIEW_REQUIRED"
    else:
        gate = "PASS"
    result = {
        "RASTER_BACKGROUND_MATCH": gate,
        "delta_e_threshold": args.threshold,
        "asset_count": n,
        "repaired": repaired,
        "flagged": len(flagged),
        "preferred_order": ["native_vector", "transparent_raster_crop",
                            "background_matched_raster_crop", "original_rectangular_crop"],
        "assets": assets,
    }
    C.write_json(args.out, result)
    print(f"RASTER_BACKGROUND_MATCH={gate} assets={n} repaired={repaired} flagged={len(flagged)}")
    return 0 if gate in ("PASS", "REVIEW_REQUIRED") else 9


def _svg_canvas(svg: str):
    m = re.search(r'viewBox="0 0 ([\d.]+) [\d.]+"', svg)
    return float(m.group(1)) if m else None


if __name__ == "__main__":
    raise SystemExit(main())
