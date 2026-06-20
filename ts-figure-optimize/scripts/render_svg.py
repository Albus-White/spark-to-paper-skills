#!/usr/bin/env python3
"""Render an SVG to PNG. Tries a headless browser (highest fidelity), then cairosvg.

Usage: python render_svg.py <in.svg> <out.png> [--width N]
Exit 0 on success; writes a sidecar <out.png>.render.json describing the backend.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _browser() -> str | None:
    env = os.environ.get("DRAWAI_SVG_RENDERER_BROWSER")
    if env and Path(env).exists():
        return env
    for name in ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        p = shutil.which(name)
        if p:
            return p
    return None


def render(svg: Path, out: Path, width: int | None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    browser = _browser()
    if browser:
        try:
            cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
                   f"--screenshot={out}", f"--window-size={width or 2048},2048",
                   "--default-background-color=00000000", str(svg.resolve().as_uri())]
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            if out.exists():
                return {"backend": "browser", "browser": browser}
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"browser render failed: {exc}\n")
    # cairosvg fallback
    import cairosvg
    # unsafe=True lets cairosvg load local <image> file references (our raster crops); without it
    # file-path crops are silently dropped from the render.
    kwargs = {"url": str(svg), "write_to": str(out), "unsafe": True}
    if width:
        kwargs["output_width"] = width
    cairosvg.svg2png(**kwargs)
    return {"backend": "cairosvg"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=2048)
    args = ap.parse_args()
    info = render(Path(args.svg), Path(args.out), args.width)
    Path(str(args.out) + ".render.json").write_text(json.dumps(info), encoding="utf-8")
    print(json.dumps(info))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
