#!/usr/bin/env python3
"""verify_text_gpt.py — final GPT-VISION text check/correction for the hybrid export.

PaddleOCR usually drops sub/superscripts and mis-cases math tokens (onset Ot -> onset Oₜ, Za -> zₐ,
Zsa -> zₛₐ, Xs -> Xₛ). This sends each text region's SOURCE crop to a vision model and asks for the
EXACT text (case + Unicode sub/superscripts + math symbols), so the editable text matches the original.

It writes {box_id: corrected_text} which `build_hybrid_pptx.py --text-overrides` consumes to re-render the
editable text correctly. This is TARGETED text transcription (per small region) — reliable, unlike the
stochastic whole-figure defect detector. Vision backend: OpenAI-compatible (gpt-5.5 default), key from
OPENAI_API_KEY or ~/.codex/auth.json. Do NOT pass temperature (gpt-5.5 rejects it).

Usage:
  python verify_text_gpt.py --source S.png --ocr ocr_boxes.json [--box-ir box_ir.json] \
      --out corrected_texts.json [--batch 10] [--scale 3] [--model gpt-5.5]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
from pathlib import Path

from PIL import Image, ImageDraw

PROMPT = (
    "Each numbered row below is a tightly-cropped snippet of text taken from a scientific figure. "
    "Transcribe the EXACT text in each row. Rules: preserve capitalisation exactly; render subscripts "
    "with Unicode subscript characters (e.g. Oₜ, zₐ, zₛₐ, Xₛ, qₜ) and "
    "superscripts with Unicode superscripts (e.g. x², aʲ); keep math symbols (Δ, λ, ≠, →, ̂ "
    "hats) as shown; do NOT translate, expand, or add words. If a row is unreadable, return its OCR "
    "guess unchanged. Return STRICT JSON mapping the row number (as a string) to the exact text, e.g. "
    "{\"1\":\"onset Oₜ\",\"2\":\"zₐ\"}. Output ONLY the JSON."
)


def _api_key() -> str | None:
    k = os.environ.get("OPENAI_API_KEY")
    if k:
        return k
    p = Path.home() / ".codex" / "auth.json"
    if p.exists():
        try:
            return json.loads(p.read_text()).get("OPENAI_API_KEY")
        except Exception:  # noqa: BLE001
            return None
    return None


def _load_boxes(path: str) -> list[dict]:
    d = json.loads(Path(path).read_text())
    if isinstance(d, dict):
        for k in ("ocr_text_boxes", "boxes", "text_boxes"):
            if isinstance(d.get(k), list):
                return d[k]
    return d if isinstance(d, list) else []


def _scale(box_ir: str | None, W: int, H: int) -> tuple[float, float]:
    if box_ir and Path(box_ir).exists():
        cv = json.loads(Path(box_ir).read_text()).get("canvas", {})
        if cv.get("width") and cv.get("height"):
            return W / float(cv["width"]), H / float(cv["height"])
    return 1.0, 1.0


def _montage(items: list[tuple[int, Image.Image, str]], scale: float) -> str:
    pad, lblw, gap = 6, 46, 8
    crops = [(n, im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS), t) for n, im, t in items]
    Wc = lblw + max(c.width for _, c, _ in crops) + pad * 2
    Hc = sum(c.height + gap for _, c, _ in crops) + pad
    canvas = Image.new("RGB", (Wc, Hc), "white")
    d = ImageDraw.Draw(canvas)
    y = pad
    for n, c, _ in crops:
        d.text((4, y + c.height // 2 - 6), f"{n}", fill="red")
        canvas.paste(c, (lblw, y))
        d.rectangle([lblw - 1, y - 1, lblw + c.width, y + c.height], outline=(220, 220, 220))
        y += c.height + gap
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--box-ir", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--model", default=os.environ.get("VISION_MODEL", "gpt-5.5"))
    ap.add_argument("--base-url", default=os.environ.get("VISION_BASE_URL", ""))
    a = ap.parse_args()

    key = _api_key()
    if not key:
        print("FATAL: no OPENAI_API_KEY / ~/.codex/auth.json", flush=True)
        return 2
    from openai import OpenAI
    client = OpenAI(api_key=key, **({"base_url": a.base_url} if a.base_url else {}))

    src = Image.open(a.source).convert("RGB")
    W, H = src.size
    sx, sy = _scale(a.box_ir or None, W, H)
    boxes = _load_boxes(a.ocr)

    items = []  # (key, crop, ocr_text)
    for i, b in enumerate(boxes):
        bb = b.get("bbox") or b.get("box")
        if not bb or len(bb) < 4:
            continue
        x1, y1, x2, y2 = sorted((bb[0] * sx, bb[2] * sx))[0], sorted((bb[1] * sy, bb[3] * sy))[0], \
            sorted((bb[0] * sx, bb[2] * sx))[1], sorted((bb[1] * sy, bb[3] * sy))[1]
        x1, y1, x2, y2 = int(max(0, x1)), int(max(0, y1)), int(min(W, x2)), int(min(H, y2))
        if x2 - x1 < 3 or y2 - y1 < 3:
            continue
        key_id = b.get("id") or f"idx{i}"
        items.append((key_id, src.crop((x1, y1, x2, y2)), (b.get("text") or "").strip()))

    corrected: dict[str, str] = {}
    changed = 0
    for s in range(0, len(items), a.batch):
        chunk = items[s:s + a.batch]
        numbered = [(j + 1, im, t) for j, (_, im, t) in enumerate(chunk)]
        try:
            r = client.chat.completions.create(model=a.model, messages=[{"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": _montage(numbered, a.scale)}},
            ]}])
            txt = r.choices[0].message.content or ""
            m = re.search(r"\{.*\}", txt, re.S)
            got = json.loads(m.group(0)) if m else {}
        except Exception as e:  # noqa: BLE001
            print(f"  batch {s//a.batch}: vision error {str(e)[:120]}")
            got = {}
        for j, (key_id, _, ocr_t) in enumerate(chunk):
            new = (got.get(str(j + 1)) or "").strip() or ocr_t
            corrected[key_id] = new
            if new != ocr_t:
                changed += 1
                print(f"  fix [{key_id}] {ocr_t!r} -> {new!r}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(corrected, ensure_ascii=False, indent=2))
    print(f"text verify: {len(corrected)} boxes, {changed} corrected -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
