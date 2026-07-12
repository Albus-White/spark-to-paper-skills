#!/usr/bin/env python3
"""Execute a bounded formal experiment on its locked local or remote backend."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rlc = _load("rlc", HERE / "lifecycle.py")
failure = _load("failure", HERE / "classify_failure.py")
bounded = _load("rlc_bounded", HERE / "bounded_execution.py")
backend = _load("rlc_backend", HERE / "execution_backend.py")

AUTO_RETRY = {"INFRASTRUCTURE_FAILURE"}
STATE_CHANGE_REQUIRED = {"DEPENDENCY_FAILURE", "IMPLEMENTATION_FAILURE"}
NO_AUTO_RETRY = {
    "PROTOCOL_FAILURE", "DATA_FAILURE", "BASELINE_REPRODUCTION_FAILURE", "RESOURCE_EXHAUSTED",
    "HYPOTHESIS_NOT_SUPPORTED", "INCONCLUSIVE", *STATE_CHANGE_REQUIRED,
}
MAX_ATTEMPTS = 3
MIN_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 86_400


def classify(text: str, code: int, *, transport_error: bool = False) -> str:
    if code == 0:
        return "NONE"
    if transport_error:
        return "INFRASTRUCTURE_FAILURE"
    for label, pattern in failure.RULES:
        if re.search(pattern, text, re.I):
            return label
    return "INCONCLUSIVE"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--run-type", choices=["baseline", "pilot", "full", "revalidation"], required=True)
    parser.add_argument("--experiment-id", action="append", required=True,
                        help="frozen contract experiment ID; repeat when one run covers multiple units")
    parser.add_argument("--command", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--replicate-id", required=True,
                        help="domain-appropriate replicate identifier: seed, specimen, fold, workload, proof case, etc.")
    parser.add_argument("--random-seed", type=int, default=None)
    parser.add_argument("--input-hash", action="append", required=True,
                        help="name=sha256 for an input, dataset, specimen set, checkpoint, or workload")
    parser.add_argument("--protocol-hash", required=True)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=14_400)
    parser.add_argument("--test-set", action="store_true")
    parser.add_argument("--cwd", default=".")
    args = parser.parse_args()
    try:
        args.input_hashes = dict(item.split("=", 1) for item in args.input_hash)
    except ValueError:
        parser.error("--input-hash values must use name=sha256")
    if any(not key or not value for key, value in args.input_hashes.items()):
        parser.error("--input-hash values must have non-empty names and hashes")
    if any(not re.fullmatch(r"[0-9a-fA-F]{64}", value) for value in args.input_hashes.values()):
        parser.error("--input-hash values must be SHA-256")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.protocol_hash):
        parser.error("--protocol-hash must be SHA-256")
    budget = bounded.StageBudget(
        "experiment", args.max_attempts, args.timeout_seconds,
        stagnation_limit=1, consecutive_failure_limit=2,
    )
    issues = budget.validate()
    if issues or not MIN_TIMEOUT_SECONDS <= args.timeout_seconds <= MAX_TIMEOUT_SECONDS:
        parser.error("; ".join(issues or [
            f"--timeout-seconds must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS}"
        ]))
    return args


def _locked_executor(root: Path):
    lock = rlc.read_json(root / "environment/environment.lock.json")
    locked_environment = lock.get("environment") if lock.get("status") == "LOCKED" else {}
    execution = locked_environment.get("execution") if isinstance(locked_environment, dict) else {}
    locked_kind = execution.get("backend") if isinstance(execution, dict) else "local"
    if locked_kind == "remote":
        settings = backend.load_settings()
        if settings.policy == "local_only":
            raise ValueError("locked remote environment conflicts with local_only execution policy")
        remote = backend.RemoteExecutor(settings)
        return "remote", remote, locked_environment, lock
    if locked_kind not in {None, "local"}:
        raise ValueError(f"unsupported locked execution backend: {locked_kind!r}")
    current = backend.local_environment_snapshot()
    issues = backend.validate_locked_backend(lock, current)
    if issues:
        raise ValueError("; ".join(issues))
    return "local", None, current, lock


def _failure_state(label: str, result) -> dict:
    output = f"{result.stdout}\n{result.stderr}"[-8_000:]
    return {
        "failure_class": label,
        "exit_code": result.returncode,
        "backend": result.backend,
        "transport_error": result.transport_error,
        "outcome_unknown": result.outcome_unknown,
        "output_hash": hashlib.sha256(output.encode()).hexdigest(),
    }


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        print(json.dumps({"ok": False, "error": f"cwd not found: {cwd}"}, indent=2))
        return 2
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    try:
        backend_kind, remote_executor, current_environment, environment_lock = _locked_executor(root)
    except Exception as exc:  # noqa: BLE001 - locked execution preflight boundary
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                          "stop_reason": "execution_environment_mismatch"}, indent=2))
        return 2

    iteration_count = len(list((root / "experiments/iterations").glob("iteration-*")))
    iteration_name = f"iteration-{iteration_count + 1:03d}"
    iteration_dir = root / "experiments/iterations" / iteration_name
    iteration_dir.mkdir(parents=True)
    attempts = []
    budget = bounded.StageBudget(
        "experiment", args.max_attempts, args.timeout_seconds,
        stagnation_limit=1, consecutive_failure_limit=2,
    )
    tracker = bounded.ProgressTracker(budget)
    stop_reason = "attempt_budget_exhausted"

    for attempt in range(1, args.max_attempts + 1):
        log = iteration_dir / f"attempt-{attempt:02d}.log"
        start = time.time()
        if backend_kind == "remote":
            probe = remote_executor.probe()
            if not probe.get("ok"):
                result = backend.ExecutionResult(
                    "remote", 255, "", str(probe.get("error", "remote preflight failed")),
                    bool(probe.get("timed_out")), transport_error=True,
                    detail="locked_remote_preflight_failed",
                )
            else:
                lock_issues = backend.validate_locked_backend(environment_lock, probe["environment"])
                if lock_issues:
                    report = {"ok": False, "execution_backend": "remote", "attempts": attempts,
                              "stop_reason": "execution_environment_mismatch", "errors": lock_issues}
                    (iteration_dir / "iteration_summary.json").write_text(
                        json.dumps(report, indent=2) + "\n", encoding="utf-8"
                    )
                    print(json.dumps(report, indent=2))
                    return 2
                current_environment = probe["environment"]
                token = f"{root.name}-{iteration_name}-attempt-{attempt:02d}"
                result = remote_executor.execute(
                    args.command, cwd=cwd, token=token, timeout_seconds=args.timeout_seconds
                )
        else:
            result = backend.execute_local(args.command, cwd=cwd, timeout_seconds=args.timeout_seconds)
        text = f"{result.stdout}\n{result.stderr}"
        if result.detail:
            text += f"\nEXECUTION_DETAIL: {result.detail}"
        log.write_text(rlc.redact_secrets(text), encoding="utf-8")
        label = classify(text, result.returncode, transport_error=result.transport_error)
        execution_meta = current_environment.get("execution") or {}
        manifest = {
            "run_type": args.run_type,
            "experiment_ids": args.experiment_id,
            "command": args.command,
            "replicate_id": args.replicate_id,
            "random_seed": args.random_seed,
            "config": config,
            "input_artifact_hashes": args.input_hashes,
            "protocol_hash": args.protocol_hash,
            "status": "completed" if result.returncode == 0 else "failed",
            "failure_class": label,
            "test_set_accessed": args.test_set,
            "test_access_purpose": "final confirmation" if args.test_set else "none",
            "exit_code": result.returncode,
            "timed_out": result.timed_out,
            "timeout_seconds": args.timeout_seconds,
            "duration_seconds": round(time.time() - start, 3),
            "raw_log": str(log.relative_to(root)),
            "execution_backend": backend_kind,
            "execution_target": execution_meta.get("target", "localhost"),
            "execution_environment_fingerprint": execution_meta.get("fingerprint", ""),
            "remote_workdir": result.remote_workdir,
            "transport_error": result.transport_error,
            "outcome_unknown": result.outcome_unknown,
        }
        run_id = rlc.register_run(root, manifest)
        attempt_record = {
            "attempt": attempt,
            "run_id": run_id,
            "failure_class": label,
            "exit_code": result.returncode,
            "timed_out": result.timed_out,
            "execution_backend": backend_kind,
            "transport_error": result.transport_error,
            "outcome_unknown": result.outcome_unknown,
            "log": str(log),
        }
        attempts.append(attempt_record)
        if result.returncode == 0:
            stop_reason = "success"
            break
        if result.outcome_unknown:
            stop_reason = "remote_outcome_unknown"
            break
        if label in STATE_CHANGE_REQUIRED:
            stop_reason = "state_change_required"
            break
        if label in NO_AUTO_RETRY:
            stop_reason = "scientific_or_protocol_decision_required"
            break
        progress_stop = tracker.observe(state=_failure_state(label, result), success=False)
        if progress_stop:
            stop_reason = progress_stop
            break
        if label not in AUTO_RETRY:
            stop_reason = "non_retryable_failure"
            break

    final = attempts[-1]
    report = {
        "ok": final["exit_code"] == 0,
        "execution_backend": backend_kind,
        "attempts": attempts,
        "stop_reason": stop_reason,
    }
    (iteration_dir / "iteration_summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
