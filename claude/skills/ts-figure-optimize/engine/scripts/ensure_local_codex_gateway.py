#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_BASE_URL = "http://127.0.0.1:8787/v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATEWAY_DIR = str(REPO_ROOT / ".local" / "drawai_runtime" / "tools" / "local-codex-openai-gateway")
STATE_DIR = Path(".local/local_codex_gateway")


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    gateway_dir = Path(args.gateway_dir).expanduser().resolve(strict=False)
    token = args.api_key if args.api_key is not None else os.getenv("LOCAL_CODEX_GATEWAY_API_KEY", "")

    if is_gateway_ready(base_url, token):
        emit(args, {"status": "running", "base_url": base_url, "started": False})
        return 0

    if args.check_only:
        emit(args, {"status": "not_running", "base_url": base_url, "started": False})
        return 1

    ensure_gateway_build(gateway_dir, args)
    process = start_gateway(gateway_dir, base_url, token, args)
    for _ in range(max(1, args.wait_seconds * 2)):
        if is_gateway_ready(base_url, token):
            emit(
                args,
                {
                    "status": "started",
                    "base_url": base_url,
                    "pid": process.pid,
                    "started": True,
                    "log_path": str(log_path()),
                },
            )
            return 0
        if process.poll() is not None:
            raise RuntimeError(f"local Codex gateway exited early with code {process.returncode}; see {log_path()}")
        time.sleep(0.5)
    raise TimeoutError(f"local Codex gateway did not become ready within {args.wait_seconds}s; see {log_path()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure the local Codex OpenAI-compatible gateway is running.")
    parser.add_argument("--base-url", default=os.getenv("DRAWAI_LOCAL_CODEX_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--gateway-dir", default=os.getenv("DRAWAI_LOCAL_CODEX_GATEWAY_DIR", DEFAULT_GATEWAY_DIR))
    parser.add_argument("--api-key", default=os.getenv("DRAWAI_LOCAL_CODEX_API_KEY"))
    parser.add_argument("--host", default=os.getenv("DRAWAI_LOCAL_CODEX_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DRAWAI_LOCAL_CODEX_PORT", "8787")))
    parser.add_argument("--cwd-mode", choices=("isolated", "repo"), default=os.getenv("DRAWAI_LOCAL_CODEX_CWD_MODE", "isolated"))
    parser.add_argument(
        "--sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default=os.getenv("DRAWAI_LOCAL_CODEX_SANDBOX", "read-only"),
    )
    parser.add_argument("--wait-seconds", type=int, default=int(os.getenv("DRAWAI_LOCAL_CODEX_WAIT_SECONDS", "600")))
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def is_gateway_ready(base_url: str, token: str) -> bool:
    request = urllib.request.Request(f"{base_url}/models", headers=auth_headers(token))
    try:
        with _urlopen(request, base_url, timeout=2) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _urlopen(request: urllib.request.Request, base_url: str, *, timeout: float):
    if _is_loopback_url(base_url):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


def _is_loopback_url(value: str) -> bool:
    hostname = urlparse(str(value or "")).hostname
    return hostname in {"127.0.0.1", "localhost", "::1"}


def ensure_gateway_build(gateway_dir: Path, args: argparse.Namespace) -> None:
    if not gateway_dir.exists():
        raise FileNotFoundError(f"local Codex gateway directory not found: {gateway_dir}")
    cli_path = gateway_dir / "dist/src/cli.js"
    if cli_path.exists():
        return
    run(["npm", "install"], cwd=gateway_dir, quiet=args.quiet)
    run(["npm", "run", "build"], cwd=gateway_dir, quiet=args.quiet)


def start_gateway(gateway_dir: Path, base_url: str, token: str, args: argparse.Namespace) -> subprocess.Popen[str]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = log_path().open("a", encoding="utf-8")
    env = dict(os.environ)
    if token:
        env["LOCAL_CODEX_GATEWAY_API_KEY"] = token
    command = [
        "node",
        "dist/src/cli.js",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--cwd-mode",
        args.cwd_mode,
        "--sandbox",
        args.sandbox,
    ]
    process = subprocess.Popen(
        command,
        cwd=gateway_dir,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    (STATE_DIR / "pid").write_text(str(process.pid), encoding="utf-8")
    (STATE_DIR / "base_url").write_text(base_url + "\n", encoding="utf-8")
    return process


def run(command: list[str], *, cwd: Path, quiet: bool) -> None:
    if not quiet:
        print(f"[local-codex-gateway] {' '.join(command)}", file=sys.stderr)
    subprocess.run(command, cwd=cwd, check=True)


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def log_path() -> Path:
    return STATE_DIR / "gateway.log"


def emit(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if args.quiet:
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ensure_local_codex_gateway failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
