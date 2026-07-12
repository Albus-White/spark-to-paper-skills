from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from drawai.experiment_artifacts import next_timestamped_run_dir, safe_run_slug


RUN_SCHEMA = "drawai.run_manifest.v1"
CASE_SCHEMA = "drawai.case_manifest.v1"
SELECTED_CASE_SCHEMA = "drawai.selected_case.v1"
REQUIRED_COMPLETED_ARTIFACTS = (
    ("semantic_svg", Path("svg") / "semantic.svg"),
    ("semantic_rendered_png", Path("svg") / "rendered.png"),
    ("svg_to_pptx", Path("svg_to_ppt") / "semantic.svg_to_ppt.pptx"),
    ("pipeline_summary", Path("reports") / "pipeline_summary.json"),
    ("stage_status", Path("reports") / "stage_status.json"),
    ("svg_validation_report", Path("reports") / "svg_validation_report.json"),
    ("svg_to_ppt_report", Path("reports") / "svg_to_ppt_export_report.json"),
)
OK_REPORT_STATUSES = {"ok", "success", "passed", "completed"}


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    case_slug: str
    source_image: Path
    source_sha256: str
    config_path: Path
    output_dir: Path
    stdout_log: Path
    stderr_log: Path
    expected_result: str


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    _ensure_host_home_env()
    _maybe_reexec_local_runtime(args, repo_root)
    now = datetime.now().astimezone()
    images = [Path(item).expanduser().resolve(strict=True) for item in args.images]
    mode = args.mode or ("single" if len(images) == 1 else "batch")
    run_slug = safe_run_slug(args.run_name, default="drawai_experiment")
    run_dir = next_timestamped_run_dir(args.run_root, slug=run_slug, now=now)
    run_dir.mkdir(parents=True, exist_ok=False)

    configs_dir = run_dir / "configs"
    logs_dir = run_dir / "logs"
    outputs_dir = run_dir / "outputs"
    reports_dir = run_dir / "reports"
    for directory in (configs_dir, logs_dir, outputs_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    base_config_path = Path(args.base_config).expanduser().resolve(strict=True)
    base_config = _read_yaml_mapping(base_config_path)
    _validate_codex_python_sdk_auth_if_needed(base_config)
    _ensure_local_codex_gateway_if_needed(args, repo_root, base_config)
    cases = _prepare_cases(
        images=images,
        base_config=base_config,
        configs_dir=configs_dir,
        outputs_dir=outputs_dir,
        logs_dir=logs_dir,
        expected_result=args.expected_result,
    )

    run_manifest = _run_manifest(
        run_dir=run_dir,
        mode=mode,
        purpose=args.purpose or args.run_name,
        expected_outcome=args.expected_outcome,
        created_at=now,
        created_by=args.created_by,
        base_config_path=base_config_path,
        case_count=len(cases),
        dry_run=args.dry_run,
        local_inprocess=args.local_inprocess,
        local_runtime_root=args.local_runtime_root,
        sam3_device=args.sam3_device,
        rmbg_device=args.rmbg_device,
        paddle_device=args.paddle_device,
        ocr_det_limit_side_len=args.ocr_det_limit_side_len,
        parallel_public_stages=args.parallel_public_stages,
    )
    _write_json(run_dir / "run_manifest.json", run_manifest)
    _write_selected_cases(run_dir / "selected_cases.jsonl", cases)

    for case in cases:
        _write_json(
            case.output_dir / "case_manifest.json",
            _case_manifest(
                case,
                status="planned",
                dry_run=args.dry_run,
                local_inprocess=args.local_inprocess,
            ),
        )

    if args.dry_run:
        rows = [_status_row(case, status="planned", exitcode=None, duration_seconds=0.0) for case in cases]
    else:
        workers = max(1, min(args.workers, len(cases)))
        rows = _run_cases(
            cases,
            workers=workers,
            local_inprocess=args.local_inprocess,
            local_runtime_root=args.local_runtime_root,
            sam3_device=args.sam3_device,
            rmbg_device=args.rmbg_device,
            paddle_device=args.paddle_device,
            ocr_det_limit_side_len=args.ocr_det_limit_side_len,
            parallel_public_stages=args.parallel_public_stages,
        )

    _write_run_status(reports_dir / "run_status.csv", rows)
    summary = {
        "schema": "drawai.run_summary.v1",
        "run_id": run_dir.name,
        "mode": mode,
        "status": _aggregate_status(rows),
        "case_count": len(cases),
        "success_count": sum(1 for row in rows if row["status"] == "completed"),
        "failure_count": sum(1 for row in rows if row["status"] == "failed"),
        "dry_run": args.dry_run,
        "run_manifest": str(run_dir / "run_manifest.json"),
        "selected_cases": str(run_dir / "selected_cases.jsonl"),
        "run_status": str(reports_dir / "run_status.csv"),
        "cases": rows,
    }
    _write_json(reports_dir / "run_summary.json", summary)
    print(f"run_dir: {run_dir}")
    print(f"run_summary: {reports_dir / 'run_summary.json'}")
    return 0 if summary["status"] in {"planned", "completed"} else 1


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and run a manifest-backed DrawAI CLI experiment.")
    parser.add_argument("--images", nargs="+", required=True, help="Input image paths.")
    parser.add_argument("--run-name", required=True, help="Short run name used in the run directory slug.")
    parser.add_argument("--purpose", default="", help="Human-readable purpose for run_manifest.json.")
    parser.add_argument("--expected-outcome", default="", help="Expected run-level outcome.")
    parser.add_argument("--expected-result", default="", help="Default expected result for each selected case.")
    parser.add_argument("--mode", choices=["single", "batch", "smoke", "rerun", "ablation"], default="")
    parser.add_argument("--base-config", default="configs/drawai/config.yaml", help="Base DrawAI YAML config.")
    parser.add_argument("--run-root", default="runs", help="Root directory for dated run folders.")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent CLI workers.")
    parser.add_argument("--created-by", default="codex")
    parser.add_argument("--dry-run", action="store_true", help="Create manifests/configs/reports without invoking the pipeline.")
    parser.add_argument(
        "--local-inprocess",
        action="store_true",
        help="Run SAM3, PaddleOCR, and RMBG in this process instead of calling the HTTP services.",
    )
    parser.add_argument(
        "--local-runtime-root",
        default=".local/drawai_runtime",
        help="Root containing local model files for --local-inprocess.",
    )
    parser.add_argument(
        "--sam3-device",
        default="cpu",
        help="Torch device for local SAM3: cpu, cuda, mps, or auto. SAM3 MPS falls back to CPU.",
    )
    parser.add_argument(
        "--rmbg-device",
        default="cpu",
        help="Torch device for local RMBG: cpu, cuda, mps, or auto.",
    )
    parser.add_argument("--paddle-device", default="cpu", help="PaddleOCR device for local OCR, e.g. cpu.")
    parser.add_argument(
        "--ocr-det-limit-side-len",
        type=int,
        default=1280,
        help="Local PaddleOCR text_det_limit_side_len; use 0 to match the service default with no local limit.",
    )
    parser.add_argument(
        "--skip-local-codex-gateway-ensure",
        action="store_true",
        help="Do not auto-check/start the local Codex OpenAI gateway for --local-inprocess runs.",
    )
    parser.add_argument(
        "--parallel-public-stages",
        action="store_true",
        help=(
            "For --local-inprocess, run detect_structure and detect_text in parallel. "
            "Default is sequential because PaddleOCR and SAM3 native libraries can segfault when initialized in parallel."
        ),
    )
    return parser.parse_args(argv)


def _ensure_host_home_env() -> None:
    if os.environ.get("DRAWAI_HOST_HOME"):
        return
    home = os.environ.get("HOME")
    if home:
        os.environ["DRAWAI_HOST_HOME"] = str(Path(home).expanduser().resolve())


def _validate_codex_python_sdk_auth_if_needed(base_config: Mapping[str, Any]) -> None:
    if not _uses_codex_python_sdk(base_config):
        return
    if os.environ.get("OPENAI_API_KEY"):
        return

    model_name = _configured_codex_python_sdk_model_name(base_config)
    auth_paths = _codex_auth_candidate_paths()
    for auth_path in auth_paths:
        payload = _read_json_if_exists(auth_path)
        if _codex_auth_payload_supports_model(payload, model_name=model_name):
            return

    searched = ", ".join(str(path) for path in auth_paths) or "<none>"
    model_note = " ChatGPT Codex login or OpenAI API credentials are accepted."
    raise RuntimeError(
        "Codex Python SDK SVG generation requires Codex/OpenAI authentication before running local inference. "
        "Set OPENAI_API_KEY or run `printenv OPENAI_API_KEY | codex login --with-api-key`. "
        f"{model_note} "
        f"Checked: {searched}"
    )


def _uses_codex_python_sdk(base_config: Mapping[str, Any]) -> bool:
    svg_config = base_config.get("svg") if isinstance(base_config.get("svg"), dict) else {}
    model_runtime = base_config.get("model_runtime") if isinstance(base_config.get("model_runtime"), dict) else {}
    generation_backend = str(svg_config.get("generation_backend") or "").strip()
    provider = str(model_runtime.get("provider") or "").strip()
    return generation_backend == "codex_python_sdk_controlled" or provider == "codex-python-sdk"


def _codex_auth_candidate_paths() -> list[Path]:
    paths: list[Path] = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        paths.append(Path(codex_home).expanduser().resolve() / "auth.json")
    host_home = os.environ.get("DRAWAI_HOST_HOME") or os.environ.get("HOME")
    if host_home:
        paths.append(Path(host_home).expanduser().resolve() / ".codex" / "auth.json")
    return paths


def _configured_codex_python_sdk_model_name(base_config: Mapping[str, Any]) -> str:
    model_runtime = base_config.get("model_runtime") if isinstance(base_config.get("model_runtime"), dict) else {}
    model_name = str(model_runtime.get("model_name") or "").strip()
    return "" if model_name.lower() in {"auto", "default", "codex-default"} else model_name


def _codex_auth_payload_supports_model(payload: Mapping[str, Any], *, model_name: str) -> bool:
    if payload.get("OPENAI_API_KEY"):
        return True
    auth_mode = str(payload.get("auth_mode") or "").strip().lower()
    tokens = payload.get("tokens")
    if auth_mode == "chatgpt":
        return bool(tokens)
    return auth_mode in {"api_key", "apikey", "openai", "access_token"} and bool(tokens)


def _maybe_reexec_local_runtime(args: argparse.Namespace, repo_root: Path) -> None:
    if not args.local_inprocess or args.dry_run or os.environ.get("DRAWAI_LOCAL_RUNTIME_REEXEC") == "1":
        return
    runtime_root = _runtime_root_path(args.local_runtime_root, repo_root)
    venv_python = runtime_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        raise FileNotFoundError(
            f"Local DrawAI runtime venv not found: {venv_python}. "
            "Run scripts/bootstrap_drawai_local_runtime.sh first."
        )
    if Path(sys.prefix).resolve() == (runtime_root / ".venv").resolve():
        return
    env = dict(os.environ)
    env["DRAWAI_LOCAL_RUNTIME_REEXEC"] = "1"
    os.execve(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]], env)


def _ensure_local_codex_gateway_if_needed(
    args: argparse.Namespace,
    repo_root: Path,
    base_config: Mapping[str, Any],
) -> None:
    if (
        not args.local_inprocess
        or args.dry_run
        or args.skip_local_codex_gateway_ensure
        or os.environ.get("DRAWAI_SKIP_LOCAL_CODEX_GATEWAY_ENSURE") == "1"
    ):
        return
    svg_config = base_config.get("svg") if isinstance(base_config.get("svg"), dict) else {}
    generation_backend = str(svg_config.get("generation_backend") or "").strip()
    model_runtime = base_config.get("model_runtime") if isinstance(base_config.get("model_runtime"), dict) else {}
    provider = str(model_runtime.get("provider") or "").strip()
    if generation_backend == "codex_python_sdk_controlled" or provider != "local-codex-gateway":
        return
    base_url = str(model_runtime.get("base_url") or "").strip()
    if not _is_loopback_url(base_url):
        return
    runtime_root = _runtime_root_path(args.local_runtime_root, repo_root)
    gateway_dir = runtime_root / "tools" / "local-codex-openai-gateway"
    env = dict(os.environ)
    env.setdefault("DRAWAI_LOCAL_CODEX_BASE_URL", base_url.rstrip("/"))
    if gateway_dir.exists():
        env.setdefault("DRAWAI_LOCAL_CODEX_GATEWAY_DIR", str(gateway_dir))
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "ensure_local_codex_gateway.py"),
            "--wait-seconds",
            "600",
            "--quiet",
        ],
        cwd=repo_root,
        env=env,
        check=True,
    )


def _runtime_root_path(value: str, repo_root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve(strict=False)


def _is_loopback_url(value: str) -> bool:
    hostname = urlparse(str(value or "")).hostname
    return hostname in {"127.0.0.1", "localhost", "::1"}


def _prepare_cases(
    *,
    images: list[Path],
    base_config: dict[str, Any],
    configs_dir: Path,
    outputs_dir: Path,
    logs_dir: Path,
    expected_result: str,
) -> list[CaseSpec]:
    cases: list[CaseSpec] = []
    for index, image in enumerate(images, start=1):
        case_id = f"case_{index:03d}"
        case_slug = _case_slug(image)
        output_dir = outputs_dir / f"{case_id}_{case_slug}"
        output_dir.mkdir(parents=True, exist_ok=True)
        config_path = configs_dir / f"{case_id}.yaml"
        config_payload = json.loads(json.dumps(base_config))
        input_config = config_payload.setdefault("input", {})
        input_config["image"] = str(image)
        input_config["output_dir"] = str(output_dir.resolve(strict=False))
        _write_yaml(config_path, config_payload)
        cases.append(
            CaseSpec(
                case_id=case_id,
                case_slug=case_slug,
                source_image=image,
                source_sha256=_sha256_file(image),
                config_path=config_path,
                output_dir=output_dir,
                stdout_log=logs_dir / f"{case_id}.stdout.log",
                stderr_log=logs_dir / f"{case_id}.stderr.log",
                expected_result=expected_result or "Full DrawAI/SAM3 CLI pipeline completes and outputs are inspected.",
            )
        )
    return cases


def _run_cases(
    cases: list[CaseSpec],
    *,
    workers: int,
    local_inprocess: bool = False,
    local_runtime_root: str = ".local/drawai_runtime",
    sam3_device: str = "cpu",
    rmbg_device: str = "cpu",
    paddle_device: str = "cpu",
    ocr_det_limit_side_len: int = 1280,
    parallel_public_stages: bool = False,
) -> list[dict[str, Any]]:
    if local_inprocess:
        from drawai.local_runtime import build_local_runtime_components

        components = build_local_runtime_components(
            runtime_root=local_runtime_root,
            sam3_device=sam3_device,
            rmbg_device=rmbg_device,
            paddle_device=paddle_device,
            ocr_det_limit_side_len=ocr_det_limit_side_len,
        )
        return [_run_case_local_inprocess(case, components, parallel_public_stages=parallel_public_stages) for case in cases]

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_run_case, case): case for case in cases}
        for future in as_completed(futures):
            rows.append(future.result())
    return sorted(rows, key=lambda row: row["case_id"])


def _run_case_local_inprocess(case: CaseSpec, components: Any, *, parallel_public_stages: bool = False) -> dict[str, Any]:
    from drawai.public_stages import run_public_stage

    started = datetime.now().astimezone()
    start = time.monotonic()
    summary: dict[str, Any]
    exception_text = ""
    status = "failed"
    exitcode = 1
    failed_stage = ""
    try:
        summary = run_public_stage(
            case.config_path,
            "all",
            sam3_transport=components.sam3_transport,
            ocr_provider=components.ocr_provider,
            rmbg_client=components.rmbg_client,
            parallel=parallel_public_stages,
        )
        status = "completed" if summary.get("status") == "ok" else "failed"
        exitcode = 0 if status == "completed" else 1
        failed_stage = _failed_stage_from_reports(case, fallback=str(summary.get("public_stage") or ""))
    except Exception as exc:  # noqa: BLE001 - case-level experiment boundary.
        exception_text = f"{type(exc).__name__}: {exc}"
        summary = {
            "status": "failed",
            "failed_stage": _failed_stage_from_reports(case, fallback="local_inprocess"),
            "exception": exception_text,
        }
        failed_stage = str(summary["failed_stage"])
    ended = datetime.now().astimezone()
    duration = time.monotonic() - start
    row = _finalize_case_status_row(
        case,
        status=status,
        exitcode=exitcode,
        duration_seconds=duration,
        failed_stage=failed_stage if status == "failed" else "",
    )
    _write_json(
        case.output_dir / "case_manifest.json",
        _case_manifest(
            case,
            status=str(row["status"]),
            exitcode=_row_exitcode(row),
            started_at=started,
            ended_at=ended,
            duration_seconds=duration,
            failed_stage=str(row["failed_stage"] or ""),
            stage_sequence=summary.get("stages", []),
            dry_run=False,
            local_inprocess=True,
            parallel_public_stages=parallel_public_stages,
        ),
    )
    case.stdout_log.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    case.stderr_log.write_text(exception_text, encoding="utf-8")
    return row


def _run_case(case: CaseSpec) -> dict[str, Any]:
    started = datetime.now().astimezone()
    command = [sys.executable, "-m", "drawai.cli", "run", "all", "--config", str(case.config_path)]
    start = time.monotonic()
    with case.stdout_log.open("w", encoding="utf-8") as stdout, case.stderr_log.open("w", encoding="utf-8") as stderr:
        proc = subprocess.run(command, stdout=stdout, stderr=stderr, cwd=Path(__file__).resolve().parents[1], check=False)
    ended = datetime.now().astimezone()
    duration = time.monotonic() - start
    status = "completed" if proc.returncode == 0 else "failed"
    summary = _read_json_if_exists(case.output_dir / "reports" / "pipeline_summary.json")
    failed_stage = _failed_stage_from_reports(case) if status == "failed" else ""
    row = _finalize_case_status_row(
        case,
        status=status,
        exitcode=proc.returncode,
        duration_seconds=duration,
        failed_stage=str(failed_stage or ""),
    )
    _write_json(
        case.output_dir / "case_manifest.json",
        _case_manifest(
            case,
            status=str(row["status"]),
            exitcode=_row_exitcode(row),
            started_at=started,
            ended_at=ended,
            duration_seconds=duration,
            failed_stage=str(row["failed_stage"] or ""),
            stage_sequence=summary.get("stages", []),
            dry_run=False,
        ),
    )
    return row


def _run_manifest(
    *,
    run_dir: Path,
    mode: str,
    purpose: str,
    expected_outcome: str,
    created_at: datetime,
    created_by: str,
    base_config_path: Path,
    case_count: int,
    dry_run: bool,
    local_inprocess: bool = False,
    local_runtime_root: str = ".local/drawai_runtime",
    sam3_device: str = "cpu",
    rmbg_device: str = "cpu",
    paddle_device: str = "cpu",
    ocr_det_limit_side_len: int = 1280,
    parallel_public_stages: bool = False,
) -> dict[str, Any]:
    execution_backend = "local_inprocess" if local_inprocess else "service_http"
    command_template = (
        "python scripts/run_drawai_experiment.py --local-inprocess --base-config ... --images ..."
        if local_inprocess
        else "uv run python -m drawai.cli run all --config configs/case_XXX.yaml"
    )
    service_requirements = (
        {
            "sam3": "in-process local SAM3",
            "ocr": "in-process local PaddleOCR",
            "rmbg": "in-process local RMBG-2.0",
        }
        if local_inprocess
        else {
            "sam3": "http://127.0.0.1:18080/v1/segment/proposals",
            "ocr": "http://127.0.0.1:18080/v1/ocr/boxes",
        }
    )
    return {
        "schema": RUN_SCHEMA,
        "run_id": run_dir.name,
        "mode": mode,
        "execution_backend": execution_backend,
        "purpose": purpose,
        "expected_outcome": expected_outcome,
        "created_at": created_at.isoformat(timespec="seconds"),
        "created_by": created_by,
        "git_commit": _git_output(["rev-parse", "HEAD"]),
        "dirty_worktree": bool(_git_output(["status", "--porcelain"])),
        "case_count": case_count,
        "dry_run": dry_run,
        "base_config": str(base_config_path),
        "command_template": command_template,
        "service_requirements": service_requirements,
        "local_runtime": {
            "root": local_runtime_root,
            "sam3_device": sam3_device,
            "rmbg_device": rmbg_device,
            "paddle_device": paddle_device,
            "ocr_det_limit_side_len": ocr_det_limit_side_len,
            "public_stage_parallel": parallel_public_stages,
        } if local_inprocess else {},
        "notes": [],
    }


def _case_manifest(
    case: CaseSpec,
    *,
    status: str,
    dry_run: bool,
    exitcode: int | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    duration_seconds: float | None = None,
    failed_stage: str = "",
    stage_sequence: Any = None,
    local_inprocess: bool = False,
    parallel_public_stages: bool = False,
) -> dict[str, Any]:
    if local_inprocess:
        mode = "parallel" if parallel_public_stages else "sequential"
        command = f"in-process drawai.public_stages.run_public_stage all --{mode} --config {case.config_path}"
    else:
        command = f"uv run python -m drawai.cli run all --config {case.config_path}"
    payload: dict[str, Any] = {
        "schema": CASE_SCHEMA,
        "case_id": case.case_id,
        "case_slug": case.case_slug,
        "execution_backend": "local_inprocess" if local_inprocess else "service_http",
        "source_image_path": str(case.source_image),
        "source_image_sha256": case.source_sha256,
        "config_path": str(case.config_path),
        "output_dir": str(case.output_dir),
        "command": command,
        "status": status,
        "dry_run": dry_run,
        "expected_result": case.expected_result,
        "artifacts": {
            "box_ir_merged": "box_ir/box_ir.merged.json",
            "semantic_svg": "svg/semantic.svg",
            "rendered_png": "svg/rendered.png",
            "pipeline_summary": "reports/pipeline_summary.json",
            "stage_status": "reports/stage_status.json",
            "stage_io_manifest": "reports/stage_io_manifest.json",
            "svg_to_ppt_report": "reports/svg_to_ppt_export_report.json",
            "svg_to_pptx": "svg_to_ppt/semantic.svg_to_ppt.pptx",
        },
        "notes": [],
    }
    if exitcode is not None:
        payload["exitcode"] = exitcode
    if started_at is not None:
        payload["started_at"] = started_at.isoformat(timespec="seconds")
    if ended_at is not None:
        payload["ended_at"] = ended_at.isoformat(timespec="seconds")
    if duration_seconds is not None:
        payload["duration_seconds"] = round(duration_seconds, 3)
    if failed_stage:
        payload["failed_stage"] = failed_stage
    if stage_sequence is not None:
        payload["stage_sequence"] = stage_sequence
    return payload


def _status_row(
    case: CaseSpec,
    *,
    status: str,
    exitcode: int | None,
    duration_seconds: float,
    failed_stage: str = "",
) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "case_slug": case.case_slug,
        "status": status,
        "exitcode": "" if exitcode is None else exitcode,
        "duration_seconds": round(duration_seconds, 3),
        "failed_stage": failed_stage,
        "semantic_svg": str(case.output_dir / "svg" / "semantic.svg"),
        "semantic_rendered_png": str(case.output_dir / "svg" / "rendered.png"),
        "pptx": str(case.output_dir / "svg_to_ppt" / "semantic.svg_to_ppt.pptx"),
        "notes": "",
    }


def _finalize_case_status_row(
    case: CaseSpec,
    *,
    status: str,
    exitcode: int | None,
    duration_seconds: float,
    failed_stage: str = "",
) -> dict[str, Any]:
    row = _status_row(
        case,
        status=status,
        exitcode=exitcode,
        duration_seconds=duration_seconds,
        failed_stage=failed_stage,
    )
    notes: list[str] = []
    pipeline_summary = _read_json_if_exists(case.output_dir / "reports" / "pipeline_summary.json")
    stage_status = _read_json_if_exists(case.output_dir / "reports" / "stage_status.json")

    if status == "completed":
        summary_status = str(pipeline_summary.get("status") or "").strip().lower()
        if pipeline_summary and summary_status != "ok":
            _mark_row_failed(
                row,
                pipeline_summary.get("failed_stage") or stage_status.get("latest_stage") or "pipeline_summary",
            )
            notes.append(f"pipeline_summary status={summary_status or 'missing'}")

        latest_status = str(stage_status.get("latest_status") or "").strip().lower()
        if stage_status and latest_status not in OK_REPORT_STATUSES:
            _mark_row_failed(row, stage_status.get("latest_stage") or "stage_status")
            notes.append(f"stage_status latest_status={latest_status or 'missing'}")

        missing_artifacts = [
            str(relative_path)
            for _name, relative_path in REQUIRED_COMPLETED_ARTIFACTS
            if not _nonempty_file(case.output_dir / relative_path)
        ]
        if missing_artifacts:
            _mark_row_failed(row, "artifact_validation")
            notes.append(f"missing required artifacts: {', '.join(missing_artifacts)}")

        for report_name, relative_path in (
            ("svg_validation_report", Path("reports") / "svg_validation_report.json"),
            ("svg_to_ppt_report", Path("reports") / "svg_to_ppt_export_report.json"),
        ):
            report = _read_json_if_exists(case.output_dir / relative_path)
            report_status = str(report.get("status") or "").strip().lower()
            if report and report_status and report_status not in OK_REPORT_STATUSES:
                _mark_row_failed(row, report_name)
                notes.append(f"{report_name} status={report_status}")

    if row["status"] == "failed" and row["exitcode"] in {"", 0, "0"}:
        row["exitcode"] = 1
    row["notes"] = "; ".join(notes)
    return row


def _mark_row_failed(row: dict[str, Any], failed_stage: Any) -> None:
    if row["status"] != "failed":
        row["status"] = "failed"
    if not row.get("failed_stage"):
        row["failed_stage"] = str(failed_stage or "unknown")
    if row["exitcode"] in {"", 0, "0"}:
        row["exitcode"] = 1


def _failed_stage_from_reports(case: CaseSpec, *, fallback: str = "") -> str:
    summary = _read_json_if_exists(case.output_dir / "reports" / "pipeline_summary.json")
    stage_status = _read_json_if_exists(case.output_dir / "reports" / "stage_status.json")
    return str(summary.get("failed_stage") or stage_status.get("latest_stage") or fallback or "")


def _row_exitcode(row: Mapping[str, Any]) -> int | None:
    value = row.get("exitcode")
    if value == "":
        return None
    return int(value)


def _nonempty_file(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def _write_selected_cases(path: Path, cases: list[CaseSpec]) -> None:
    lines = []
    for case in cases:
        lines.append(
            json.dumps(
                {
                    "schema": SELECTED_CASE_SCHEMA,
                    "case_id": case.case_id,
                    "case_slug": case.case_slug,
                    "source_image_path": str(case.source_image),
                    "source_image_sha256": case.source_sha256,
                    "config_path": str(case.config_path.relative_to(path.parent)),
                    "output_dir": str(case.output_dir.relative_to(path.parent)),
                    "expected_result": case.expected_result,
                    "tags": [],
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_run_status(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id",
        "case_slug",
        "status",
        "exitcode",
        "duration_seconds",
        "failed_stage",
        "semantic_svg",
        "semantic_rendered_png",
        "pptx",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _aggregate_status(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "empty"
    statuses = {str(row["status"]) for row in rows}
    if statuses == {"planned"}:
        return "planned"
    if statuses == {"completed"}:
        return "completed"
    return "failed"


def _case_slug(path: Path) -> str:
    stem = path.stem
    stem = stem.removeprefix("ref_ref_").removeprefix("test_test_")
    parts = safe_run_slug(stem, default="image").split("_")
    short = "_".join(parts[:6])
    return short[:64].strip("_") or "image"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(args: list[str]) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=Path(__file__).resolve().parents[1], check=False, capture_output=True, text=True)
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML config must be a mapping: {path}")
    return payload


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
