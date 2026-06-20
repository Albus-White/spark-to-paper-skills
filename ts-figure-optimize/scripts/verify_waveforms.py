#!/usr/bin/env python3
"""Audio-waveform style gate (WAVEFORM_STYLE).

Decides whether audio waveforms in the reconstruction follow the bar-style standard and remain
editable. Optionally performs a SAFE local repair: only elements explicitly in a waveform/audio
context are replaced (with the bar-style primitive at the same bbox/color), so unrelated geometry is
never touched. Falls back to REVIEW_REQUIRED rather than a destructive guess.

Usage:
  python verify_waveforms.py --svg semantic.svg --source-ocr ocr.json --out waveform_gate.json
      [--repair --svg-out fixed.svg]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402
import waveform_primitive as WP  # noqa: E402

EXPECT_TOKENS = ("audio", "waveform", "mel", "rhythm", "onset", "beat", "beats", "tempo",
                 "spectrogram", "clip", "sound", "music")


def waveform_expected(ocr_json: Path) -> bool:
    txt = C.ocr_text_from_boxir(ocr_json).lower()
    return any(t in txt for t in EXPECT_TOKENS)


def _bbox_of_element(attrs: str):
    def f(name):
        m = re.search(name + r'="([-\d.]+)"', attrs)
        return float(m.group(1)) if m else None
    pts = re.search(r'points="([^"]*)"', attrs)
    d = re.search(r'\bd="([^"]*)"', attrs)
    xs, ys = [], []
    if pts:
        nums = [float(n) for n in re.findall(r"[-\d.]+", pts.group(1))]
        xs = nums[0::2]; ys = nums[1::2]
    elif d:
        nums = [float(n) for n in re.findall(r"[-\d.]+", d.group(1))]
        xs = nums[0::2]; ys = nums[1::2]
    else:
        x, y, w, h = f("x"), f("y"), f("width"), f("height")
        if None not in (x, y, w, h):
            return (x, y, x + w, y + h)
        return None
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _stroke_color(attrs: str) -> str:
    m = re.search(r'stroke="([^"]+)"', attrs)
    return m.group(1) if m else "#1aa39a"


def repair_waveforms(svg_text: str) -> tuple[str, int]:
    """Replace forbidden waveform-context placeholders with the bar-style primitive (same bbox/color).
    Only elements whose own attributes mention a waveform/audio hint are touched."""
    replaced = 0

    def repl(m):
        nonlocal replaced
        whole, attrs = m.group(0), m.group(1)
        low = attrs.lower()
        if not any(h in low for h in WP.FORBIDDEN_WAVEFORM_HINT):
            return whole
        bbox = _bbox_of_element(attrs)
        if not bbox:
            return whole
        x1, y1, x2, y2 = bbox
        w, h = max(8.0, x2 - x1), max(6.0, y2 - y1)
        color = _stroke_color(attrs)
        replaced += 1
        return WP.waveform_group_svg(x1, y1, w, h, bar_count=max(8, int(w / 5)),
                                     color=color, stroke_width=2.0, gid=f"wave_fix_{replaced}")

    out = re.sub(r"<path\b([^>]*)/>", repl, svg_text)
    out = re.sub(r"<polyline\b([^>]*)/>", repl, out)
    out = re.sub(r"<polygon\b([^>]*)/>", repl, out)
    return out, replaced


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--source-ocr", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--svg-out", default="")
    args = ap.parse_args()

    svg = Path(args.svg).read_text(encoding="utf-8")
    expected = waveform_expected(Path(args.source_ocr))
    cls = WP.classify_waveform_svg(svg)

    repaired = 0
    if args.repair and cls["forbidden_total"] > 0:
        fixed, repaired = repair_waveforms(svg)
        out_svg = Path(args.svg_out or args.svg)
        out_svg.write_text(fixed, encoding="utf-8")
        cls = WP.classify_waveform_svg(fixed)  # re-classify after repair

    if cls["forbidden_total"] > 0:
        gate = "FAILED"
    elif cls["has_bar_style"]:
        gate = "PASS"
    elif expected:
        gate = "REVIEW_REQUIRED"   # waveform expected from OCR but no bar-style waveform present
    else:
        gate = "PASS"             # no waveform expected and none present

    result = {
        "WAVEFORM_STYLE": gate,
        "waveform_expected": expected,
        "classification": cls,
        "repaired_elements": repaired,
        "note": ("Waveforms must be editable bar-style vertical lines (panel accent color), not "
                 "sine/zigzag/square/continuous-polyline placeholders. Use scripts/waveform_primitive.py."),
    }
    C.write_json(args.out, result)
    print(f"WAVEFORM_STYLE={gate} expected={expected} bar_style={cls['has_bar_style']} "
          f"forbidden={cls['forbidden_total']} repaired={repaired}")
    return 0 if gate in ("PASS", "REVIEW_REQUIRED") else 8


if __name__ == "__main__":
    raise SystemExit(main())
