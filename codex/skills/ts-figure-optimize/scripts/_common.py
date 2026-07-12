"""Shared helpers for the image-to-editable-scientific-pptx skill.

Pure-stdlib + numpy + PIL. Optional libs (skimage, lpips/torch, cairosvg) are imported
lazily and their absence is reported honestly rather than faked.
All paths are handled as given; callers pass relative or absolute paths.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

# ----------------------------------------------------------------------------- io

def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


# -------------------------------------------------------------------------- image

def load_gray(path: str | Path, size: tuple[int, int] | None = None) -> np.ndarray:
    im = Image.open(path).convert("L")
    if size is not None and im.size != size:
        im = im.resize(size, Image.LANCZOS)
    return np.asarray(im, dtype=np.float64)


def load_rgb(path: str | Path, size: tuple[int, int] | None = None) -> np.ndarray:
    im = Image.open(path).convert("RGB")
    if size is not None and im.size != size:
        im = im.resize(size, Image.LANCZOS)
    return np.asarray(im, dtype=np.float64)


# --------------------------------------------------------------------- ssim/edges

def ssim(a: np.ndarray, b: np.ndarray, win: int = 7) -> float:
    """Windowed SSIM via box filter. Pure numpy; matches scikit-image closely."""
    from numpy.lib.stride_tricks import sliding_window_view as swv

    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    def boxmean(x: np.ndarray) -> np.ndarray:
        p = win // 2
        xp = np.pad(x, p, mode="reflect")
        return swv(xp, (win, win)).mean(axis=(-1, -2))

    mu_a, mu_b = boxmean(a), boxmean(b)
    va = boxmean(a * a) - mu_a ** 2
    vb = boxmean(b * b) - mu_b ** 2
    vab = boxmean(a * b) - mu_a * mu_b
    s = ((2 * mu_a * mu_b + C1) * (2 * vab + C2)) / ((mu_a ** 2 + mu_b ** 2 + C1) * (va + vb + C2))
    return float(np.clip(s.mean(), -1.0, 1.0))


def ms_ssim(a: np.ndarray, b: np.ndarray, scales: int = 3) -> float | None:
    """Multi-scale SSIM (mean of SSIM over downsampled octaves). None if too small."""
    vals = []
    ca, cb = a, b
    for i in range(scales):
        if min(ca.shape) < 16:
            break
        vals.append(ssim(ca, cb))
        ca = ca[::2, ::2]
        cb = cb[::2, ::2]
    return float(np.mean(vals)) if vals else None


def edge_map(path_or_arr, size: tuple[int, int]) -> np.ndarray:
    if isinstance(path_or_arr, np.ndarray):
        im = Image.fromarray(path_or_arr.astype(np.uint8)).convert("L").resize(size, Image.LANCZOS)
    else:
        im = Image.open(path_or_arr).convert("L").resize(size, Image.LANCZOS)
    a = np.asarray(im.filter(ImageFilter.FIND_EDGES), dtype=np.float64)
    thr = a.mean() + a.std()
    return a > thr


def edge_similarity(src, ren, size: tuple[int, int]) -> dict[str, float]:
    es, er = edge_map(src, size), edge_map(ren, size)
    inter = float(np.logical_and(es, er).sum())
    union = float(np.logical_or(es, er).sum())
    return {
        "edge_iou": round(inter / union, 4) if union else 0.0,
        "src_edge_density": round(float(es.mean()), 4),
        "render_edge_density": round(float(er.mean()), 4),
    }


def color_hist_similarity(src_rgb: np.ndarray, ren_rgb: np.ndarray, bins: int = 8) -> float:
    """Cosine similarity of coarse 3D RGB histograms (0..1)."""
    def hist(x):
        idx = np.clip((x / 256 * bins).astype(int), 0, bins - 1)
        flat = (idx[..., 0] * bins + idx[..., 1]) * bins + idx[..., 2]
        h = np.bincount(flat.ravel(), minlength=bins ** 3).astype(np.float64)
        n = np.linalg.norm(h)
        return h / n if n else h

    hs, hr = hist(src_rgb), hist(ren_rgb)
    return float(np.clip(np.dot(hs, hr), 0.0, 1.0))


def dominant_color(rgb: np.ndarray) -> tuple[float, float, float]:
    return tuple(float(v) for v in rgb.reshape(-1, 3).mean(axis=0))


def color_delta(c1, c2) -> float:
    return float(np.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2))))


def _rgb_to_lab(c) -> tuple[float, float, float]:
    def f(t):
        t = t / 255.0
        t = ((t + 0.055) / 1.055) ** 2.4 if t > 0.04045 else t / 12.92
        return t
    r, g, b = (f(c[0]), f(c[1]), f(c[2]))
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722) / 1.00000
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def g3(t):
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)
    fx, fy, fz = g3(x), g3(y), g3(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(c1, c2) -> float:
    """CIE76 ΔE in Lab space (perceptual color difference). Inputs are RGB 0-255 triples."""
    l1 = _rgb_to_lab(c1)
    l2 = _rgb_to_lab(c2)
    return float(np.sqrt(sum((a - b) ** 2 for a, b in zip(l1, l2))))


def parse_color(value: str):
    """Parse an SVG color (#rgb, #rrggbb, rgb(...), or a few names) to an (r,g,b) tuple or None."""
    if not value:
        return None
    v = value.strip().lower()
    if v in ("none", "transparent"):
        return None
    names = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0),
             "green": (0, 128, 0), "blue": (0, 0, 255), "gray": (128, 128, 128),
             "grey": (128, 128, 128)}
    if v in names:
        return names[v]
    m = re.match(r"#([0-9a-f]{3})$", v)
    if m:
        h = m.group(1)
        return tuple(int(c * 2, 16) for c in h)
    m = re.match(r"#([0-9a-f]{6})$", v)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)", v)
    if m:
        return tuple(int(float(m.group(i))) for i in (1, 2, 3))
    return None


# ----------------------------------------------------------------------- text/ocr

def tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) >= 2]


def svg_text_content(svg_path: str | Path) -> str:
    txt = Path(svg_path).read_text(encoding="utf-8", errors="ignore")
    chunks = re.findall(r"<(?:text|tspan)\b[^>]*>(.*?)</(?:text|tspan)>", txt, re.S | re.I)
    out = []
    for c in chunks:
        c = re.sub(r"<[^>]+>", " ", c)
        for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
            c = c.replace(a, b)
        out.append(c)
    return " ".join(out)


def ocr_text_from_boxir(ocr_json: str | Path) -> str:
    d = read_json(ocr_json)
    boxes = d.get("ocr_text_boxes", d.get("boxes", []))
    return " ".join(str(b.get("text", "")) for b in boxes if isinstance(b, dict))


def token_prf(source_text: str, render_text: str) -> dict[str, Any]:
    src = tokens(source_text)
    ren = tokens(render_text)
    src_set, ren_set = set(src), set(ren)
    if not src_set:
        return {"recall": None, "precision": None, "src_unique": 0}
    matched = sum(1 for t in src_set if t in ren_set)
    prec_match = sum(1 for t in ren_set if t in src_set)
    return {
        "recall": round(matched / len(src_set), 4),
        "precision": round(prec_match / len(ren_set), 4) if ren_set else 0.0,
        "src_unique": len(src_set),
        "render_unique": len(ren_set),
        "matched_unique": matched,
    }


# ------------------------------------------------------------- box-ir / geometry

MATH_CHARS = set("=±×÷≈≤≥≠∑∏∫√∞λμσθΔ∂∇αβγδεφψω̂^_₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴")


def looks_like_formula(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if any(ch in MATH_CHARS for ch in t):
        return True
    # patterns like "L = ...", "y = 0", "z_s", single greek-ish tokens
    if re.search(r"[A-Za-z]\s*=\s*\S", t) and len(t) <= 60:
        return True
    if re.search(r"\b[A-Za-z]_[A-Za-z0-9]", t):
        return True
    return False


def boxir_boxes(box_ir: dict) -> list[dict]:
    return [b for b in box_ir.get("boxes", []) if isinstance(b, dict)]


def bbox_iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return float(inter / ua) if ua > 0 else 0.0


def crop_scaled(img: Image.Image, bbox, src_canvas, dst_size) -> Image.Image:
    """Crop img (already at dst_size) using bbox given in src_canvas coords."""
    cw, ch = src_canvas
    dw, dh = dst_size
    sx, sy = dw / cw, dh / ch
    x1, y1, x2, y2 = bbox
    box = (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
    box = (max(0, box[0]), max(0, box[1]), min(dw, box[2]), min(dh, box[3]))
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    return img.crop(box)


# ---------------------------------------------------------------- combined score

# Weights for the normalized combined global similarity (only available metrics counted).
GLOBAL_WEIGHTS = {
    "ssim": 0.25,
    "ms_ssim": 0.15,
    "lpips_sim": 0.15,        # 1 - lpips distance
    "edge_iou": 0.10,
    "ocr_f1": 0.20,
    "color_hist": 0.05,
    "object_count": 0.05,
    "layout_iou": 0.05,
}


def combined_score(metrics: dict[str, float | None]) -> dict[str, Any]:
    used, total_w, acc = [], 0.0, 0.0
    for key, w in GLOBAL_WEIGHTS.items():
        v = metrics.get(key)
        if v is None:
            continue
        used.append(key)
        total_w += w
        acc += w * float(v)
    score = round(acc / total_w, 4) if total_w else None
    return {"combined": score, "metrics_used": used, "weight_covered": round(total_w, 3)}
