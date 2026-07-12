#!/usr/bin/env python3
"""Validate manuscript result bindings against the lifecycle's canonical fact manifest."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained_file(root: Path, value: str) -> Path | None:
    try:
        path = (root / value).resolve()
        path.relative_to(root)
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


def load_lifecycle(workdir: Path):
    script = Path(__file__).resolve().parents[2] / "ts-research-lifecycle" / "scripts" / "lifecycle.py"
    spec = importlib.util.spec_from_file_location("research_lifecycle", script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def load_facts(path: Path) -> dict[str, dict]:
    facts = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            fact = json.loads(raw); facts[fact["fact_id"]] = fact
    return facts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workdir")
    args = parser.parse_args()
    workdir = Path(args.workdir).resolve()
    research = workdir / "research"
    manifest = research / "evidence/results/results-manifest.jsonl"
    bindings_path = workdir / "results_bindings.json"
    issues: list[str] = []
    if not (research / "research_state.json").is_file():
        issues.append("data-aware output requires a lifecycle under <workdir>/research")
    elif not manifest.is_file():
        issues.append("canonical lifecycle results manifest is missing")
    else:
        lifecycle = load_lifecycle(workdir)
        try:
            lifecycle.validate_results_manifest(research)
        except ValueError as exc:
            issues.append(str(exc))
    if not bindings_path.is_file():
        issues.append("results_bindings.json is missing")
        bindings = {}
    else:
        try:
            bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            issues.append(f"results_bindings.json is invalid: {exc}"); bindings = {}
    facts = load_facts(manifest) if manifest.is_file() else {}
    if manifest.is_file() and bindings.get("research_manifest_sha256") != sha256(manifest):
        issues.append("results_bindings.json is not bound to the current research manifest")
    items = bindings.get("bindings")
    if not isinstance(items, list) or not items:
        issues.append("results_bindings.bindings must be a non-empty list")
        items = []
    for index, binding in enumerate(items):
        if not isinstance(binding, dict):
            issues.append(f"binding {index} must be an object"); continue
        fact_id = binding.get("fact_id"); artifact = binding.get("artifact"); line = binding.get("line")
        rendered = str(binding.get("rendered_value", ""))
        if fact_id not in facts:
            issues.append(f"binding {index} references unknown fact {fact_id}"); continue
        path = contained_file(workdir, str(artifact or ""))
        if path is None:
            issues.append(f"binding {index} artifact missing: {artifact}"); continue
        if binding.get("artifact_sha256") != sha256(path):
            issues.append(f"binding {index} artifact hash mismatch: {artifact}")
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if not isinstance(line, int) or line < 1 or line > len(lines) or rendered not in lines[line - 1]:
            issues.append(f"binding {index} rendered value is not present at {artifact}:{line}")
        allowed = {str(facts[fact_id].get("value")), str(facts[fact_id].get("display_value", ""))}
        if rendered not in allowed:
            issues.append(f"binding {index} rendered value does not match canonical fact {fact_id}")
    report = {"ok": not issues, "facts": len(facts), "bindings": len(items), "issues": issues}
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
