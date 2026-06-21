#!/usr/bin/env python3
"""run_preprocess_ir.py — run ONLY DrawAI's local IR stages (NO Codex).

Runs INSIDE the DrawAI runtime venv (<runtime-root>/.venv/bin/python) because it needs the local
SAM3/PaddleOCR models. Executes the four Codex-free public stages — prepare → detect_structure (SAM3)
→ detect_text (OCR) → assemble_boxir — producing box_ir + ocr for the HYBRID export. The expensive
Codex stages (asset_analyze, svg) are deliberately skipped.

Usage (driven by run_hybrid.py):
  <runtime>/.venv/bin/python run_preprocess_ir.py --config case_001.yaml --runtime-root .local/drawai_runtime \
      --sam3-device cpu --rmbg-device cpu --paddle-device cpu
"""
from __future__ import annotations

import argparse

STAGES = ["prepare", "detect_structure", "detect_text", "assemble_boxir"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--runtime-root", default=".local/drawai_runtime")
    ap.add_argument("--sam3-device", default="cpu")
    ap.add_argument("--rmbg-device", default="cpu")
    ap.add_argument("--paddle-device", default="cpu")
    ap.add_argument("--ocr-det-limit-side-len", type=int, default=1280)
    a = ap.parse_args()

    from drawai.local_runtime import build_local_runtime_components
    from drawai.public_stages import run_public_stage

    comp = build_local_runtime_components(
        runtime_root=a.runtime_root, sam3_device=a.sam3_device, rmbg_device=a.rmbg_device,
        paddle_device=a.paddle_device, ocr_det_limit_side_len=a.ocr_det_limit_side_len)
    for st in STAGES:
        r = run_public_stage(a.config, st, sam3_transport=comp.sam3_transport,
                             ocr_provider=comp.ocr_provider, rmbg_client=comp.rmbg_client)
        print(f"{st} -> {r.get('status')}", flush=True)
        if r.get("status") != "ok":
            raise SystemExit(f"IR stage {st} failed")
    print("IR_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
