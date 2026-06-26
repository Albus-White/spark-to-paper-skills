#!/usr/bin/env python3
"""setup_drawai.py — one-command auto-deploy of the VENDORED DrawAI engine for ts-figure-optimize.

The DrawAI SOURCE (~5 MB) is vendored under ts-figure-optimize/engine/ (includes the MPS guard fix).
This script provisions the heavy RUNTIME that is NOT vendored: the ~4 GB model weights (SAM3 /
PaddleOCR / RMBG) + a runtime venv with torch/paddle/transformers/openai-codex/sam3. Updates are
manual (re-vendor the source yourself); this only deploys the runtime.

Strategy (portable): try DrawAI's official `setup local` first; if its bootstrap fails (e.g. the
hardcoded China PaddlePaddle index is unreachable, or the openai-codex prerelease won't resolve via
the default index — both seen behind proxies), fall back to the validated manual install sequence
(paddle from PyPI, CPU torch, openai-codex via pypi.org/simple, editable engine + runtime deps, sam3
editable, triton). Idempotent.

Usage:
  python setup_drawai.py [--engine <vendored dir>] [--device cpu] [--check-only]
                         [--reuse-runtime <existing .local/drawai_runtime>]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import _dotenv  # noqa: F401  -- load unified .env so HF_TOKEN/OPENAI_API_KEY reach the model download

HERE = Path(__file__).resolve().parent
DEFAULT_ENGINE = HERE.parent / "engine"          # ts-figure-optimize/engine (vendored DrawAI)
RUNTIME_DEPS = [
    "paddleocr==3.5.0", "paddlex==3.5.2", "transformers==4.57.6", "timm==1.0.27",
    "opencv-python-headless==4.11.0.86", "numpy==1.26.4", "einops", "kornia==0.8.2",
    "kornia-rs==0.1.11", "pycocotools", "scikit-image",
]
TORCH_INDEX = {"cpu": "https://download.pytorch.org/whl/cpu"}
PYPI = "https://pypi.org/simple/"


def run(cmd, cwd=None, env=None, check=False):
    print("  $ " + " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, text=True)


def out(cmd, cwd=None):
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)


def doctor_ok(engine: Path) -> bool:
    r = out(["uv", "run", "--frozen", "drawai", "doctor", "local"], cwd=engine)
    print(r.stdout[-800:] if r.stdout else r.stderr[-800:])
    return r.returncode == 0 and "status: ok" in (r.stdout or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default=str(DEFAULT_ENGINE))
    ap.add_argument("--device", default="cpu", choices=["cpu", "gpu"])
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--reuse-runtime", default="", help="symlink an existing .local/drawai_runtime (skip 4GB download)")
    a = ap.parse_args()
    engine = Path(a.engine).resolve()
    if not (engine / "src" / "drawai").exists():
        print(f"FATAL: vendored DrawAI not found at {engine} (expected src/drawai). Re-vendor the engine.", file=sys.stderr)
        return 2
    runtime = engine / ".local" / "drawai_runtime"

    print(f"[setup] engine={engine}\n[setup] runtime={runtime}\n[setup] device={a.device}")

    if a.check_only:
        ok = doctor_ok(engine)
        print(f"[setup] doctor: {'OK' if ok else 'NEEDS SETUP'}")
        return 0 if ok else 1

    # 0) reuse an existing runtime by symlink (this machine already has /CS/DrawAI/.local/...)
    if a.reuse_runtime:
        src = Path(a.reuse_runtime).resolve()
        if not src.exists():
            print(f"FATAL: --reuse-runtime path not found: {src}", file=sys.stderr); return 2
        runtime.parent.mkdir(parents=True, exist_ok=True)
        if runtime.is_symlink() or runtime.exists():
            if runtime.is_symlink():
                runtime.unlink()
        if not runtime.exists():
            runtime.symlink_to(src)
            print(f"[setup] symlinked runtime -> {src}")

    # 1) base deps for the engine (lockfile-exact; avoids the openai-codex prerelease re-resolve)
    print("[setup] step 1/4: uv sync --frozen (engine base deps)")
    run(["uv", "sync", "--frozen"], cwd=engine)

    if doctor_ok(engine):
        print("[setup] already provisioned (doctor ok)."); return 0

    # 2) try DrawAI's official one-shot setup (works on networks that can reach its indexes)
    print("[setup] step 2/4: official `drawai setup local` (best-effort)")
    run(["uv", "run", "--frozen", "drawai", "setup", "local", "--device", a.device], cwd=engine)
    if doctor_ok(engine):
        print("[setup] official setup succeeded."); return 0

    # 3) fallback: download models, then build the runtime venv with the validated workaround
    print("[setup] step 3/4: fallback — download models, then manual runtime venv")
    run(["uv", "run", "--frozen", "drawai", "setup", "local", "--download-only", "--device", a.device], cwd=engine)

    rt_py = runtime / ".venv" / "bin" / "python"
    if not rt_py.exists():
        run(["uv", "venv", "--python", "3.12", str(runtime / ".venv")], cwd=engine)
    def pip(args, prerelease=False, index=None, reinstall=False):
        cmd = ["uv", "pip", "install", "--python", str(rt_py)]
        if index:
            cmd += ["--index-url", index]
        if prerelease:
            cmd += ["--prerelease=allow"]
        if reinstall:
            cmd += ["--reinstall-package", "torch", "--reinstall-package", "torchvision"]
        return run(cmd + args, cwd=engine)
    pip(["paddlepaddle==3.2.0"])                                            # PyPI (not the China index)
    pip([f"torch>=2.4,<2.12", "torchvision>=0.19,<0.27"], index=TORCH_INDEX.get(a.device, TORCH_INDEX["cpu"]))
    pip(["openai-codex", "pydantic==2.12.5"], prerelease=True, index=PYPI)
    pip(["-e", str(engine), *RUNTIME_DEPS], prerelease=True, index=PYPI)
    sam3_src = runtime / "source" / "sam3"
    if sam3_src.exists():
        pip(["-e", str(sam3_src)])
    pip(["triton"], index=PYPI)

    # 4) verify
    print("[setup] step 4/4: doctor")
    ok = doctor_ok(engine)
    print(f"[setup] {'DONE — runtime ready' if ok else 'INCOMPLETE — see doctor output above'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
