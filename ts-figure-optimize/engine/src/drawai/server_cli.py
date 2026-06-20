from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse
import urllib.request

from .device_profiles import DEFAULT_LOCAL_DEVICE, LOCAL_DEVICE_CHOICES, resolve_local_model_devices
from .http_utils import urlopen_direct_for_loopback
from .local_setup import runtime_venv_bin, runtime_venv_python


DEFAULT_MODEL_PORT = 18080
DEFAULT_API_PORT = 8890
DEFAULT_FRONTEND_PORT = 5174


def server_cli(argv: Sequence[str]) -> int:
    args = list(argv)
    if not args or args[0] in {"-h", "--help"}:
        print(
            "usage: drawai server {model,api,workbench} ...\n\n"
            "Run DrawAI servers.\n\n"
            "commands:\n"
            "  model      Run SAM3, OCR, and RMBG model runtime services.\n"
            "  api        Run the Workbench API and pipeline backend.\n"
            "  workbench  Alias for server api.\n"
        )
        return 0
    command, remaining = args[0], args[1:]
    if command == "model":
        from .local_services import main as local_services_main

        return local_services_main(remaining)
    if command in {"api", "workbench"}:
        return _server_api_cli(remaining)
    print(f"unknown drawai server command: {command}", file=sys.stderr)
    return 2


def workbench_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Run the DrawAI Workbench frontend or full local workbench stack.")
    parser.add_argument("--api", "--workbench-api", dest="api_url", default="", help="Existing Workbench API URL.")
    parser.add_argument("--host", default=os.environ.get("DRAWAI_WORKBENCH_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DRAWAI_WORKBENCH_FRONTEND_PORT", str(DEFAULT_FRONTEND_PORT))))
    parser.add_argument("--model-api", default="", help="Model runtime base URL used by the self-hosted stack.")
    parser.add_argument(
        "--device",
        choices=LOCAL_DEVICE_CHOICES,
        default=os.environ.get("DRAWAI_DEVICE", DEFAULT_LOCAL_DEVICE),
        help="Local model device profile when the self-hosted stack starts model services.",
    )
    args = parser.parse_args(list(argv))
    if args.api_url:
        return _run_frontend_only(api_url=args.api_url, host=args.host, port=args.port)
    if _is_windows():
        return _run_workbench_native(args)
    env = os.environ.copy()
    if args.model_api:
        env["DRAWAI_MODEL_API"] = args.model_api.rstrip("/")
    env["DRAWAI_DEVICE"] = args.device
    env["DRAWAI_WORKBENCH_HOST"] = args.host
    env["DRAWAI_WORKBENCH_FRONTEND_PORT"] = str(args.port)
    script = _repo_root() / "scripts" / "start_drawai_workbench_local.sh"
    return subprocess.call([str(script)], cwd=_repo_root(), env=env)


def _server_api_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run the DrawAI Workbench API and pipeline backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--workspace", default=os.environ.get("DRAWAI_WORKBENCH_WORKSPACE", ".local/workbench"))
    parser.add_argument("--config", default=os.environ.get("DRAWAI_WORKBENCH_DEFAULT_CONFIG", "configs/drawai/config.yaml"))
    parser.add_argument("--model-api", default=os.environ.get("DRAWAI_MODEL_API", ""), help="Base URL for SAM3, OCR, and RMBG.")
    parser.add_argument("--sam3-api", default=os.environ.get("DRAWAI_SAM3_BASE_URL", ""))
    parser.add_argument("--ocr-api", default=os.environ.get("DRAWAI_OCR_BASE_URL", ""))
    parser.add_argument("--rmbg-api", default=os.environ.get("DRAWAI_RMBG_BASE_URL", ""))
    parser.add_argument(
        "--ocr-timeout-seconds",
        type=float,
        default=_optional_float(os.environ.get("DRAWAI_WORKBENCH_OCR_TIMEOUT_SECONDS")),
        help="Override remote PaddleOCR timeout written into Workbench case configs.",
    )
    parser.add_argument("--no-start-model", action="store_true", help="Do not start a local model runtime subprocess.")
    parser.add_argument("--model-host", default=os.environ.get("DRAWAI_MODEL_HOST", "127.0.0.1"))
    parser.add_argument("--model-port", type=int, default=int(os.environ.get("DRAWAI_MODEL_PORT", str(DEFAULT_MODEL_PORT))))
    parser.add_argument("--runtime-root", default=os.environ.get("DRAWAI_LOCAL_RUNTIME_ROOT", ".local/drawai_runtime"))
    parser.add_argument(
        "--device",
        choices=LOCAL_DEVICE_CHOICES,
        default=os.environ.get("DRAWAI_DEVICE", DEFAULT_LOCAL_DEVICE),
        help="Local model device profile when this API process starts missing model services.",
    )
    parser.add_argument("--sam3-device", default=os.environ.get("DRAWAI_SAM3_DEVICE", ""))
    parser.add_argument("--rmbg-device", default=os.environ.get("DRAWAI_RMBG_DEVICE", ""))
    parser.add_argument("--paddle-device", default=os.environ.get("DRAWAI_PADDLE_DEVICE", ""))
    parser.add_argument("--ocr-det-limit-side-len", type=int, default=int(os.environ.get("DRAWAI_OCR_DET_LIMIT_SIDE_LEN", "1280")))
    args = parser.parse_args(argv)
    devices = resolve_local_model_devices(
        args.device,
        sam3_device=args.sam3_device,
        rmbg_device=args.rmbg_device,
        paddle_device=args.paddle_device,
    )
    args.sam3_device = devices.sam3_device
    args.rmbg_device = devices.rmbg_device
    args.paddle_device = devices.paddle_device

    model_base = (args.model_api or f"http://{args.model_host}:{args.model_port}").rstrip("/")
    sam3_api = (args.sam3_api or model_base).rstrip("/")
    ocr_api = (args.ocr_api or model_base).rstrip("/")
    rmbg_api = (args.rmbg_api or model_base).rstrip("/")
    env = os.environ.copy()
    env["DRAWAI_WORKBENCH_WORKSPACE"] = args.workspace
    env["DRAWAI_WORKBENCH_DEFAULT_CONFIG"] = args.config
    env["DRAWAI_SAM3_BASE_URL"] = sam3_api
    env["DRAWAI_OCR_BASE_URL"] = ocr_api
    env["DRAWAI_RMBG_BASE_URL"] = rmbg_api
    if args.ocr_timeout_seconds is not None:
        if args.ocr_timeout_seconds <= 0:
            raise ValueError("--ocr-timeout-seconds must be positive")
        env["DRAWAI_WORKBENCH_OCR_TIMEOUT_SECONDS"] = str(args.ocr_timeout_seconds)

    model_process = None
    models_to_start = _models_to_start(args)
    if not args.no_start_model and models_to_start:
        model_process = _start_model_server(args, models_to_start)
        time.sleep(0.75)
        if model_process.poll() is not None:
            return int(model_process.returncode or 1)
    try:
        from .workbench.api import create_app, settings_from_env

        os.environ.update(env)
        import uvicorn

        uvicorn.run(create_app(settings_from_env()), host=args.host, port=args.port)
        return 0
    finally:
        if model_process is not None:
            model_process.terminate()
            model_process.wait(timeout=10)


def _models_to_start(args: argparse.Namespace) -> tuple[str, ...]:
    if args.model_api:
        return ()
    selected = []
    if not args.sam3_api:
        selected.append("sam3")
    if not args.ocr_api:
        selected.append("ocr")
    if not args.rmbg_api:
        selected.append("rmbg")
    return tuple(selected)


def _start_model_server(args: argparse.Namespace, models: Sequence[str]) -> subprocess.Popen[str]:
    runtime_root = Path(args.runtime_root).expanduser()
    if not runtime_root.is_absolute():
        runtime_root = _repo_root() / runtime_root
    runtime_python = runtime_venv_python(runtime_root.resolve(strict=False))
    command = [
        str(runtime_python),
        "-m",
        "drawai.local_services",
        *models,
        "--host",
        args.model_host,
        "--runtime-root",
        args.runtime_root,
        "--sam-port",
        str(args.model_port),
        "--ocr-port",
        str(args.model_port),
        "--sam3-device",
        args.sam3_device,
        "--rmbg-device",
        args.rmbg_device,
        "--paddle-device",
        args.paddle_device,
        "--ocr-det-limit-side-len",
        str(args.ocr_det_limit_side_len),
    ]
    return subprocess.Popen(command, cwd=_repo_root(), text=True)


def _run_frontend_only(*, api_url: str, host: str, port: int) -> int:
    if _is_windows():
        return _run_frontend_only_native(api_url=api_url, host=host, port=port)
    env = os.environ.copy()
    env["DRAWAI_WORKBENCH_API_URL"] = api_url.rstrip("/")
    env["DRAWAI_WORKBENCH_HOST"] = host
    env["DRAWAI_WORKBENCH_FRONTEND_PORT"] = str(port)
    return subprocess.call([str(_script("run_drawai_workbench_frontend.sh"))], cwd=_repo_root(), env=env)


def _run_frontend_only_native(*, api_url: str, host: str, port: int) -> int:
    repo_root = _repo_root()
    app_dir = repo_root / "apps" / "workbench"
    env = os.environ.copy()
    env["DRAWAI_WORKBENCH_API_URL"] = api_url.rstrip("/")
    _ensure_workbench_frontend_deps(app_dir)
    return subprocess.call(
        [_npm_executable(), "run", "dev", "--", "--host", host, "--port", str(port)],
        cwd=app_dir,
        env=env,
    )


def _run_workbench_native(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    local_dir = repo_root / ".local"
    local_dir.mkdir(parents=True, exist_ok=True)
    host = args.host
    connect_host = _connect_host(host)
    api_port = int(os.environ.get("DRAWAI_WORKBENCH_API_PORT", str(DEFAULT_API_PORT)))
    model_port = int(os.environ.get("DRAWAI_SAM3_PORT", str(DEFAULT_MODEL_PORT)))
    ocr_port = int(os.environ.get("DRAWAI_OCR_PORT", str(model_port)))
    runtime_root_raw = os.environ.get("DRAWAI_LOCAL_RUNTIME_ROOT", ".local/drawai_runtime")
    runtime_root = Path(runtime_root_raw).expanduser()
    if not runtime_root.is_absolute():
        runtime_root = repo_root / runtime_root
    runtime_root = runtime_root.resolve(strict=False)
    workspace = os.environ.get("DRAWAI_WORKBENCH_WORKSPACE", ".local/workbench")
    config = os.environ.get("DRAWAI_WORKBENCH_DEFAULT_CONFIG", "configs/drawai/config.yaml")
    ocr_timeout_seconds = os.environ.get("DRAWAI_WORKBENCH_OCR_TIMEOUT_SECONDS", "600")
    raw_model_api = args.model_api.strip()
    model_api = (raw_model_api or f"http://{connect_host}:{model_port}").rstrip("/")
    start_local_model = _should_start_local_model(raw_model_api)
    if start_local_model and not _is_loopback_model_api(model_api):
        print(
            f"[drawai-workbench] refusing to auto-start local model runtime for non-loopback DRAWAI_MODEL_API={model_api}",
            file=sys.stderr,
        )
        return 2

    env = _workbench_native_env(
        runtime_root=runtime_root,
        workspace=workspace,
        config=config,
        model_api=model_api,
        ocr_timeout_seconds=ocr_timeout_seconds,
    )
    processes: list[subprocess.Popen[str]] = []
    logs = []
    try:
        if start_local_model:
            model_log = (local_dir / "drawai-local-services.log").open("w", encoding="utf-8", errors="replace")
            logs.append(model_log)
            model_command = [
                str(runtime_venv_python(runtime_root)),
                "-m",
                "drawai.cli",
                "server",
                "model",
                "--host",
                host,
                "--runtime-root",
                str(runtime_root),
                "--device",
                args.device,
                "--sam-port",
                str(model_port),
                "--ocr-port",
                str(ocr_port),
            ]
            processes.append(
                _start_logged_process(
                    model_command,
                    label="model runtime",
                    cwd=repo_root,
                    env=env,
                    log_handle=model_log,
                )
            )
            _wait_for_http("model runtime", f"{model_api}/health", local_dir / "drawai-local-services.log")

        api_log = (local_dir / "workbench-api.log").open("w", encoding="utf-8", errors="replace")
        logs.append(api_log)
        api_command = [
            str(runtime_venv_python(runtime_root)),
            "-m",
            "drawai.cli",
            "server",
            "api",
            "--no-start-model",
            "--host",
            host,
            "--port",
            str(api_port),
            "--workspace",
            workspace,
            "--config",
            config,
            "--model-api",
            model_api,
            "--ocr-timeout-seconds",
            ocr_timeout_seconds,
        ]
        processes.append(
            _start_logged_process(api_command, label="workbench API", cwd=repo_root, env=env, log_handle=api_log)
        )
        _wait_for_http("workbench API", f"http://{connect_host}:{api_port}/api/health", local_dir / "workbench-api.log")

        frontend_log = (local_dir / "workbench-frontend.log").open("w", encoding="utf-8", errors="replace")
        logs.append(frontend_log)
        app_dir = repo_root / "apps" / "workbench"
        _ensure_workbench_frontend_deps(app_dir)
        frontend_env = dict(env)
        frontend_env["DRAWAI_WORKBENCH_API_URL"] = f"http://{connect_host}:{api_port}"
        frontend_command = [
            _npm_executable(),
            "run",
            "dev",
            "--",
            "--host",
            host,
            "--port",
            str(args.port),
        ]
        processes.append(
            _start_logged_process(
                frontend_command,
                label="workbench frontend",
                cwd=app_dir,
                env=frontend_env,
                log_handle=frontend_log,
            )
        )
        _wait_for_http(
            "workbench frontend",
            f"http://{connect_host}:{args.port}/",
            local_dir / "workbench-frontend.log",
            accept="text/html,*/*",
        )

        print(f"Frontend: http://{connect_host}:{args.port}/", flush=True)
        print(f"API: http://{connect_host}:{api_port}/api/health", flush=True)
        print(f"Model API: {model_api}", flush=True)
        print("Logs:", flush=True)
        print("  .local/drawai-local-services.log", flush=True)
        print("  .local/workbench-api.log", flush=True)
        print("  .local/workbench-frontend.log", flush=True)
        print("", flush=True)
        print("Press Ctrl+C to stop DrawAI Workbench.", flush=True)
        return _wait_for_process_exit(processes)
    finally:
        _terminate_processes(processes)
        for handle in logs:
            handle.close()


def _ensure_workbench_frontend_deps(app_dir: Path) -> None:
    if (app_dir / "node_modules" / ".bin" / "vite").is_file():
        return
    subprocess.run(_workbench_frontend_install_command(app_dir), cwd=app_dir, check=True)


def _workbench_frontend_install_command(app_dir: Path) -> list[str]:
    if (app_dir / "package-lock.json").is_file():
        return [_npm_executable(), "ci"]
    return [_npm_executable(), "install"]


def _optional_float(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    return float(raw)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _script(name: str) -> Path:
    script = _repo_root() / "scripts" / name
    if not script.exists():
        raise FileNotFoundError(f"DrawAI source-checkout script not found: {script}")
    return script


def _is_windows() -> bool:
    return os.name == "nt"


def _npm_executable() -> str:
    if _is_windows():
        return shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    return shutil.which("npm") or "npm"


def _connect_host(host: str) -> str:
    return "127.0.0.1" if host in {"0.0.0.0", "::", "[::]"} else host


def _should_start_local_model(raw_model_api: str) -> bool:
    env_value = os.environ.get("DRAWAI_WORKBENCH_START_MODEL")
    if env_value:
        return env_value == "1"
    return _is_loopback_model_api(raw_model_api)


def _is_loopback_model_api(value: str) -> bool:
    if not value:
        return True
    parsed = urlparse(value)
    return parsed.hostname in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}


def _workbench_native_env(
    *,
    runtime_root: Path,
    workspace: str,
    config: str,
    model_api: str,
    ocr_timeout_seconds: str,
) -> dict[str, str]:
    env = os.environ.copy()
    env["DRAWAI_LOCAL_RUNTIME_ROOT"] = str(runtime_root)
    env["DRAWAI_WORKBENCH_WORKSPACE"] = workspace
    env["DRAWAI_WORKBENCH_DEFAULT_CONFIG"] = config
    env["DRAWAI_WORKBENCH_OCR_TIMEOUT_SECONDS"] = ocr_timeout_seconds
    env["DRAWAI_MODEL_API"] = model_api
    env["DRAWAI_SAM3_BASE_URL"] = model_api
    env["DRAWAI_OCR_BASE_URL"] = model_api
    env["DRAWAI_RMBG_BASE_URL"] = model_api
    path_prefix = str(runtime_venv_bin(runtime_root))
    env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    pythonpath_parts = [str(_repo_root() / "src"), str(runtime_root / "source" / "sam3")]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def _start_logged_process(
    command: Sequence[str],
    *,
    label: str,
    cwd: Path,
    env: dict[str, str],
    log_handle,
) -> subprocess.Popen[str]:
    print(f"[drawai-workbench] starting {label}: {' '.join(command)}", flush=True)
    return subprocess.Popen(
        list(command),
        cwd=cwd,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _wait_for_http(name: str, url: str, log_path: Path, *, attempts: int = 600, accept: str = "application/json") -> None:
    request = urllib.request.Request(url, headers={"Accept": accept})
    for _ in range(attempts):
        try:
            with urlopen_direct_for_loopback(request, url, timeout=2):
                return
        except Exception:
            time.sleep(1)
    print(f"[drawai-workbench] {name} did not become ready: {url}", file=sys.stderr, flush=True)
    if log_path.is_file():
        print(f"[drawai-workbench] last lines from {log_path}:", file=sys.stderr, flush=True)
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-80:]:
            print(line, file=sys.stderr, flush=True)
    raise RuntimeError(f"{name} did not become ready: {url}")


def _wait_for_process_exit(processes: Sequence[subprocess.Popen[str]]) -> int:
    try:
        while True:
            for process in processes:
                returncode = process.poll()
                if returncode is not None:
                    return int(returncode)
            time.sleep(1)
    except KeyboardInterrupt:
        print("[drawai-workbench] stopping...", flush=True)
        return 130


def _terminate_processes(processes: Sequence[subprocess.Popen[str]]) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 10
    for process in reversed(processes):
        if process.poll() is not None:
            continue
        timeout = max(0.1, deadline - time.monotonic())
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
