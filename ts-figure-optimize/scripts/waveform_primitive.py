#!/usr/bin/env python3
"""Reusable audio-waveform primitive + classifier.

Visual standard (matches the bar-style waveforms in the reference figures):
  repeated vertical amplitude bars, symmetric above/below a shared horizontal centerline,
  irregular-but-controlled heights, narrow bars with rounded caps, consistent spacing,
  compact grouped segments, panel accent color, EDITABLE native SVG lines (never a screenshot,
  never a sine/zigzag/square/continuous-polyline placeholder).

Output is a native SVG `<g>` of `<line>` bars (`stroke-linecap="round"`), tagged
`data-pb-role="waveform" data-pb-editable="true"` so the DrawAI native-shapes converter maps each
bar to an editable PowerPoint line.

Usable as a library (import the functions) or a CLI:
  python waveform_primitive.py --x 0 --y 0 --width 120 --height 40 --bar-count 24 --color "#1aa39a"
  python waveform_primitive.py --classify some.svg
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402

FORBIDDEN_WAVEFORM_HINT = ("wave", "audio", "mel", "rhythm", "onset", "beat", "tempo", "spectrogram", "clip")


def _deterministic_amplitudes(n: int, seed: int = 7) -> list[float]:
    """Controlled pseudo-random heights in [0.25, 1.0] without Math.random (reproducible)."""
    out = []
    x = (seed * 2654435761) & 0xFFFFFFFF
    for i in range(n):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        frac = (x / 0x7FFFFFFF)
        # shape it so middle bars are taller (typical clip envelope)
        env = 0.55 + 0.45 * math.sin(math.pi * (i + 0.5) / n)
        out.append(round(0.25 + 0.75 * frac * env, 4))
    return out


def waveform_group_svg(x, y, width, height, bar_count=20, amplitudes=None,
                       stroke_width=2.0, color="#1aa39a", spacing=None, gid="wave",
                       seed=7) -> str:
    """Return an editable SVG <g> of symmetric vertical bars about the centerline y+height/2."""
    x, y, width, height = float(x), float(y), float(width), float(height)
    bar_count = max(1, int(bar_count))
    if amplitudes is None:
        amplitudes = _deterministic_amplitudes(bar_count, seed)
    amplitudes = list(amplitudes)[:bar_count] + [0.5] * max(0, bar_count - len(amplitudes))
    cy = y + height / 2.0
    if spacing is None:
        spacing = width / bar_count
    spacing = float(spacing)
    # center the group of bars within width
    total = spacing * (bar_count - 1)
    start = x + (width - total) / 2.0
    half_max = height / 2.0
    lines = [f'<g id="{gid}" data-pb-role="waveform" data-pb-editable="true" '
             f'data-pb-source="waveform_primitive">']
    for i in range(bar_count):
        bx = start + i * spacing
        h = max(stroke_width, abs(float(amplitudes[i])) * half_max)
        lines.append(
            f'<line x1="{bx:.2f}" y1="{cy - h:.2f}" x2="{bx:.2f}" y2="{cy + h:.2f}" '
            f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round"/>'
        )
    lines.append("</g>")
    return "".join(lines)


def multi_segment_waveform(x, y, seg_width, height, n_segments=5, bar_count=8,
                           gap=10.0, color="#1aa39a", stroke_width=2.0, labels=None,
                           ellipsis_before_last=False, gid="waveseg") -> str:
    """Equal-width segments on a shared centerline, consistent spacing, optional centered time
    labels and an editable <text> ellipsis before the final segment (e.g. t1 t2 ... tN)."""
    x, y, seg_width, height, gap = map(float, (x, y, seg_width, height, gap))
    cy = y + height / 2.0
    parts = [f'<g id="{gid}" data-pb-role="waveform" data-pb-editable="true">']
    cursor = x
    for s in range(int(n_segments)):
        if ellipsis_before_last and s == int(n_segments) - 1:
            ex = cursor + gap / 2.0
            parts.append(f'<text x="{ex:.2f}" y="{cy + 3:.2f}" data-pb-role="label" '
                         f'data-pb-editable="true" font-size="12">…</text>')
            cursor += gap
        parts.append(waveform_group_svg(cursor, y, seg_width, height, bar_count=bar_count,
                                        stroke_width=stroke_width, color=color, gid=f"{gid}_{s}", seed=7 + s))
        if labels and s < len(labels):
            lx = cursor + seg_width / 2.0
            parts.append(f'<text x="{lx:.2f}" y="{y + height + 14:.2f}" data-pb-role="label" '
                         f'data-pb-editable="true" font-size="11" text-anchor="middle">{labels[s]}</text>')
        cursor += seg_width + gap
    parts.append("</g>")
    return "".join(parts)


# --------------------------------------------------------------------- classifier

def classify_waveform_svg(svg_text: str) -> dict:
    """Inspect waveform-context elements and judge whether they follow the bar-style standard.

    Only elements EXPLICITLY in a waveform/audio context are judged (data-pb-role/id/class/data-*
    containing wave/audio/mel/rhythm/onset/beat/tempo/clip), so unrelated geometry is never touched.
    """
    bar_groups = len(re.findall(r'data-pb-role="waveform"', svg_text))
    # bar-style line count inside waveform groups (rough: lines with rounded caps)
    rounded_lines = len(re.findall(r'<line\b[^>]*stroke-linecap="round"', svg_text))

    def _ctx(s):
        return any(h in (s or "").lower() for h in FORBIDDEN_WAVEFORM_HINT)

    forbidden = {"sine_curve": 0, "zigzag_or_polyline": 0, "square_wave": 0, "faint_placeholder": 0}
    # <path> in a waveform context: curve commands => sine/curvy placeholder; many line-to
    # segments forming one continuous stroke => zigzag/continuous-polyline placeholder.
    for m in re.finditer(r"<path\b([^>]*)>", svg_text):
        attrs = m.group(1)
        if not _ctx(attrs):
            continue
        d = re.search(r'\bd="([^"]*)"', attrs)
        dval = d.group(1) if d else ""
        if re.search(r"[CSQTAcsqta]", dval):
            forbidden["sine_curve"] += 1
        elif len(re.findall(r"[Ll]", dval)) >= 4 and len(re.findall(r"[Mm]", dval)) <= 2:
            forbidden["zigzag_or_polyline"] += 1
    # <polyline>/<polygon> used as a waveform (continuous line) in context
    for tag in ("polyline", "polygon"):
        for m in re.finditer(r"<" + tag + r"\b([^>]*)>", svg_text):
            attrs = m.group(1)
            if _ctx(attrs):
                pts = re.search(r'points="([^"]*)"', attrs)
                npts = len(re.findall(r"[-\d.]+[ ,]+[-\d.]+", pts.group(1))) if pts else 0
                if npts >= 5:
                    forbidden["zigzag_or_polyline"] += 1
    # square wave: many axis-aligned H/V path segments in context
    for m in re.finditer(r"<path\b([^>]*)>", svg_text):
        attrs = m.group(1)
        if _ctx(attrs) and len(re.findall(r"[HVhv]", attrs)) >= 6:
            forbidden["square_wave"] += 1
    # faint placeholder: waveform-context stroke with very low opacity
    for m in re.finditer(r"<(?:line|path|polyline)\b([^>]*)>", svg_text):
        attrs = m.group(1)
        if _ctx(attrs):
            op = re.search(r'(?:stroke-)?opacity="([\d.]+)"', attrs)
            if op and float(op.group(1)) < 0.25:
                forbidden["faint_placeholder"] += 1

    total_forbidden = sum(forbidden.values())
    has_bar_style = bar_groups > 0 and rounded_lines > 0
    if total_forbidden > 0:
        verdict = "FAILED"
    elif has_bar_style:
        verdict = "PASS"
    else:
        verdict = "NONE"  # no waveform-style elements detected (caller decides if expected)
    return {
        "waveform_groups": bar_groups,
        "rounded_bar_lines": rounded_lines,
        "has_bar_style": has_bar_style,
        "forbidden": forbidden,
        "forbidden_total": total_forbidden,
        "verdict": verdict,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classify", default="", help="classify waveform style in an SVG file")
    ap.add_argument("--x", type=float, default=0)
    ap.add_argument("--y", type=float, default=0)
    ap.add_argument("--width", type=float, default=120)
    ap.add_argument("--height", type=float, default=40)
    ap.add_argument("--bar-count", type=int, default=24)
    ap.add_argument("--stroke-width", type=float, default=2.0)
    ap.add_argument("--color", default="#1aa39a")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if args.classify:
        print(json.dumps(classify_waveform_svg(Path(args.classify).read_text(encoding="utf-8")), indent=2))
        return 0
    g = waveform_group_svg(args.x, args.y, args.width, args.height, bar_count=args.bar_count,
                           stroke_width=args.stroke_width, color=args.color)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {args.width} {args.height}">{g}</svg>')
    if args.out:
        Path(args.out).write_text(svg, encoding="utf-8")
        print(args.out)
    else:
        print(svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
