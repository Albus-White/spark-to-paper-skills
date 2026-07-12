#!/usr/bin/env python3
"""Select and execute a provenance-safe remote-first experiment backend over SSH/rsync."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _dotenv  # noqa: F401

POLICIES = frozenset({"remote_first", "remote_only", "local_only"})
_HOST_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_USER_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_REMOTE_PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]+$")
_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    value = int(raw) if raw else default
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _safe_remote_path(name: str, value: str, default: str = "") -> str:
    value = str(value or default).strip().rstrip("/")
    if not value or not _REMOTE_PATH_RE.fullmatch(value) or ".." in Path(value).parts:
        raise ValueError(f"{name} must be an absolute remote path using only [A-Za-z0-9._/-]")
    return value


@dataclass(frozen=True)
class RemoteExperimentSettings:
    policy: str
    host: str
    user: str
    port: int
    remote_root: str
    remote_env_file: str
    identity_file: str
    known_hosts_file: str
    connect_timeout_seconds: int
    sync_timeout_seconds: int
    allow_local_fallback: bool

    @property
    def configured(self) -> bool:
        return bool(self.host)

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    @property
    def target_id(self) -> str:
        return f"{self.target}:{self.port}"

    def public_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "configured": self.configured,
            "target": self.target_id if self.configured else "",
            "remote_root": self.remote_root,
            "remote_env_file_configured": bool(self.remote_env_file),
            "identity_file_configured": bool(self.identity_file),
            "known_hosts_file_configured": bool(self.known_hosts_file),
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "sync_timeout_seconds": self.sync_timeout_seconds,
            "allow_local_fallback": self.allow_local_fallback,
        }


def load_settings() -> RemoteExperimentSettings:
    policy = os.environ.get("TS_EXPERIMENT_EXECUTION_POLICY", "remote_first").strip() or "remote_first"
    if policy not in POLICIES:
        raise ValueError(f"TS_EXPERIMENT_EXECUTION_POLICY must be one of {sorted(POLICIES)}")
    host = os.environ.get("TS_EXPERIMENT_REMOTE_HOST", "").strip()
    user = os.environ.get("TS_EXPERIMENT_REMOTE_USER", "").strip()
    if host and not _HOST_RE.fullmatch(host):
        raise ValueError("TS_EXPERIMENT_REMOTE_HOST must be a DNS name or IPv4 address without user/port")
    if user and not _USER_RE.fullmatch(user):
        raise ValueError("TS_EXPERIMENT_REMOTE_USER contains unsupported characters")
    if user and not host:
        raise ValueError("TS_EXPERIMENT_REMOTE_USER requires TS_EXPERIMENT_REMOTE_HOST")
    remote_root = _safe_remote_path(
        "TS_EXPERIMENT_REMOTE_ROOT",
        os.environ.get("TS_EXPERIMENT_REMOTE_ROOT", ""),
        "/tmp/ts-experiment-runs",
    )
    remote_env_raw = os.environ.get("TS_EXPERIMENT_REMOTE_ENV_FILE", "").strip()
    remote_env_file = (
        _safe_remote_path("TS_EXPERIMENT_REMOTE_ENV_FILE", remote_env_raw) if remote_env_raw else ""
    )
    identity_raw = os.environ.get("TS_EXPERIMENT_SSH_IDENTITY_FILE", "").strip()
    identity_file = ""
    if identity_raw:
        identity = Path(os.path.expandvars(identity_raw)).expanduser().resolve()
        if not identity.is_file():
            raise ValueError(f"TS_EXPERIMENT_SSH_IDENTITY_FILE not found: {identity}")
        identity_file = str(identity)
    known_raw = os.environ.get("TS_EXPERIMENT_SSH_KNOWN_HOSTS", "").strip()
    known_hosts = ""
    if known_raw:
        known = Path(os.path.expandvars(known_raw)).expanduser().resolve()
        if not known.is_file():
            raise ValueError(f"TS_EXPERIMENT_SSH_KNOWN_HOSTS not found: {known}")
        known_hosts = str(known)
    return RemoteExperimentSettings(
        policy=policy,
        host=host,
        user=user,
        port=_bounded_int("TS_EXPERIMENT_REMOTE_PORT", 22, 1, 65_535),
        remote_root=remote_root,
        remote_env_file=remote_env_file,
        identity_file=identity_file,
        known_hosts_file=known_hosts,
        connect_timeout_seconds=_bounded_int("TS_EXPERIMENT_SSH_CONNECT_TIMEOUT_SECONDS", 15, 3, 60),
        sync_timeout_seconds=_bounded_int("TS_EXPERIMENT_SYNC_TIMEOUT_SECONDS", 900, 30, 3_600),
        allow_local_fallback=_truthy(os.environ.get("TS_EXPERIMENT_ALLOW_LOCAL_FALLBACK"), True),
    )


@dataclass
class ProcessResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error: str = ""


@dataclass
class ExecutionResult:
    backend: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    transport_error: bool = False
    outcome_unknown: bool = False
    remote_workdir: str = ""
    detail: str = ""


def execute_local(command: str, *, cwd: Path, timeout_seconds: int) -> ExecutionResult:
    """Execute through bash with a process-group timeout so children cannot outlive the stage."""
    process = subprocess.Popen(
        ["bash", "-lc", command],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return ExecutionResult("local", process.returncode, stdout, stderr, False)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, 15)
            stdout, stderr = process.communicate(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, 9)
            except OSError:
                process.kill()
            stdout, stderr = process.communicate()
        return ExecutionResult(
            "local", 124, stdout or "", stderr or "", True, detail=f"timeout after {timeout_seconds}s"
        )


def _run(command: list[str], *, timeout: float, cwd: Path | None = None) -> ProcessResult:
    try:
        result = subprocess.run(
            command, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout
        )
        return ProcessResult(result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return ProcessResult(124, stdout, stderr, True, f"timeout after {timeout:g}s")
    except OSError as exc:
        return ProcessResult(127, "", "", False, f"{type(exc).__name__}: {exc}")


def _capture(command: list[str], timeout: int) -> str:
    result = _run(command, timeout=timeout)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def _environment_fingerprint(payload: dict[str, Any]) -> str:
    stable = {key: payload[key] for key in ("os", "python", "framework", "dependencies", "hardware", "cuda")}
    encoded = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def local_environment_snapshot(*, fallback_reason: str = "") -> dict[str, Any]:
    payload = {
        "os": _capture(["uname", "-a"], 20),
        "python": sys.version.split()[0],
        "framework": os.environ.get("RLC_FRAMEWORK", "unspecified"),
        "dependencies": _capture([sys.executable, "-m", "pip", "freeze"], 60).splitlines(),
        "hardware": {
            "gpu": _capture(
                ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], 20
            ),
            "cpu": _capture(["uname", "-m"], 20),
        },
        "cuda": _capture(["nvcc", "--version"], 20),
    }
    payload["execution"] = {
        "backend": "local",
        "target": "localhost",
        "fingerprint": _environment_fingerprint(payload),
        "fallback_reason": fallback_reason,
    }
    return payload


_REMOTE_SNAPSHOT_CODE = r'''
import json, os, subprocess, sys
def capture(args, timeout):
    try:
        return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True, timeout=timeout).strip()
    except Exception:
        return "unavailable"
payload = {
    "os": capture(["uname", "-a"], 20),
    "python": sys.version.split()[0],
    "framework": os.environ.get("RLC_FRAMEWORK", "unspecified"),
    "dependencies": capture([sys.executable, "-m", "pip", "freeze"], 60).splitlines(),
    "hardware": {
        "gpu": capture(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], 20),
        "cpu": capture(["uname", "-m"], 20),
    },
    "cuda": capture(["nvcc", "--version"], 20),
}
print(json.dumps(payload))
'''.strip()


class RemoteExecutor:
    def __init__(self, settings: RemoteExperimentSettings):
        if not settings.configured:
            raise ValueError("remote executor requires TS_EXPERIMENT_REMOTE_HOST")
        self.settings = settings

    def ssh_base(self) -> list[str]:
        command = [
            "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", f"ConnectTimeout={self.settings.connect_timeout_seconds}",
            "-p", str(self.settings.port),
        ]
        if self.settings.identity_file:
            command.extend(["-i", self.settings.identity_file])
        if self.settings.known_hosts_file:
            command.extend(["-o", f"UserKnownHostsFile={self.settings.known_hosts_file}"])
        command.append(self.settings.target)
        return command

    def rsync_shell(self) -> str:
        return shlex.join(self.ssh_base()[:-1])

    def probe(self) -> dict[str, Any]:
        if shutil.which("ssh") is None or shutil.which("rsync") is None:
            return {"ok": False, "error": "local ssh and rsync executables are required"}
        env_source = ""
        if self.settings.remote_env_file:
            env_source = (
                f"test -f {shlex.quote(self.settings.remote_env_file)}; set -a; "
                f". {shlex.quote(self.settings.remote_env_file)}; set +a; "
            )
        remote = (
            f"set -eu; {env_source}command -v bash >/dev/null; command -v timeout >/dev/null; "
            "command -v rsync >/dev/null; command -v python3 >/dev/null; "
            f"mkdir -p {shlex.quote(self.settings.remote_root)}; "
            f"python3 -c {shlex.quote(_REMOTE_SNAPSHOT_CODE)}"
        )
        result = _run(
            [*self.ssh_base(), remote],
            timeout=max(90, self.settings.connect_timeout_seconds + 75),
        )
        if result.returncode != 0:
            return {
                "ok": False,
                "error": result.error or result.stderr.strip() or f"ssh exited {result.returncode}",
                "timed_out": result.timed_out,
            }
        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"remote environment response invalid: {exc}"}
        if not isinstance(payload, dict):
            return {"ok": False, "error": "remote environment response is not an object"}
        payload["execution"] = {
            "backend": "remote",
            "target": self.settings.target_id,
            "fingerprint": _environment_fingerprint(payload),
        }
        return {"ok": True, "environment": payload, "connection": self.settings.public_dict()}

    def _rsync(self, source: str, destination: str, *, inbound: bool) -> ProcessResult:
        command = [
            "rsync", "-az", "--exclude=.git/", "--exclude=.env", "--exclude=.venv/",
            "--exclude=__pycache__/", "--exclude=*.pyc", "--exclude=.ts-execution/" if not inbound else "--exclude=.git/",
            "-e", self.rsync_shell(), source, destination,
        ]
        return _run(command, timeout=self.settings.sync_timeout_seconds)

    def execute(self, command: str, *, cwd: Path, token: str, timeout_seconds: int) -> ExecutionResult:
        safe_token = _TOKEN_RE.sub("-", token).strip("-")[:120]
        if not safe_token:
            raise ValueError("execution token is empty after normalization")
        remote_dir = f"{self.settings.remote_root}/{safe_token}"
        prepare = _run(
            [*self.ssh_base(), f"mkdir -p {shlex.quote(remote_dir)}"],
            timeout=self.settings.connect_timeout_seconds + 15,
        )
        if prepare.returncode != 0:
            return ExecutionResult(
                "remote", prepare.returncode, prepare.stdout, prepare.stderr, prepare.timed_out,
                transport_error=True, detail=prepare.error or "remote_prepare_failed",
                remote_workdir=remote_dir,
            )
        outbound = self._rsync(f"{cwd.resolve()}/", f"{self.settings.target}:{remote_dir}/", inbound=False)
        if outbound.returncode != 0:
            return ExecutionResult(
                "remote", outbound.returncode, outbound.stdout, outbound.stderr, outbound.timed_out,
                transport_error=True, detail=outbound.error or "remote_sync_out_failed",
                remote_workdir=remote_dir,
            )
        meta = f".ts-execution/{safe_token}"
        env_source = ""
        if self.settings.remote_env_file:
            env_source = (
                f"test -f {shlex.quote(self.settings.remote_env_file)}; set -a; "
                f". {shlex.quote(self.settings.remote_env_file)}; set +a; "
            )
        wrapper = (
            f"set -u; cd {shlex.quote(remote_dir)}; mkdir -p {shlex.quote(meta)}; "
            f"date -u +%Y-%m-%dT%H:%M:%SZ > {shlex.quote(meta + '/started_at')}; "
            f"{env_source}set +e; timeout --signal=TERM --kill-after=30s {int(timeout_seconds)}s "
            f"bash -lc {shlex.quote(command)} > {shlex.quote(meta + '/stdout.log')} "
            f"2> {shlex.quote(meta + '/stderr.log')}; rc=$?; "
            f"printf '%s\\n' \"$rc\" > {shlex.quote(meta + '/exit_code')}; exit \"$rc\""
        )
        execution = _run(
            [*self.ssh_base(), wrapper],
            timeout=timeout_seconds + self.settings.connect_timeout_seconds + 45,
        )
        inbound = self._rsync(
            f"{self.settings.target}:{remote_dir}/", f"{cwd.resolve()}/", inbound=True
        )
        local_meta = cwd.resolve() / meta
        exit_path = local_meta / "exit_code"
        started = (local_meta / "started_at").is_file()
        exit_code: int | None = None
        if exit_path.is_file():
            try:
                exit_code = int(exit_path.read_text(encoding="utf-8").strip())
            except ValueError:
                exit_code = None
        stdout = (local_meta / "stdout.log").read_text(encoding="utf-8", errors="replace") \
            if (local_meta / "stdout.log").is_file() else execution.stdout
        stderr = (local_meta / "stderr.log").read_text(encoding="utf-8", errors="replace") \
            if (local_meta / "stderr.log").is_file() else execution.stderr
        if inbound.returncode != 0 or exit_code is None:
            return ExecutionResult(
                "remote", execution.returncode, stdout, stderr, execution.timed_out,
                transport_error=True, outcome_unknown=started and exit_code is None,
                detail=inbound.error or "remote_outcome_unavailable", remote_workdir=remote_dir,
            )
        return ExecutionResult(
            "remote", exit_code, stdout, stderr, exit_code == 124,
            transport_error=False, outcome_unknown=False, remote_workdir=remote_dir,
        )


def select_environment(settings: RemoteExperimentSettings) -> dict[str, Any]:
    if settings.policy == "local_only":
        environment = local_environment_snapshot(fallback_reason="policy_local_only")
        return {"ok": True, "backend": "local", "environment": environment, "remote": settings.public_dict()}
    if settings.configured:
        report = RemoteExecutor(settings).probe()
        if report.get("ok"):
            return {"ok": True, "backend": "remote", "environment": report["environment"],
                    "remote": settings.public_dict()}
        if settings.policy == "remote_only" or not settings.allow_local_fallback:
            return {"ok": False, "backend": "", "remote": settings.public_dict(),
                    "error": report.get("error", "remote preflight failed")}
        fallback = f"remote_preflight_failed: {report.get('error', 'unknown')}"
    else:
        if settings.policy == "remote_only":
            return {"ok": False, "backend": "", "remote": settings.public_dict(),
                    "error": "remote_only policy requires TS_EXPERIMENT_REMOTE_HOST"}
        fallback = "remote_not_configured"
    environment = local_environment_snapshot(fallback_reason=fallback)
    return {"ok": True, "backend": "local", "environment": environment,
            "remote": settings.public_dict(), "fallback_reason": fallback}


def validate_locked_backend(environment_lock: dict[str, Any], current_environment: dict[str, Any]) -> list[str]:
    locked = environment_lock.get("environment") if environment_lock.get("status") == "LOCKED" else None
    if not isinstance(locked, dict):
        return ["environment is not locked"]
    expected = locked.get("execution") if isinstance(locked.get("execution"), dict) else {}
    actual = current_environment.get("execution") if isinstance(current_environment.get("execution"), dict) else {}
    if not expected:
        return [] if actual.get("backend") == "local" else ["legacy environment lock permits local execution only"]
    issues = []
    for key in ("backend", "target", "fingerprint"):
        if expected.get(key) != actual.get(key):
            issues.append(f"locked execution {key} mismatch: {expected.get(key)!r} != {actual.get(key)!r}")
    return issues


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Select remote-first experiment execution environment.")
    parser.add_argument("command", choices=["select", "preflight"])
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    try:
        settings = load_settings()
        report = select_environment(settings) if args.command == "select" else (
            RemoteExecutor(settings).probe() if settings.configured else
            {"ok": False, "error": "TS_EXPERIMENT_REMOTE_HOST is not configured",
             "connection": settings.public_dict()}
        )
    except Exception as exc:  # noqa: BLE001 - configuration/preflight boundary
        report = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if args.out:
        output = Path(args.out).expanduser().resolve()
        payload = report.get("environment") if args.command == "select" and report.get("ok") else report
        _write_json(output, payload)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
