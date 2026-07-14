#!/usr/bin/env python3
"""Build the exact release-audit payload from current frozen artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from publication_audit import audit as publication_audit
from run_gates import CITATIONS_LINT, LIFECYCLE, SVG_TOOLS, check_figure_critique


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_json(script: Path, args: list[str]) -> tuple[bool, dict, str]:
    result = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, timeout=600)
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError):
        payload = {}
    return result.returncode == 0, payload, (result.stderr or result.stdout).strip()


def build(workdir: Path) -> tuple[dict, list[str]]:
    workdir = workdir.resolve()
    research = workdir / "research"
    blockers: list[str] = []
    state = json.loads((research / "research_state.json").read_text(encoding="utf-8"))
    active = state.get("active", {})
    publication_id = active.get("publication_contract_id")
    manuscript_id = active.get("manuscript_id")
    judgment_id = active.get("publication_judgment_id")
    contract_path = research / "contracts" / f"{publication_id}.json"
    manuscript_path = research / "manuscript" / f"{manuscript_id}.json"
    judgment_path = research / "reports/manuscript" / f"{judgment_id}.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8")) if contract_path.is_file() else {}

    lifecycle_ok, lifecycle_report, lifecycle_error = run_json(LIFECYCLE, ["--root", str(research), "validate"])
    if not lifecycle_ok:
        blockers.append(f"lifecycle validation failed: {lifecycle_error or lifecycle_report}")
    citation_ok, citation_report, citation_error = run_json(CITATIONS_LINT, [str(workdir)])
    if not citation_ok:
        blockers.append(f"citation gate failed: {citation_error or citation_report.get('issues')}")
    publication_report = publication_audit(workdir)
    figure_problems = check_figure_critique(workdir)
    if not publication_report["ok"]:
        blockers.extend(f"publication figure audit: {item}" for item in publication_report["issues"])
    blockers.extend(f"figure pipeline: {item}" for item in figure_problems)
    vector = subprocess.run([sys.executable, str(SVG_TOOLS), "check", "--workdir", str(workdir)], capture_output=True, text=True, timeout=600)
    if vector.returncode != 0:
        blockers.append(f"publication graphic gate failed: {(vector.stderr or vector.stdout).strip()}")

    claims = json.loads((research / "claims/claim-registry.json").read_text(encoding="utf-8")).get("claims", [])
    unresolved = [item.get("claim_id") for item in claims if item.get("active") and item.get("support_status") in {"UNVERIFIED", "NEEDS_AUTHOR_CONFIRMATION"}]
    if unresolved:
        blockers.append(f"unresolved active claims: {unresolved}")
    latex_path = research / "reports/manuscript/latex-verdict.json"
    latex: dict = {}
    try:
        latex = json.loads(latex_path.read_text(encoding="utf-8"))
        pdf = research / latex["pdf"]
        latex_ok = latex.get("compiled") is True and latex.get("error_count") == 0 and pdf.is_file() and sha256(pdf) == latex.get("pdf_sha256")
    except (OSError, ValueError, KeyError, TypeError):
        latex_ok = False
    if not latex_ok:
        blockers.append("registered LaTeX verdict or compiled PDF is missing, failed, or stale")
    try:
        judgment = json.loads(judgment_path.read_text(encoding="utf-8"))
        page_scale = judgment.get("page_scale") or {}
        target_range = contract.get("targets", {}).get("page_range")
        rendered_review = judgment.get("rendered_pdf_review") or {}
        judgment_ok = (
            judgment.get("verdict") in {"PASS", "PASS_WITH_EXPLAINED_DEVIATION"}
            and judgment.get("publication_contract_id") == publication_id
            and judgment.get("publication_contract_hash") == sha256(contract_path)
            and judgment.get("manuscript_id") == manuscript_id
            and judgment.get("manuscript_hash") == sha256(manuscript_path)
            and page_scale.get("actual_pages") == latex.get("page_count")
            and page_scale.get("target_range") == target_range
            and rendered_review.get("pdf_sha256") == latex.get("pdf_sha256")
            and rendered_review.get("actual_pdf_reviewed") is True
            and rendered_review.get("blocking_issues") == []
        )
    except (OSError, ValueError, TypeError):
        judgment_ok = False
    if not judgment_ok:
        blockers.append("active publication judgment is missing, failed, or stale")

    payload = {
        "publication_contract_id": publication_id,
        "publication_contract_hash": sha256(contract_path) if contract_path.is_file() else "",
        "manuscript_id": manuscript_id,
        "manuscript_hash": sha256(manuscript_path) if manuscript_path.is_file() else "",
        "publication_judgment_id": judgment_id,
        "publication_judgment_hash": sha256(judgment_path) if judgment_path.is_file() else "",
        "citation_verdict": "PASS" if citation_ok else "FAIL",
        "figure_verdict": "PASS" if publication_report["ok"] and not figure_problems and vector.returncode == 0 else "FAIL",
        "latex_verdict": "PASS" if latex_ok else "FAIL",
        "claim_verdict": "PASS" if not unresolved else "FAIL",
        "blocking_issues": blockers,
        "reviewer": {"id": "build_release_audit.py", "type": "deterministic"},
        "details": {
            "lifecycle_ok": lifecycle_ok,
            "actual_unique_citations": citation_report.get("n_cited"),
            "required_unique_citations": citation_report.get("required_unique_cited_references"),
            "publication_figure_audit": publication_report,
            "publication_judgment_ok": judgment_ok,
            "page_scale": (judgment.get("page_scale") if judgment_ok else {}),
        },
    }
    return payload, blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workdir")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        payload, blockers = build(Path(args.workdir))
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
