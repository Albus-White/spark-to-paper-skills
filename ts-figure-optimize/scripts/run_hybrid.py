#!/usr/bin/env python3
"""run_hybrid.py — DEFAULT figure-optimize flow: Codex-free preprocessing (IR) + HYBRID export.

Self-contained / deploy-anywhere: it runs the VENDORED DrawAI engine (ts-figure-optimize/engine) and
that engine's runtime venv — it does NOT depend on being nested inside an outer DrawAI checkout.

Production path (validated to beat pure-A: ~0.91 vs ~0.67 SSIM, and cheaper):
  1. DrawAI DRY-RUN scaffold (config + run dir, no models).
  2. Codex-FREE IR stages in the runtime venv (prepare→SAM3→OCR→Box-IR) via run_preprocess_ir.py.
  3. GPT per-region TEXT correction (verify_text_gpt.py) — fixes OCR-dropped subscripts/case.
  4. HYBRID build (build_hybrid_pptx.py): pixel-exact graphics + editable text → PPTX/PDF/SVG.
  5. Editability verification.

Prereq: run `setup_drawai.py` once to provision the engine runtime (engine/.local/drawai_runtime).
Host python (this interpreter) needs the skill deps in ts-figure-optimize/requirements.txt
(numpy, Pillow, python-pptx, cairosvg, openai).

The legacy PURE-A flow (Codex vector redraw + measured loop) lives in run_reconstruction.py.

Usage:
  python run_hybrid.py --image fig.png --run-name myfig [--runs-root runs] [--device cpu] \
      [--runtime-root .local/drawai_runtime] [--drawai-cmd "uv run --frozen drawai"] [--no-text-gpt]
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _engine() -> Path:
    """Locate the VENDORED DrawAI engine (where `uv run --frozen drawai` runs) so the hybrid flow is a
    self-contained, deploy-anywhere skill. Portable order: $DRAWAI_REPO, else the engine shipped inside
    this skill (ts-figure-optimize/engine), else an upward search for src/drawai, else cwd."""
    env = os.environ.get("DRAWAI_REPO")
    if env and (Path(env) / "src" / "drawai").exists():
        return Path(env)
    vendored = HERE.parent / "engine"
    if (vendored / "src" / "drawai").exists():
        return vendored
    for p in [HERE, *HERE.parents]:
        if (p / "src" / "drawai").exists():
            return p
    return Path.cwd()


def sh(cmd, cwd=None):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd)
    if r.stdout:
        print(r.stdout[-1200:])
    if r.returncode != 0 and r.stderr:
        print(r.stderr[-1200:], file=sys.stderr)
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--runs-root", default="runs", help="output root (relative paths resolve against CWD)")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--runtime-root", default=".local/drawai_runtime",
                    help="DrawAI runtime venv root; relative paths resolve under the vendored engine")
    ap.add_argument("--drawai-cmd", default="uv run --frozen drawai")
    ap.add_argument("--no-text-gpt", action="store_true", help="skip GPT text correction (subscripts may be lost)")
    ap.add_argument("--font", default="")
    a = ap.parse_args()

    engine = _engine()
    image = Path(a.image).resolve()
    # outputs go to the CALLER's location, not inside the skill/engine
    run_root = Path(a.runs_root)
    if not run_root.is_absolute():
        run_root = Path.cwd() / run_root
    run_root = (run_root / a.run_name).resolve()
    L = {k: run_root / k for k in ("drawai", "ir", "source", "comparisons", "final")}
    for d in L.values():
        d.mkdir(parents=True, exist_ok=True)
    drawai_root = L["drawai"] / "runs"
    drawai_cmd = shlex.split(a.drawai_cmd)
    # runtime venv lives under the vendored engine by default (matches setup_drawai.py)
    runtime = Path(a.runtime_root)
    if not runtime.is_absolute():
        runtime = engine / runtime

    # 1) DRY-RUN scaffold (config + run dir, no models, no Codex) — run from the engine
    print(f"[1/5] scaffold config (dry-run)  engine={engine}")
    sh([*drawai_cmd, "run", str(image), "--local", "--run-name", a.run_name,
        "--out", str(drawai_root), "--device", a.device, "--dry-run"], cwd=str(engine))
    cfgs = sorted(drawai_root.glob(f"*/*_{a.run_name}/configs/case_001.yaml"), key=lambda p: p.stat().st_mtime)
    if not cfgs:
        print("FATAL: dry-run did not produce a case config (is the engine runtime set up? run setup_drawai.py)", file=sys.stderr)
        return 2
    cfg = cfgs[-1]
    case_dir = next((cfg.parents[1] / "outputs").glob("case_001*"), None)
    if case_dir is None:
        print("FATAL: case output dir not found", file=sys.stderr)
        return 2

    # 2) Codex-FREE IR stages (runtime venv)
    print("[2/5] preprocess IR (SAM3 + OCR + Box-IR, no Codex)")
    rtpy = runtime / ".venv" / "bin" / "python"
    if not rtpy.exists():
        print(f"FATAL: runtime venv not found at {rtpy} — run setup_drawai.py first (engine={engine})", file=sys.stderr)
        return 2
    r = sh([rtpy, HERE / "run_preprocess_ir.py", "--config", cfg, "--runtime-root", str(runtime),
            "--sam3-device", a.device, "--rmbg-device", a.device, "--paddle-device", a.device], cwd=str(engine))
    if r.returncode != 0:
        return 2

    # 3) collect IR + normalized source
    pairs = [(case_dir / "box_ir/box_ir.json", L["ir"] / "box_ir.json"),
             (case_dir / "ocr/ocr_boxes.json", L["ir"] / "ocr_boxes.json"),
             (case_dir / "inputs/figure.png", L["source"] / "source.png")]
    for s, d in pairs:
        if not s.exists():
            print(f"FATAL: expected IR artifact missing: {s}", file=sys.stderr)
            return 2
        shutil.copy2(s, d)
    src, ocr, boxir = L["source"] / "source.png", L["ir"] / "ocr_boxes.json", L["ir"] / "box_ir.json"

    # 4) GPT text correction (optional) + HYBRID build  (run with the host python; see requirements.txt)
    overrides = L["comparisons"] / "corrected_texts.json"
    if not a.no_text_gpt:
        print("[3/5] GPT text correction")
        sh([sys.executable, HERE / "verify_text_gpt.py", "--source", src, "--ocr", ocr,
            "--box-ir", boxir, "--out", overrides], cwd=str(run_root))
    print("[4/5] build hybrid (exact graphics + editable text)")
    hb = [sys.executable, HERE / "build_hybrid_pptx.py", "--source", src, "--ocr", ocr, "--box-ir", boxir,
          "--out-pptx", L["final"] / "editable_hybrid.pptx", "--out-pdf", L["final"] / "editable_hybrid.pdf",
          "--out-svg", L["final"] / "editable_hybrid.svg", "--out-bg", L["final"] / "_hybrid_bg.png",
          "--report", L["comparisons"] / "hybrid_report.json"]
    if a.font:
        hb += ["--font", a.font]
    if overrides.exists():
        hb += ["--text-overrides", overrides]
    if sh(hb, cwd=str(run_root)).returncode != 0:
        return 2

    # 5) verify editability
    print("[5/5] verify editability")
    sh([sys.executable, HERE / "verify_pptx_editability.py", L["final"] / "editable_hybrid.pptx",
        "--out", L["comparisons"] / "pptx_hybrid.json"], cwd=str(run_root))
    print(f"\nHYBRID done -> {L['final']}/editable_hybrid.{{pptx,pdf,svg}}  (no Codex used)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
