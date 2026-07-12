#!/usr/bin/env python3
"""Validate a model-designed, evidence-backed implementation verification suite.

The main model decides which scientific risks and tests apply. This script only proves that every
declared applicable risk has passing executable evidence and that every omission is explicit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PASSING = {"PASS", "PASS_WITH_EXPLAINED_DEVIATION"}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("verification suite root must be an object")
    return value


def validate(data: dict, root: Path) -> list[str]:
    issues: list[str] = []
    selection = data.get("selection_judgment")
    tests = data.get("tests")
    if not isinstance(selection, dict):
        return ["selection_judgment must be an object produced by the main model"]
    if not selection.get("implementation_summary"):
        issues.append("selection_judgment.implementation_summary is required")
    risks = selection.get("risks")
    if not isinstance(risks, list) or not risks:
        issues.append("selection_judgment.risks must be a non-empty, implementation-specific list")
        risks = []
    if not isinstance(tests, list):
        issues.append("tests must be a list")
        tests = []
    by_id: dict[str, dict] = {}
    for index, item in enumerate(tests):
        if not isinstance(item, dict):
            issues.append(f"tests[{index}] must be an object")
            continue
        test_id = item.get("test_id")
        if not test_id:
            issues.append(f"tests[{index}].test_id is required")
            continue
        if test_id in by_id:
            issues.append(f"duplicate test_id: {test_id}")
        by_id[test_id] = item
        for key in ("purpose", "command", "oracle", "observed", "status", "evidence"):
            if key not in item or item[key] in (None, "", []):
                issues.append(f"{test_id}.{key} is required")
        if item.get("status") not in PASSING | {"FAIL", "BLOCKED"}:
            issues.append(f"{test_id}.status is invalid")
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list):
            issues.append(f"{test_id}.evidence must be a list")
        else:
            for artifact in evidence:
                if not (root / artifact).is_file():
                    issues.append(f"{test_id} evidence missing: {artifact}")
    seen_risks: set[str] = set()
    for index, risk in enumerate(risks):
        if not isinstance(risk, dict):
            issues.append(f"risks[{index}] must be an object")
            continue
        risk_id = risk.get("risk_id")
        if not risk_id:
            issues.append(f"risks[{index}].risk_id is required")
            continue
        if risk_id in seen_risks:
            issues.append(f"duplicate risk_id: {risk_id}")
        seen_risks.add(risk_id)
        for key in ("failure_mode", "scientific_consequence", "rationale"):
            if not risk.get(key):
                issues.append(f"{risk_id}.{key} is required")
        applicable = risk.get("applicable")
        if not isinstance(applicable, bool):
            issues.append(f"{risk_id}.applicable must be boolean")
            continue
        covered_by = risk.get("covered_by", [])
        if applicable:
            if not isinstance(covered_by, list) or not covered_by:
                issues.append(f"applicable risk {risk_id} has no selected tests")
                continue
            for test_id in covered_by:
                test = by_id.get(test_id)
                if not test:
                    issues.append(f"risk {risk_id} references unknown test {test_id}")
                elif test.get("status") not in PASSING:
                    issues.append(f"risk {risk_id} is covered by non-passing test {test_id}")
        elif not risk.get("counterfactual_trigger"):
            issues.append(f"non-applicable risk {risk_id} requires counterfactual_trigger")
    if not selection.get("reviewer"):
        issues.append("selection_judgment.reviewer is required")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--root")
    parser.add_argument("--out")
    args = parser.parse_args()
    path = Path(args.file).resolve()
    root = Path(args.root).resolve() if args.root else path.parent.parent.parent
    try:
        issues = validate(load(path), root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issues = [str(exc)]
    report = {"ok": not issues, "verdict": "PASS" if not issues else "FAIL", "issues": issues}
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
