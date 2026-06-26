from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .codex_cli import codex_executable_candidates, resolve_codex_executable
from .device_profiles import (
    DEFAULT_LOCAL_DEVICE,
    LOCAL_DEVICE_CHOICES,
    LocalDeviceProfile,
    normalize_local_device,
    resolve_local_model_devices,
)
from .local_setup import bootstrap_local_runtime, download_local_models, runtime_venv_python


DEFAULT_RUNTIME_ROOT = ".local/drawai_runtime"
DEFAULT_BASE_CONFIG = "configs/drawai/config.yaml"
DEFAULT_MODEL_SOURCE = "modelscope"
DEFAULT_TORCH_SPEC = "torch>=2.4,<2.12"
DEFAULT_TORCHVISION_SPEC = "torchvision>=0.19,<0.27"
DEFAULT_TORCH_BACKEND = "cpu"
TORCH_BACKEND_INDEX_URLS = {
    "cpu": "https://download.pytorch.org/whl/cpu",
    "cu121": "https://download.pytorch.org/whl/cu121",
    "cu124": "https://download.pytorch.org/whl/cu124",
    "cu126": "https://download.pytorch.org/whl/cu126",
    "cu128": "https://download.pytorch.org/whl/cu128",
    "cu130": "https://download.pytorch.org/whl/cu130",
}


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str
    fix: str = ""

    def to_dict(self) -> dict[str, str]:
        payload = {"name": self.name, "status": self.status, "detail": self.detail}
        if self.fix:
            payload["fix"] = self.fix
        return payload


def setup_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Set up DrawAI local runtimes.")
    subparsers = parser.add_subparsers(dest="target", required=True)

    local = subparsers.add_parser("local", description="Download models and bootstrap the local in-process runtime.")
    local.add_argument("--runtime-root", default=DEFAULT_RUNTIME_ROOT, help="Local runtime root.")
    local.add_argument("--full", action="store_true", help="Set up the full local runtime. This is the default.")
    local.add_argument(
        "--source",
        default=os.environ.get("DRAWAI_MODEL_SOURCE", DEFAULT_MODEL_SOURCE),
        help="Model artifact source: modelscope or huggingface. Default: modelscope.",
    )
    local.add_argument("--hf-token", default="", help="Hugging Face token when --source huggingface needs gated access.")
    local.add_argument("--accept-sam3-license", action="store_true", help="Confirm SAM3 Hugging Face gated access terms.")
    local.add_argument(
        "--accept-rmbg-license",
        dest="accept_rmbg_license",
        action="store_true",
        default=True,
        help="Confirm RMBG-2.0 upstream license/access terms. Enabled by default for the local setup flow.",
    )
    local.add_argument(
        "--no-accept-rmbg-license",
        dest="accept_rmbg_license",
        action="store_false",
        help="Do not confirm RMBG-2.0 terms; setup will stop before downloading RMBG artifacts.",
    )
    local.add_argument("--sam3-source", default="", help="Use a local facebookresearch/sam3 checkout instead of downloading it.")
    local.add_argument("--sam3-checkpoint", default="", help="Use a local sam3.pt checkpoint instead of downloading it.")
    local.add_argument("--sam3-bpe", default="", help="Use a local bpe_simple_vocab_16e6.txt.gz instead of downloading it.")
    local.add_argument("--python", default="", help="Python version for the local runtime venv, e.g. 3.12.")
    local.add_argument(
        "--device",
        choices=LOCAL_DEVICE_CHOICES,
        default=os.environ.get("DRAWAI_DEVICE", DEFAULT_LOCAL_DEVICE),
        help=(
            "Local runtime device profile. cpu is the default; gpu installs a CUDA PyTorch wheel; "
            "mps installs the default macOS PyTorch wheel; auto preserves environment-based selection."
        ),
    )
    local.add_argument(
        "--torch-spec",
        default=os.environ.get("DRAWAI_TORCH_SPEC", DEFAULT_TORCH_SPEC),
        help=f"PyTorch package spec for the local runtime. Default: {DEFAULT_TORCH_SPEC!r}.",
    )
    local.add_argument(
        "--torchvision-spec",
        default=os.environ.get("DRAWAI_TORCHVISION_SPEC", DEFAULT_TORCHVISION_SPEC),
        help=f"Torchvision package spec for the local runtime. Default: {DEFAULT_TORCHVISION_SPEC!r}.",
    )
    local.add_argument(
        "--torch-index-url",
        default=os.environ.get("DRAWAI_TORCH_INDEX_URL", ""),
        help="Optional package index for torch/torchvision, e.g. a PyTorch CPU or CUDA wheel index.",
    )
    local.add_argument(
        "--torch-backend",
        choices=["auto", "default", "cpu", "cu121", "cu124", "cu126", "cu128", "cu130"],
        default=os.environ.get("DRAWAI_TORCH_BACKEND", ""),
        help=(
            "Advanced Torch wheel backend override. When omitted, --device chooses the backend. "
            "auto chooses a compatible CUDA backend from nvidia-smi on Linux, falls back to CPU on Linux "
            "without NVIDIA, and uses the package default elsewhere."
        ),
    )
    local.add_argument(
        "--skip-torch-install",
        action="store_true",
        help="Skip torch/torchvision installation when the runtime venv already contains a compatible build.",
    )
    local.add_argument("--download-only", action="store_true", help="Only download model artifacts; skip bootstrap.")
    local.add_argument("--bootstrap-only", action="store_true", help="Only create/refresh the runtime venv; skip download.")
    local.add_argument("--skip-doctor", action="store_true", help="Skip the automatic doctor check after a full setup.")
    local.add_argument("--dry-run", action="store_true", help="Print planned commands without running them.")

    args = parser.parse_args(argv)
    if args.target == "local":
        return setup_local(args)
    raise AssertionError(f"Unsupported setup target: {args.target}")


def setup_local(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    runtime_root = _runtime_root_path(args.runtime_root, repo_root)
    model_source = _normalize_model_source(args.source)
    env = dict(os.environ)
    env["DRAWAI_LOCAL_RUNTIME_ROOT"] = str(runtime_root)
    env["DRAWAI_MODEL_SOURCE"] = model_source
    local_device = normalize_local_device(args.device)
    env["DRAWAI_DEVICE"] = local_device
    env["DRAWAI_TORCH_SPEC"] = args.torch_spec
    env["DRAWAI_TORCHVISION_SPEC"] = args.torchvision_spec
    torch_backend, torch_index_url = _resolve_setup_torch_install_backend(
        local_device,
        args.torch_backend,
        args.torch_index_url,
    )
    env["DRAWAI_TORCH_BACKEND"] = torch_backend
    if torch_index_url:
        env["DRAWAI_TORCH_INDEX_URL"] = torch_index_url
    if args.skip_torch_install:
        env["DRAWAI_SKIP_TORCH_INSTALL"] = "1"
    if args.hf_token:
        env["HF_TOKEN"] = args.hf_token
    if args.python:
        env["DRAWAI_LOCAL_RUNTIME_PYTHON"] = args.python

    if args.download_only and args.bootstrap_only:
        raise ValueError("--download-only and --bootstrap-only cannot be used together")
    manual_sam3 = _configure_manual_sam3_sources(args, env)

    print("[drawai-setup] setup implementation: python-native")
    _print_setup_environment(env)
    if not args.bootstrap_only:
        if model_source == "huggingface" and not manual_sam3 and not args.accept_sam3_license:
            raise ValueError("SAM3 Hugging Face download requires --accept-sam3-license.")
        if not args.accept_rmbg_license:
            raise ValueError("RMBG-2.0 is enabled by default; rerun without --no-accept-rmbg-license to download it.")
        if manual_sam3:
            print("manual_sam3: using provided SAM3 source/checkpoint/BPE; skipping SAM3 download")
        download_local_models(
            repo_root=repo_root,
            runtime_root=runtime_root,
            model_source=model_source,
            include_paddle=True,
            include_sam3=not manual_sam3,
            include_rmbg=True,
            accept_sam3_license=args.accept_sam3_license,
            accept_rmbg_license=args.accept_rmbg_license,
            dry_run=args.dry_run,
            env=env,
        )
    if not args.download_only:
        bootstrap_local_runtime(
            repo_root=repo_root,
            runtime_root=runtime_root,
            env=env,
            dry_run=args.dry_run,
        )

    if args.dry_run:
        print("dry_run: no files were downloaded or modified")
    else:
        print(f"local_runtime: {runtime_root}")
        if _should_run_post_setup_doctor(args):
            print("post_setup: running uv run drawai doctor local")
            print("")
            return doctor_local(argparse.Namespace(runtime_root=str(runtime_root), json=False))
        if args.skip_doctor:
            print("doctor: skipped (--skip-doctor)")
        print("next: uv run drawai doctor local")
    return 0


def _should_run_post_setup_doctor(args: argparse.Namespace) -> bool:
    return not args.skip_doctor and not args.download_only and not args.bootstrap_only


def _normalize_model_source(value: str) -> str:
    if value in ("modelscope", "ms"):
        return "modelscope"
    if value in ("huggingface", "hf"):
        return "huggingface"
    raise ValueError(f"Unsupported model source: {value!r}. Use modelscope or huggingface.")


def _resolve_torch_install_backend(backend: str, explicit_index_url: str) -> tuple[str, str]:
    normalized = str(backend or DEFAULT_TORCH_BACKEND).strip().lower()
    if normalized not in {"auto", "default", *TORCH_BACKEND_INDEX_URLS}:
        supported = ", ".join(["auto", "default", *TORCH_BACKEND_INDEX_URLS])
        raise ValueError(f"Unsupported torch backend: {backend!r}. Use one of: {supported}.")
    if explicit_index_url:
        return normalized, explicit_index_url
    if normalized == "auto":
        normalized = _detect_torch_backend()
    return normalized, TORCH_BACKEND_INDEX_URLS.get(normalized, "")


def _resolve_setup_torch_install_backend(device: str, backend: str, explicit_index_url: str) -> tuple[str, str]:
    if str(backend or "").strip():
        return _resolve_torch_install_backend(backend, explicit_index_url)

    normalized_device = normalize_local_device(device)
    if normalized_device == "cpu":
        return _resolve_torch_install_backend("cpu", explicit_index_url)
    if normalized_device == "mps":
        if platform.system().lower() != "darwin":
            raise ValueError("--device mps is only supported on macOS. Use --device cpu or --device gpu on this platform.")
        return _resolve_torch_install_backend("default", explicit_index_url)
    if normalized_device == "auto":
        return _resolve_torch_install_backend("auto", explicit_index_url)

    if explicit_index_url:
        return "default", explicit_index_url
    detected = _detect_torch_backend()
    if detected in {"cpu", "default"}:
        raise ValueError(
            "--device gpu requires a detected NVIDIA CUDA runtime. "
            "Install NVIDIA drivers with nvidia-smi available, or pass --torch-backend cu126/cu128/cu130 explicitly."
        )
    return _resolve_torch_install_backend(detected, explicit_index_url)


def _detect_torch_backend() -> str:
    if platform.system().lower() != "linux":
        return "default"
    version = _nvidia_smi_cuda_version()
    if version:
        return _torch_backend_from_cuda_version(version)
    return "cpu"


def _nvidia_smi_cuda_version() -> str:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return ""
    completed = subprocess.run([nvidia_smi], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        return ""
    match = re.search(r"CUDA Version:\s*([0-9]+(?:\.[0-9]+)?)", completed.stdout)
    return match.group(1) if match else ""


def _torch_backend_from_cuda_version(version: str) -> str:
    match = re.match(r"^\s*([0-9]+)(?:\.([0-9]+))?", version)
    if match is None:
        return "cpu"
    major = int(match.group(1))
    minor = int(match.group(2) or "0")
    if (major, minor) >= (13, 0):
        return "cu130"
    if (major, minor) >= (12, 8):
        return "cu128"
    if (major, minor) >= (12, 6):
        return "cu126"
    if (major, minor) >= (12, 4):
        return "cu124"
    if (major, minor) >= (12, 1):
        return "cu121"
    return "cpu"


def _configure_manual_sam3_sources(args: argparse.Namespace, env: dict[str, str]) -> bool:
    values = (args.sam3_source, args.sam3_checkpoint, args.sam3_bpe)
    if not any(values):
        return False
    if not all(values):
        raise ValueError("--sam3-source, --sam3-checkpoint, and --sam3-bpe must be provided together.")
    env["DRAWAI_SAM3_SOURCE"] = str(Path(args.sam3_source).expanduser().resolve(strict=False))
    env["DRAWAI_SAM3_CHECKPOINT_SOURCE"] = str(Path(args.sam3_checkpoint).expanduser().resolve(strict=False))
    env["DRAWAI_SAM3_BPE_SOURCE"] = str(Path(args.sam3_bpe).expanduser().resolve(strict=False))
    return True


def doctor_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Diagnose a DrawAI runtime.")
    subparsers = parser.add_subparsers(dest="target", required=True)

    local = subparsers.add_parser("local", description="Check local in-process runtime readiness.")
    local.add_argument("--runtime-root", default=DEFAULT_RUNTIME_ROOT, help="Local runtime root.")
    local.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    args = parser.parse_args(argv)
    if args.target == "local":
        return doctor_local(args)
    raise AssertionError(f"Unsupported doctor target: {args.target}")


def doctor_local(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    runtime_root = _runtime_root_path(args.runtime_root, repo_root)
    checks = local_runtime_checks(runtime_root=runtime_root, repo_root=repo_root)
    status = "ok" if all(check.status != "missing" for check in checks) else "needs_setup"
    payload = {
        "schema": "drawai.local_doctor.v1",
        "status": status,
        "runtime_root": str(runtime_root),
        "checks": [check.to_dict() for check in checks],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_doctor_report(payload)
    return 0 if status == "ok" else 1


def local_runtime_checks(*, runtime_root: Path, repo_root: Path) -> list[DoctorCheck]:
    runtime_python = runtime_venv_python(runtime_root)
    checks = [
        _check_path("runtime root", runtime_root, "directory", "Run: uv run drawai setup local"),
        _check_path(
            "runtime Python",
            runtime_python,
            "file",
            "Run: uv run drawai setup local --bootstrap-only",
        ),
        _check_path(
            "SAM3 source checkout",
            runtime_root / "source" / "sam3",
            "directory",
            "Run: uv run drawai setup local",
        ),
        _check_path(
            "SAM3 checkpoint",
            runtime_root / "models" / "sam3" / "sam3.pt",
            "file",
            "Run: uv run drawai setup local",
        ),
        _check_path(
            "SAM3 BPE vocab",
            runtime_root / "models" / "sam3" / "bpe_simple_vocab_16e6.txt.gz",
            "file",
            "Run: uv run drawai setup local",
        ),
        _check_path(
            "PaddleOCR detection model",
            runtime_root / "models" / "paddlex" / "official_models" / "PP-OCRv5_server_det" / "inference.pdiparams",
            "file",
            "Run: uv run drawai setup local",
        ),
        _check_path(
            "PaddleOCR recognition model",
            runtime_root / "models" / "paddlex" / "official_models" / "PP-OCRv5_server_rec" / "inference.pdiparams",
            "file",
            "Run: uv run drawai setup local",
        ),
        _check_path(
            "RMBG-2.0 weights",
            runtime_root / "models" / "rmbg2" / "model.safetensors",
            "file",
            "Run: uv run drawai setup local",
        ),
        _check_codex_executable(runtime_root),
        _check_codex_auth(),
        _check_codex_sdk_auth_connectivity(runtime_python),
        _check_runtime_python_import(
            "Workbench/API Python import: Codex SDK",
            Path(sys.executable),
            "import openai_codex; import drawai.codex_python_sdk_svg",
            "Run: uv sync",
        ),
        _check_browser_renderer(),
    ]
    checks.extend(
        [
            _check_runtime_python_import(
                "runtime import: local services",
                runtime_python,
                "import fastapi, uvicorn; import drawai.local_services",
            ),
            _check_runtime_python_import(
                "runtime import: Codex SDK",
                runtime_python,
                "import openai_codex; import drawai.codex_python_sdk_svg",
            ),
            _check_runtime_python_import(
                "runtime import: SAM3",
                runtime_python,
                "from drawai.local_runtime import install_sam3_edt_fallback_if_needed; "
                "install_sam3_edt_fallback_if_needed(); import sam3.model.vitdet",
            ),
        ]
    )
    for script_name in ("download_drawai_local_models.sh", "bootstrap_drawai_local_runtime.sh", "run_drawai_experiment.py"):
        script = repo_root / "scripts" / script_name
        checks.append(
            DoctorCheck(
                name=f"source checkout script: {script_name}",
                status="ok" if script.exists() else "missing",
                detail=str(script),
                fix="" if script.exists() else "Run from a DrawAI source checkout; packaged setup support is not enabled yet.",
            )
        )
    return checks


def run_image_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Run DrawAI on one or more images.")
    parser.add_argument("images", nargs="+", help="Input image path(s).")
    parser.add_argument("--local", action="store_true", help="Use the local in-process SAM3/PaddleOCR/RMBG runtime.")
    parser.add_argument(
        "--device",
        choices=LOCAL_DEVICE_CHOICES,
        default=os.environ.get("DRAWAI_DEVICE", DEFAULT_LOCAL_DEVICE),
        help="Local runtime device profile. Default: cpu. gpu maps Torch models to cuda; mps maps RMBG to mps.",
    )
    parser.add_argument(
        "--profile",
        choices=["local-auto", "local-cpu", "local-accelerated"],
        default="",
        help="Legacy local runtime profile. Prefer --device cpu|gpu|mps|auto.",
    )
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG, help="Base DrawAI YAML config.")
    parser.add_argument("--run-name", default="local_single_svg_ppt", help="Run name used in the timestamped run slug.")
    parser.add_argument("--out", "--run-root", dest="run_root", default="runs", help="Root for timestamped run folders.")
    parser.add_argument("--runtime-root", default=DEFAULT_RUNTIME_ROOT, help="Local runtime root.")
    parser.add_argument("--sam3-device", default="", help="Override SAM3 device.")
    parser.add_argument("--rmbg-device", default="", help="Override RMBG device.")
    parser.add_argument("--paddle-device", default="", help="Override PaddleOCR device.")
    parser.add_argument("--ocr-det-limit-side-len", type=int, default=1280)
    parser.add_argument("--dry-run", action="store_true", help="Create run manifests/configs without executing models.")
    args = parser.parse_args(argv)

    if not args.local:
        parser.error("image shorthand currently requires --local. For staged service runs, use: uv run drawai run all --config ...")

    repo_root = _repo_root()
    if args.profile:
        devices = _profile_devices(args.profile)
    else:
        devices = resolve_local_model_devices(args.device)
    sam3_device = args.sam3_device or devices.sam3_device
    rmbg_device = args.rmbg_device or devices.rmbg_device
    paddle_device = args.paddle_device or devices.paddle_device

    command = [
        sys.executable,
        str(_script("run_drawai_experiment.py")),
        "--local-inprocess",
        "--images",
        *args.images,
        "--run-name",
        args.run_name,
        "--base-config",
        args.base_config,
        "--run-root",
        args.run_root,
        "--purpose",
        "Local single-command DrawAI run",
        "--expected-outcome",
        "Generate semantic SVG, rendered PNG, and PPTX export artifacts",
        "--expected-result",
        "Full DrawAI local pipeline completes for the provided image.",
        "--local-runtime-root",
        args.runtime_root,
        "--sam3-device",
        sam3_device,
        "--rmbg-device",
        rmbg_device,
        "--paddle-device",
        paddle_device,
        "--ocr-det-limit-side-len",
        str(args.ocr_det_limit_side_len),
    ]
    if args.dry_run:
        command.append("--dry-run")
    completed = subprocess.run(command, cwd=repo_root, check=False)
    return int(completed.returncode)


def _profile_devices(profile: str) -> LocalDeviceProfile:
    if profile in {"local-auto", "local-accelerated"}:
        return LocalDeviceProfile(sam3_device="auto", rmbg_device="auto", paddle_device="cpu")
    return LocalDeviceProfile(sam3_device="cpu", rmbg_device="cpu", paddle_device="cpu")


def _check_path(name: str, path: Path, kind: str, fix: str) -> DoctorCheck:
    exists = path.is_dir() if kind == "directory" else path.is_file()
    return DoctorCheck(
        name=name,
        status="ok" if exists else "missing",
        detail=str(path),
        fix="" if exists else fix,
    )


def _check_codex_auth() -> DoctorCheck:
    if os.environ.get("OPENAI_API_KEY"):
        return DoctorCheck("Codex/OpenAI auth", "ok", "OPENAI_API_KEY is set")
    candidates = _codex_auth_candidate_paths()
    for path in candidates:
        if path.exists():
            return DoctorCheck(
                "Codex/OpenAI auth",
                "ok",
                f"{path} (file present; SDK connectivity check follows)",
            )
    searched = ", ".join(str(path) for path in candidates) or "<none>"
    return DoctorCheck(
        "Codex/OpenAI auth",
        "missing",
        f"Checked: {searched}",
        "Set OPENAI_API_KEY or run Codex login before SVG generation.",
    )


def _check_codex_sdk_auth_connectivity(runtime_python: Path) -> DoctorCheck:
    if not runtime_python.is_file():
        return DoctorCheck(
            "Codex SDK auth connectivity",
            "missing",
            str(runtime_python),
            "Run: uv run drawai setup local --bootstrap-only",
        )
    if not _codex_auth_credentials_present():
        searched = ", ".join(str(path) for path in _codex_auth_candidate_paths()) or "<none>"
        return DoctorCheck(
            "Codex SDK auth connectivity",
            "missing",
            f"No OPENAI_API_KEY or Codex auth file. Checked: {searched}",
            "Set OPENAI_API_KEY or run Codex login before SVG generation.",
        )
    timeout = _doctor_codex_connectivity_timeout()
    command = [
        str(runtime_python),
        "-c",
        (
            "from drawai.codex_python_sdk_svg import check_codex_python_sdk_connectivity\n"
            f"print(check_codex_python_sdk_connectivity(timeout_seconds={timeout!r}))\n"
        ),
    ]
    env = dict(os.environ)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        detail = f"timed out after {exc.timeout:g}s"
        return DoctorCheck(
            "Codex SDK auth connectivity",
            "missing",
            detail,
            "Check network/proxy settings, or refresh Codex login before SVG generation.",
        )
    except OSError as exc:
        detail = _safe_doctor_error_excerpt(str(exc))
        return DoctorCheck(
            "Codex SDK auth connectivity",
            "missing",
            detail,
            "Run: uv run drawai setup local --bootstrap-only",
        )
    if completed.returncode == 0:
        detail = (completed.stdout or "").strip() or "Codex SDK request completed"
        return DoctorCheck("Codex SDK auth connectivity", "ok", detail)
    output = (completed.stderr or completed.stdout).strip()
    detail = _safe_doctor_error_excerpt(output or f"exit status {completed.returncode}")
    return DoctorCheck(
        "Codex SDK auth connectivity",
        "missing",
        detail,
        "Refresh Codex login or set a working OPENAI_API_KEY before SVG generation.",
    )


def _codex_auth_credentials_present() -> bool:
    if os.environ.get("OPENAI_API_KEY"):
        return True
    return any(path.exists() for path in _codex_auth_candidate_paths())


def _doctor_codex_connectivity_timeout() -> float:
    raw = os.environ.get("DRAWAI_DOCTOR_CODEX_TIMEOUT_SECONDS", "600").strip()
    return float(raw or "600")


def _safe_doctor_error_excerpt(text: str, *, max_chars: int = 1200) -> str:
    sanitized = re.sub(
        r"(?i)\b(Bearer|Basic)\s+([A-Za-z0-9._~+/=-]{20,}|[A-Za-z0-9._~+/=-]*[._~+/=-][A-Za-z0-9._~+/=-]*)",
        r"\1 <redacted>",
        text,
    )
    sanitized = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "sk-<redacted>", sanitized)
    lines = [line.strip() for line in sanitized.splitlines() if line.strip()]
    excerpt = " | ".join(lines[-6:]) if lines else sanitized.strip()
    if len(excerpt) > max_chars:
        return f"{excerpt[:max_chars]}..."
    return excerpt


def _check_codex_executable(runtime_root: Path) -> DoctorCheck:
    path = resolve_codex_executable(runtime_root)
    if path is not None:
        return DoctorCheck("Codex CLI", "ok", str(path))
    candidates = codex_executable_candidates(runtime_root)
    searched = ", ".join(str(path) for path in candidates)
    return DoctorCheck(
        "Codex CLI",
        "missing",
        f"Checked: {searched}; PATH",
        "Run: uv run drawai setup local --bootstrap-only",
    )


def _check_browser_renderer() -> DoctorCheck:
    from .svg_validation import _browser_renderer_path

    browser_path = _browser_renderer_path()
    browser = str(browser_path) if browser_path is not None else shutil.which("google-chrome-stable")
    if browser:
        return DoctorCheck("SVG browser renderer", "ok", str(browser))
    return DoctorCheck(
        "SVG browser renderer",
        "warn",
        "Chrome/Chromium was not found on PATH.",
        "Install Chrome/Chromium or set DRAWAI_SVG_RENDERER_BROWSER.",
    )


def _check_runtime_python_import(
    name: str,
    runtime_python: Path,
    import_code: str,
    fix: str = "Run: uv run drawai setup local --bootstrap-only",
) -> DoctorCheck:
    if not runtime_python.is_file():
        return DoctorCheck(
            name,
            "missing",
            str(runtime_python),
            fix,
        )
    command = [str(runtime_python), "-c", import_code]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if completed.returncode == 0:
        return DoctorCheck(name, "ok", str(runtime_python))
    output = (completed.stderr or completed.stdout).strip()
    detail = output.splitlines()[-1] if output else f"exit status {completed.returncode}"
    return DoctorCheck(
        name,
        "missing",
        detail,
        fix,
    )


def _codex_auth_candidate_paths() -> list[Path]:
    paths: list[Path] = []

    def append_candidate(path: Path) -> None:
        resolved = path.expanduser().resolve(strict=False)
        if resolved not in paths:
            paths.append(resolved)

    codex_home = os.environ.get("DRAWAI_HOST_CODEX_HOME") or os.environ.get("CODEX_HOME")
    if codex_home:
        append_candidate(Path(codex_home) / "auth.json")
    for home_var in ("DRAWAI_HOST_HOME", "HOME", "USERPROFILE"):
        host_home = os.environ.get(home_var)
        if host_home:
            append_candidate(Path(host_home) / ".codex" / "auth.json")
    append_candidate(Path.home() / ".codex" / "auth.json")
    return paths


_DOCTOR_GROUP_ORDER = (
    "Runtime base",
    "Model assets",
    "Codex",
    "Runtime imports",
    "Source checkout",
    "Other",
)

_DOCTOR_LABELS = {
    "runtime root": "root",
    "runtime Python": "python",
    "SAM3 source checkout": "sam3 src",
    "SAM3 checkpoint": "sam3 pt",
    "SAM3 BPE vocab": "bpe",
    "PaddleOCR detection model": "ocr det",
    "PaddleOCR recognition model": "ocr rec",
    "RMBG-2.0 weights": "rmbg",
    "Codex CLI": "cli",
    "Codex/OpenAI auth": "auth",
    "Codex SDK auth connectivity": "sdk auth",
    "Workbench/API Python import: Codex SDK": "api sdk",
    "SVG browser renderer": "renderer",
    "runtime import: local services": "services",
    "runtime import: Codex SDK": "codex sdk",
    "runtime import: SAM3": "sam3 import",
    "source checkout script: download_drawai_local_models.sh": "download",
    "source checkout script: bootstrap_drawai_local_runtime.sh": "bootstrap",
    "source checkout script: run_drawai_experiment.py": "runner",
}


def _print_doctor_report(payload: dict[str, Any]) -> None:
    checks = list(payload["checks"])
    total = len(checks)
    ok_count = sum(1 for item in checks if item["status"] == "ok")
    warn_count = sum(1 for item in checks if item["status"] == "warn")
    missing_count = sum(1 for item in checks if item["status"] == "missing")

    print("DrawAI local doctor")
    print(f"runtime: {payload['runtime_root']}")
    print(
        f"status: {payload['status']}  ready: {ok_count}/{total}  "
        f"warn: {warn_count}  missing: {missing_count}"
    )
    print(f"health: {_doctor_bar(ok_count, total)}")
    print("")
    print("Readiness map")
    for group_name, group_checks in _group_doctor_checks(checks):
        group_ok = sum(1 for item in group_checks if item["status"] == "ok")
        print(f"  {group_name:<16} {_doctor_bar(group_ok, len(group_checks), width=12)} {group_ok}/{len(group_checks)}")
        for line in _doctor_chip_lines(group_checks):
            print(f"    {line}")
    print("")
    print("Action queue")
    attention = [item for item in checks if item["status"] != "ok"]
    if attention:
        for index, action in enumerate(_doctor_action_groups(attention), start=1):
            print(f"  {index}. {action['title']}")
            for line in _doctor_wrapped_label_lines(action["labels"]):
                print(f"     affects: {line}")
            if action["sample"]:
                print(f"     sample: {_doctor_detail_excerpt(action['sample'])}")
    else:
        print("  none")
    print("")
    if payload["status"] == "ok":
        print("status: ok")
        print("next: uv run drawai run /path/to/image.png --local")
    else:
        print("status: needs_setup")
        print("next: uv run drawai setup local")


def _doctor_bar(value: int, total: int, *, width: int = 24) -> str:
    if total <= 0:
        filled = 0
    else:
        filled = round((value / total) * width)
    filled = max(0, min(width, filled))
    return f"[{'#' * filled}{'.' * (width - filled)}]"


def _group_doctor_checks(checks: Sequence[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in _DOCTOR_GROUP_ORDER}
    for item in checks:
        grouped[_doctor_check_group(str(item.get("name") or ""))].append(item)
    return [(name, grouped[name]) for name in _DOCTOR_GROUP_ORDER if grouped[name]]


def _doctor_check_group(name: str) -> str:
    if name in {"runtime root", "runtime Python", "SVG browser renderer"}:
        return "Runtime base"
    if name in {
        "SAM3 source checkout",
        "SAM3 checkpoint",
        "SAM3 BPE vocab",
        "PaddleOCR detection model",
        "PaddleOCR recognition model",
        "RMBG-2.0 weights",
    }:
        return "Model assets"
    if name in {
        "Codex CLI",
        "Codex/OpenAI auth",
        "Codex SDK auth connectivity",
        "Workbench/API Python import: Codex SDK",
    }:
        return "Codex"
    if name.startswith("runtime import:"):
        return "Runtime imports"
    if name.startswith("source checkout script:"):
        return "Source checkout"
    return "Other"


def _doctor_chip_lines(checks: Sequence[dict[str, Any]], *, line_width: int = 68) -> list[str]:
    lines: list[str] = []
    current = ""
    for item in checks:
        chip = f"{_doctor_status_chip(str(item.get('status') or ''))} {_doctor_check_label(str(item.get('name') or ''))}"
        candidate = chip if not current else f"{current}  {chip}"
        if current and len(candidate) > line_width:
            lines.append(current)
            current = chip
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _doctor_status_chip(status: str) -> str:
    if status == "ok":
        return "[OK]"
    if status == "warn":
        return "[WARN]"
    if status == "missing":
        return "[MISS]"
    return "[?]"


def _doctor_check_label(name: str) -> str:
    return _DOCTOR_LABELS.get(name, name)


def _doctor_detail_excerpt(value: str, *, max_chars: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > max_chars:
        return f"{text[:max_chars]}..."
    return text


def _doctor_action_groups(checks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in checks:
        title = str(item.get("fix") or _doctor_default_action_title(str(item.get("status") or "")))
        group = grouped.setdefault(title, {"title": title, "labels": [], "sample": ""})
        group["labels"].append(_doctor_check_label(str(item.get("name") or "")))
        if not group["sample"] and item.get("detail"):
            group["sample"] = str(item["detail"])
    return list(grouped.values())


def _doctor_default_action_title(status: str) -> str:
    if status == "warn":
        return "Review warning details"
    if status == "missing":
        return "Inspect missing checks"
    return "Inspect doctor check"


def _doctor_wrapped_label_lines(labels: Sequence[str], *, line_width: int = 64) -> list[str]:
    lines: list[str] = []
    current = ""
    for label in labels:
        candidate = label if not current else f"{current}, {label}"
        if current and len(candidate) > line_width:
            lines.append(current)
            current = label
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _print_setup_environment(env: dict[str, str]) -> None:
    for key in (
        "DRAWAI_LOCAL_RUNTIME_ROOT",
        "DRAWAI_DEVICE",
        "DRAWAI_TORCH_SPEC",
        "DRAWAI_TORCHVISION_SPEC",
        "DRAWAI_TORCH_BACKEND",
        "DRAWAI_TORCH_INDEX_URL",
        "DRAWAI_SKIP_TORCH_INSTALL",
    ):
        value = env.get(key)
        if value:
            print(f"{key}={value}")


def _runtime_root_path(value: str | Path, repo_root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve(strict=False)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _script(name: str) -> Path:
    script = _repo_root() / "scripts" / name
    if not script.exists():
        raise FileNotFoundError(f"DrawAI source-checkout script not found: {script}")
    return script
