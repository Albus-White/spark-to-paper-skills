#!/usr/bin/env python3
"""Render a PPTX to PNG using a REAL office renderer (LibreOffice headless or PowerPoint).

Per the skill contract, the SVG preview must NOT permanently substitute for the PPTX render.
If no office renderer is found, this writes status NOT_RUN (and exits 3) so the orchestrator
records PPTX_RENDER_CHECK=NOT_RUN and refuses an automatic PASS.

Resolution order for the renderer:
  1. $DRAWAI_SOFFICE (explicit path to soffice/libreoffice)
  2. soffice / libreoffice on PATH
  3. ./.spike_logs/lo_env/bin/soffice (local conda install, if present)

Usage: python render_pptx.py <in.pptx> <out.png>
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_soffice() -> str | None:
    env = os.environ.get("DRAWAI_SOFFICE")
    if env and Path(env).exists():
        return env
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    local = Path(".spike_logs/lo_env/bin/soffice")
    if local.exists():
        return str(local)
    return None


def pdf_to_png(pdf: Path, out: Path) -> bool:
    # Prefer pdftoppm, then PyMuPDF (fitz), then pdf2image.
    if shutil.which("pdftoppm"):
        stem = out.with_suffix("")
        subprocess.run(["pdftoppm", "-png", "-r", "150", "-singlefile", str(pdf), str(stem)],
                       check=True, capture_output=True)
        produced = Path(str(stem) + ".png")
        if produced.exists():
            produced.replace(out)
            return True
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf))
        pix = doc[0].get_pixmap(dpi=150)
        pix.save(str(out))
        return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from pdf2image import convert_from_path
        imgs = convert_from_path(str(pdf), dpi=150)
        imgs[0].save(str(out))
        return True
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("out")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sidecar = Path(str(out) + ".render.json")

    soffice = find_soffice()
    if not soffice:
        sidecar.write_text(json.dumps({"status": "NOT_RUN", "reason": "no office renderer (soffice/libreoffice) found"}), encoding="utf-8")
        print(json.dumps({"status": "NOT_RUN"}))
        return 3

    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", td, str(args.pptx)],
                           check=True, capture_output=True, timeout=180)
        except Exception as exc:  # noqa: BLE001
            sidecar.write_text(json.dumps({"status": "FAILED", "reason": f"soffice convert failed: {exc}"}), encoding="utf-8")
            print(json.dumps({"status": "FAILED"}))
            return 4
        pdfs = list(Path(td).glob("*.pdf"))
        if not pdfs:
            sidecar.write_text(json.dumps({"status": "FAILED", "reason": "no pdf produced"}), encoding="utf-8")
            return 4
        if not pdf_to_png(pdfs[0], out):
            sidecar.write_text(json.dumps({"status": "FAILED", "reason": "pdf->png conversion unavailable (install pdftoppm/PyMuPDF/pdf2image)"}), encoding="utf-8")
            print(json.dumps({"status": "FAILED"}))
            return 4
    sidecar.write_text(json.dumps({"status": "OK", "backend": "libreoffice", "soffice": soffice}), encoding="utf-8")
    print(json.dumps({"status": "OK", "soffice": soffice}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
