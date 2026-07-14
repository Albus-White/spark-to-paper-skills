#!/usr/bin/env python3
"""Reject exact internal-provenance leakage from reader-facing manuscript sources."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


HASH = re.compile(r"(?i)(?:sha[- ]?256|checksum|artifact hash)[^\n]{0,80}\b[0-9a-f]{64}\b")
INTERNAL_PATH = re.compile(
    r"(?i)(?:^|[\s`{(])(?:research/(?:reports|contracts|experiments|decisions|logs|manuscript)|"
    r"reports/(?:gates|release|schedule)|release-audit(?:\.json)?|research_state\.json)(?=$|[\s`})/.,;:])"
)
INTERNAL_ID = re.compile(r"(?i)\b(?:gate\s+G(?:1[0-6]|[0-9])|gate\s+M[1-6]|gate\s+V1)\b")
COMMAND_HINT = re.compile(r"(?m)^\s*(?:\$\s*)?(?:python3?|bash|sh|git|pip|uv|docker)\s+[^\n]+$")


def load_contract(workdir: Path) -> dict:
    state = json.loads((workdir / "research/research_state.json").read_text(encoding="utf-8"))
    contract_id = state["active"]["publication_contract_id"]
    return json.loads((workdir / f"research/contracts/{contract_id}.json").read_text(encoding="utf-8"))


def scan(workdir: Path) -> dict:
    issues = []
    warnings = []
    try:
        contract = load_contract(workdir)
        policy = contract["manuscript_content_policy"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "issues": [{"rule": "missing_manuscript_content_policy", "detail": str(exc)}], "warnings": []}
    allowed = {str(value) for value in policy.get("allowed_internal_identifiers", [])}
    paths = ([workdir / "main.tex"] if (workdir / "main.tex").is_file() else [])
    if (workdir / "sections").is_dir():
        paths.extend(sorted((workdir / "sections").rglob("*.tex")))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(workdir).as_posix()
        for rule, pattern in (("raw_internal_hash", HASH), ("internal_artifact_path", INTERNAL_PATH), ("internal_gate_identifier", INTERNAL_ID)):
            for match in pattern.finditer(text):
                snippet = match.group(0).strip()
                if snippet not in allowed:
                    issues.append({"file": relative, "rule": rule, "snippet": snippet[:180]})
        for match in COMMAND_HINT.finditer(text):
            warnings.append({"file": relative, "rule": "reader_relevance_review_required", "snippet": match.group(0).strip()[:180]})
    return {"ok": not issues, "issues": issues, "warnings": warnings}


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: manuscript_boundary_lint.py <workdir>"}))
        return 2
    report = scan(Path(sys.argv[1]).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
