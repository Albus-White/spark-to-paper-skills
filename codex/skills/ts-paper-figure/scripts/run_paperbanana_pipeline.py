#!/usr/bin/env python3
"""Initialize or validate a PaperBanana pipeline from frozen figure routing."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def initialize(workdir: Path, figure_id: str) -> Path:
    research = workdir / "research"
    state = read_object(research / "research_state.json")
    active = state.get("active", {})
    publication_id = active.get("publication_contract_id")
    routing_relative = active.get("figure_routing")
    if not publication_id or not routing_relative:
        raise ValueError("PaperBanana initialization requires frozen publication contract and figure routing")
    contract_path = research / "contracts" / f"{publication_id}.json"
    routing_path = research / routing_relative
    contract = read_object(contract_path)
    routing = read_object(routing_path)
    planned = next((item for item in contract.get("figure_plan", []) if item.get("figure_id") == figure_id), None)
    route = next((item for item in routing.get("figures", []) if item.get("figure_id") == figure_id), None)
    if not planned or not route:
        raise ValueError(f"figure {figure_id} is not present in both publication contract and routing")
    if planned.get("class") != "explanatory_synthesis" or planned.get("route") != "PAPERBANANA_REQUIRED":
        raise ValueError(f"figure {figure_id} is not routed through PaperBanana")
    budget = route.get("candidate_budget") or {}
    planned_candidates = budget.get("planned_candidates")
    if not isinstance(planned_candidates, int) or planned_candidates < 1:
        raise ValueError("frozen route lacks a positive model-selected candidate budget")
    pipeline = workdir / "figures" / f"{figure_id}.pipeline"
    pipeline.mkdir(parents=True, exist_ok=True)
    figure_contract = {
        **route,
        "figure_class": route["class"],
        "publication_contract_id": publication_id,
        "publication_contract_sha256": sha256(contract_path),
        "figure_routing_sha256": sha256(routing_path),
        "frozen_plan": planned,
    }
    (pipeline / "figure_contract.json").write_text(
        json.dumps(figure_contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    search_plan = {
        "strategy": "direct" if planned_candidates == 1 else "candidate_search",
        "planned_candidates": planned_candidates,
        "safety_cap": budget.get("safety_cap", planned_candidates),
        "resource_basis": budget.get("resource_basis"),
        "rationale": budget.get("rationale"),
        "stop_conditions": budget.get("stop_conditions"),
        "reference_strategy": {
            "search_required": True,
            "selection_required": False,
            "rationale": "Every explanatory-synthesis figure inspects accepted-paper visual precedent before planning.",
        },
    }
    if any(search_plan.get(key) in (None, "", []) for key in ("resource_basis", "rationale", "stop_conditions")):
        raise ValueError("candidate budget lacks resource_basis, rationale, or stop_conditions")
    (pipeline / "search_plan.json").write_text(
        json.dumps(search_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for directory in ("references", "paperbanana", "renders", "critique", "repairs", "final", "drawai"):
        (pipeline / directory).mkdir(exist_ok=True)
    return pipeline


def validate(pipeline: Path) -> int:
    validator = Path(__file__).with_name("validate_pipeline.py")
    try:
        return subprocess.run(
            [sys.executable, str(validator), str(pipeline)], timeout=600
        ).returncode
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "error": "PaperBanana validation timed out after 600 seconds"}))
        return 124


def execute(pipeline: Path, paperbanana_root: str | None, python: str | None, timeout_seconds: int, allow_dirty: bool) -> int:
    runner = Path(__file__).with_name("execute_paperbanana.py")
    command = [sys.executable, str(runner), "run", str(pipeline), "--timeout-seconds", str(timeout_seconds)]
    if paperbanana_root:
        command.extend(["--paperbanana-root", paperbanana_root])
    if python:
        command.extend(["--python", python])
    if allow_dirty:
        command.append("--allow-dirty")
    try:
        return subprocess.run(command, timeout=timeout_seconds + 60).returncode
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "error": "PaperBanana execution wrapper timed out"}))
        return 124


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("workdir")
    init.add_argument("figure_id")
    check = sub.add_parser("validate")
    check.add_argument("pipeline")
    run = sub.add_parser("execute")
    run.add_argument("pipeline")
    run.add_argument("--paperbanana-root")
    run.add_argument("--python")
    run.add_argument("--timeout-seconds", type=int, default=7200)
    run.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "init":
            pipeline = initialize(Path(args.workdir).resolve(), args.figure_id)
            print(json.dumps({"ok": True, "pipeline": str(pipeline)}, indent=2))
            return 0
        if args.command == "validate":
            return validate(Path(args.pipeline).resolve())
        return execute(Path(args.pipeline).resolve(), args.paperbanana_root, args.python, args.timeout_seconds, args.allow_dirty)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
