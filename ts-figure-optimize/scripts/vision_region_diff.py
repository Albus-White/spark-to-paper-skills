#!/usr/bin/env python3
"""vision_region_diff.py — GENERAL semantic defect detector via per-region VISION comparison.

The big framework already matches; the remaining errors are SMALL and SEMANTIC (an arrow over a figure,
a cycle icon drawn as a straight arrow, a matrix overlapping its colourbar, misaligned bars, text spilling
out of its box). Pixel metrics (SSIM/edge/colour) cannot see these. So this tiles the figure into small
regions and asks a VISION MODEL to compare [SOURCE | RENDER] of each region and return a STRUCTURED list
of generic defects — reusable for ANY figure, not figure-specific.

Defect taxonomy (generic):
  element_overlap | arrow_error | icon_error | shape_misalignment | text_overflow |
  missing_element | duplicated_element | wrong_position
Font / anti-aliasing / exact-colour differences are IGNORED by contract.

Vision backend is pluggable (OpenAI-compatible chat-with-images):
  --model (env VISION_MODEL, default gpt-5.5) · --base-url (env VISION_BASE_URL) ·
  key from env OPENAI_API_KEY or ~/.codex/auth.json.
(If you have no external vision endpoint, the skill executor — Claude — can read the region_crops.py
pairs and emit the same JSON by hand; this script just AUTOMATES that judgment so the loop is headless.)

Usage:
  python vision_region_diff.py --source S.png --render R.png [--box-ir box_ir.json] \
      --out comparisons/vision_defects.json [--grid 4] [--subtile 1] [--max-regions 24]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402

CATEGORIES = ["element_overlap", "arrow_error", "icon_error", "shape_misalignment",
              "text_overflow", "missing_element", "duplicated_element", "wrong_position"]

PROMPT = (
    "You compare a SOURCE scientific-figure region (LEFT) with its vector RECONSTRUCTION (RIGHT). "
    "The overall layout already matches; your job is to catch the SMALL SEMANTIC defects in the "
    "RIGHT image only. IGNORE font face, anti-aliasing, and exact colour shades — those are allowed "
    "to differ. Report a defect ONLY for: "
    + ", ".join(CATEGORIES) + ". "
    "Examples: an arrow overlapping/crossing a figure (element_overlap); a single-headed arrow where the "
    "source is double-headed, or a reversed arrow (arrow_error); a cycle/loop icon drawn as a straight "
    "arrow or a garbled icon (icon_error); unevenly aligned/sized repeated bars or rows (shape_misalignment); "
    "label text spilling outside its box/panel (text_overflow); a box/icon present in SOURCE but absent in "
    "RIGHT (missing_element); a similarity matrix overlapping its colourbar (element_overlap). "
    "Return STRICT JSON: {\"defects\":[{\"category\":<one of the list>,\"description\":<short>,"
    "\"severity\":\"low|med|high\"}]}. If the RIGHT image is faithful, return {\"defects\":[]}."
)


def _api_key() -> str | None:
    k = os.environ.get("OPENAI_API_KEY")
    if k:
        return k
    for p in (Path(os.environ.get("CODEX_HOME", "")) / "auth.json" if os.environ.get("CODEX_HOME") else None,
              Path.home() / ".codex" / "auth.json"):
        if p and p.exists():
            try:
                return json.loads(p.read_text()).get("OPENAI_API_KEY")
            except Exception:  # noqa: BLE001
                pass
    return None


def _pair_data_uri(src: Image.Image, ren: Image.Image, box, scale: float = 2.0) -> str:
    sc = src.crop(box); rc = ren.crop(box)
    cw, ch = sc.size
    canvas = Image.new("RGB", (cw * 2 + 14, ch + 18), "white")
    canvas.paste(sc, (0, 18)); canvas.paste(rc, (cw + 14, 18))
    d = ImageDraw.Draw(canvas); d.text((2, 4), "SOURCE", fill="black"); d.text((cw + 16, 4), "RENDER", fill="black")
    # upscale so the vision model can see SMALL defects (panel-scale crops are too coarse otherwise)
    if scale and scale != 1.0:
        canvas = canvas.resize((int(canvas.width * scale), int(canvas.height * scale)), Image.LANCZOS)
    buf = io.BytesIO(); canvas.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _regions(src_size, box_ir, grid, subtile):
    W, H = src_size
    regs = []
    if box_ir:
        d = C.read_json(box_ir)
        cw, ch = d.get("canvas", {}).get("width"), d.get("canvas", {}).get("height")
        sx, sy = (W / cw, H / ch) if cw and ch else (1, 1)
        for b in d.get("boxes", []):
            if b.get("type") in ("content_box", "grid"):
                x1, y1, x2, y2 = b["bbox"]
                regs.append((b.get("id"), (x1 * sx, y1 * sy, x2 * sx, y2 * sy)))
    if not regs:
        g = max(2, grid)
        regs = [(f"r{r}c{c}", (c * W / g, r * H / g, (c + 1) * W / g, (r + 1) * H / g))
                for r in range(g) for c in range(g)]
    out = []
    n = max(1, subtile)
    for rid, (x1, y1, x2, y2) in regs:
        for sr in range(n):
            for scc in range(n):
                bx = (x1 + (x2 - x1) * scc / n, y1 + (y2 - y1) * sr / n,
                      x1 + (x2 - x1) * (scc + 1) / n, y1 + (y2 - y1) * (sr + 1) / n)
                out.append((rid if n == 1 else f"{rid}_{sr}{scc}", tuple(int(v) for v in bx)))
    return out


def _ask(client, model, data_uri):
    # NOTE: do NOT set temperature (some models, e.g. gpt-5.5, reject any non-default temperature).
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]}],
    )
    txt = r.choices[0].message.content or ""
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0)) if m else {"defects": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--render", required=True)
    ap.add_argument("--box-ir", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--grid", type=int, default=4)
    ap.add_argument("--subtile", type=int, default=1)
    ap.add_argument("--max-regions", type=int, default=24)
    ap.add_argument("--scale", type=float, default=2.0, help="upscale region crops so small defects are visible")
    ap.add_argument("--model", default=os.environ.get("VISION_MODEL", "gpt-5.5"))
    ap.add_argument("--base-url", default=os.environ.get("VISION_BASE_URL", ""))
    a = ap.parse_args()

    key = _api_key()
    if not key:
        print("FATAL: no vision API key (set OPENAI_API_KEY or ~/.codex/auth.json). "
              "Alternatively run scripts/region_crops.py and let the skill executor (Claude) judge the "
              "pairs by hand into the same JSON schema.", file=sys.stderr)
        return 2
    try:
        from openai import OpenAI
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: openai SDK not available: {e}", file=sys.stderr)
        return 2
    client = OpenAI(api_key=key, **({"base_url": a.base_url} if a.base_url else {}))

    src = Image.open(a.source).convert("RGB"); W, H = src.size
    ren = Image.open(a.render).convert("RGB").resize((W, H), Image.LANCZOS)
    regions = _regions((W, H), a.box_ir or None, a.grid, a.subtile)[: a.max_regions]

    results, total = [], 0
    for rid, box in regions:
        try:
            rep = _ask(client, a.model, _pair_data_uri(src, ren, box, a.scale))
            defects = [d for d in rep.get("defects", []) if isinstance(d, dict) and d.get("category") in CATEGORIES]
        except Exception as e:  # noqa: BLE001
            results.append({"id": rid, "bbox": list(box), "error": str(e)[:160]})
            continue
        if defects:
            total += len(defects)
            results.append({"id": rid, "bbox": list(box), "defects": defects})
    summary = {}
    for r in results:
        for d in r.get("defects", []):
            summary[d["category"]] = summary.get(d["category"], 0) + 1
    out = {"model": a.model, "regions_checked": len(regions), "total_defects": total,
           "by_category": summary, "regions_with_defects": results}
    C.write_json(a.out, out)
    print(f"vision defects: {total} across {len([r for r in results if r.get('defects')])} region(s); "
          f"by category: {summary or '{}'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
