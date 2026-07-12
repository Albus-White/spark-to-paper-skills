#!/usr/bin/env python3
"""Server-side-only provisioning for the pinned DrawAI GPU model runtime.

Normal Codex clients must use remote_runtime.py and never download SAM3/PaddleOCR/RMBG locally.
Copy the Skill (or its engine) to the GPU host before invoking this helper with --server-side.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import _dotenv  # noqa: F401

HERE = Path(__file__).resolve().parent
DEFAULT_ENGINE = HERE.parent / "engine"


def run(command: list[str], cwd: Path, capture: bool = False,
        timeout_seconds: int = 900) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, cwd=str(cwd), capture_output=capture, text=True,
                              timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return subprocess.CompletedProcess(command, 124, stdout, stderr)


def doctor(engine: Path) -> tuple[bool, str]:
    result = run(["uv", "run", "--frozen", "drawai", "doctor", "local"], engine,
                 capture=True, timeout_seconds=300)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0 and "status: ok" in output.lower(), output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-side", action="store_true",
                        help="required acknowledgement: run model provisioning on the remote GPU host only")
    parser.add_argument("--engine", default=str(DEFAULT_ENGINE),
                        help="maintainer override; installed runs use the bundled engine")
    parser.add_argument("--device", choices=("gpu", "mps"), default="gpu",
                        help="quality runtime only; CPU setup is intentionally not offered")
    parser.add_argument("--source", choices=("modelscope", "huggingface"), default="modelscope")
    parser.add_argument(
        "--torch-backend", choices=("cu126", "cu128", "cu130"), default="",
        help="explicit official CUDA wheel backend when GPU discovery is unavailable in a container",
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--setup-timeout-seconds", type=int, default=7200)
    args = parser.parse_args()

    if not 600 <= args.setup_timeout_seconds <= 14_400:
        parser.error("--setup-timeout-seconds must be between 600 and 14400")

    if not args.server_side:
        print(json.dumps({
            "ok": False,
            "error": "local model provisioning is disabled; configure DRAWAI_REMOTE_* and run remote_runtime.py",
            "server_setup": "rerun this helper with --server-side on the remote GPU host",
        }))
        return 2

    engine = Path(args.engine).expanduser().resolve()
    version_file = engine / "ENGINE_VERSION.txt"
    if not (engine / "src" / "drawai").is_dir() or not version_file.is_file():
        print(json.dumps({"ok": False, "error": f"bundled DrawAI engine missing/incomplete: {engine}"}))
        return 2
    if args.device == "gpu" and not shutil.which("nvidia-smi"):
        print(json.dumps({"ok": False, "error": "GPU quality setup requested but nvidia-smi is unavailable"}))
        return 2

    if args.check_only:
        ok, output = doctor(engine)
        print(json.dumps({"ok": ok, "engine": str(engine), "doctor_tail": output[-1200:]}, ensure_ascii=False))
        return 0 if ok else 1

    sync = run(["uv", "sync", "--frozen"], engine, timeout_seconds=900)
    if sync.returncode != 0:
        print(json.dumps({"ok": False, "error": "uv sync failed", "engine": str(engine)}))
        return 3
    command = ["uv", "run", "--frozen", "drawai", "setup", "local", "--full",
               "--source", args.source, "--device", args.device, "--accept-rmbg-license"]
    if args.torch_backend:
        if args.device != "gpu":
            print(json.dumps({"ok": False, "error": "--torch-backend is valid only with --device gpu"}))
            return 2
        command.extend(["--torch-backend", args.torch_backend])
    if args.source == "huggingface":
        command.append("--accept-sam3-license")
    if args.dry_run:
        command.append("--dry-run")
    setup = run(command, engine, timeout_seconds=args.setup_timeout_seconds)
    if setup.returncode != 0:
        print(json.dumps({"ok": False, "error": "official DrawAI full setup failed",
                          "returncode": setup.returncode, "engine": str(engine)}))
        return 4
    if args.dry_run:
        print(json.dumps({"ok": True, "status": "quality-setup-planned", "engine": str(engine),
                          "device": args.device, "source": args.source,
                          "server_start": "uv run --frozen drawai server model sam3 ocr rmbg --host 127.0.0.1 --device gpu"}))
        return 0
    ok, output = doctor(engine)
    print(json.dumps({"ok": ok, "status": "ready" if ok else "doctor-failed",
                      "engine": str(engine), "device": args.device,
                      "server_start": "uv run --frozen drawai server model sam3 ocr rmbg --host 127.0.0.1 --device gpu",
                      "doctor_tail": output[-1200:]}, ensure_ascii=False))
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
