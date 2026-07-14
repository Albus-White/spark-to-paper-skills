#!/usr/bin/env python3
"""Orchestrator-level gate runner — the single place that CONSUMES linter exit codes.

    python run_gates.py <workdir> <stage|all>

It runs the gates for the requested stage (or the full Definition-of-Done set for
`all`) via subprocess, prints each gate's output, and EXITS NONZERO ON THE FIRST
gate that exits nonzero. It changes NO gate logic — it only consumes the existing,
stable exit codes (0 ok / 1 issues / 2 usage) and JSON the linters already emit.

Sibling linter paths resolve relative to THIS file's location (not the cwd), exactly
like ts-paper-cite/scripts/citations_lint.py resolves TEMPLATES_ROOT — so the runner
is workdir-independent (the agent thread resets cwd between calls).

A missing required artifact for the requested stage is a nonzero failure.
stdlib-only (json, sys, subprocess, pathlib).
"""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS_ROOT = HERE.parent.parent  # .../skills (the suite root holding ts-paper-*)

# Gate scripts, resolved relative to the skills root (workdir-independent).
TEMPLATE_LINT  = SKILLS_ROOT / "ts-paper-plan" / "scripts" / "template_lint.py"
BLUEPRINT_LINT = SKILLS_ROOT / "ts-paper-plan" / "scripts" / "blueprint_lint.py"
CONTRACT_LINT  = SKILLS_ROOT / "ts-paper-plan" / "scripts" / "research_contract_lint.py"
CITATIONS_LINT = SKILLS_ROOT / "ts-paper-cite" / "scripts" / "citations_lint.py"
BIB_INTEGRITY  = SKILLS_ROOT / "ts-paper-cite" / "scripts" / "bib_integrity_lint.py"
BENCHMARK_LINT = SKILLS_ROOT / "ts-paper-cite" / "scripts" / "benchmark_lint.py"
GROUNDING_LINT = SKILLS_ROOT / "ts-paper-cite" / "scripts" / "design_grounding_lint.py"
DRAFT_LINT     = SKILLS_ROOT / "ts-paper-write" / "scripts" / "draft_lint.py"
MANUSCRIPT_BOUNDARY = SKILLS_ROOT / "ts-paper-write" / "scripts" / "manuscript_boundary_lint.py"
RESULT_BINDING = SKILLS_ROOT / "ts-paper-data" / "scripts" / "validate_results_binding.py"
ASSEMBLE       = SKILLS_ROOT / "ts-paper-latex" / "scripts" / "assemble_paper.py"
SVG_TOOLS      = SKILLS_ROOT / "ts-figure-optimize" / "scripts" / "check_vector_pdf.py"
FIGURE_PIPELINE = SKILLS_ROOT / "ts-paper-figure" / "scripts" / "validate_pipeline.py"
PUBLICATION_AUDIT = HERE / "publication_audit.py"
LIFECYCLE      = SKILLS_ROOT / "ts-research-lifecycle" / "scripts" / "lifecycle.py"

# stage -> ordered list of (gate_script, [required_workdir_inputs])
# Each required input is a workdir-relative path; if ALL listed inputs for a gate
# are absent the gate is skipped, else the gate runs (the linter reports its own
# fine-grained missing-input issues and exit code).
STAGE_GATES = {
    "plan":   [(TEMPLATE_LINT, ["template.json"]),
               (BLUEPRINT_LINT, ["blueprint.json"])],
    "cite":   [(BIB_INTEGRITY, ["refs.bib"]),
               (BENCHMARK_LINT, ["benchmark_candidates.json"])],
    "contract": [(CONTRACT_LINT, ["research_contract.json", "claim_registry.json"]),
                 (BENCHMARK_LINT, ["benchmark_candidates.json"]),
                 (GROUNDING_LINT, ["design_evidence_matrix.json"])],
    "write":  [(DRAFT_LINT, ["sections"]),
               (MANUSCRIPT_BOUNDARY, ["sections"])],
    "refine": [(DRAFT_LINT, ["sections"]),
               (CITATIONS_LINT, ["refs.bib"]),
               (MANUSCRIPT_BOUNDARY, ["sections"])],
    "data":   [(RESULT_BINDING, ["research/evidence/results/results-manifest.jsonl", "results_bindings.json"]),
               (DRAFT_LINT, ["sections"])],
}


def _missing_inputs(wd: Path, rels) -> list[str]:
    return [item for item in rels if not (wd / item).exists()]


def _run(script: Path, args) -> int:
    """Run a gate via subprocess, stream its output, return its exit code."""
    if not script.exists():
        print(f"[run_gates] FAIL: gate script not found: {script}")
        return 1
    print(f"\n===== gate: {script.name} {' '.join(args)} =====")
    try:
        r = subprocess.run([sys.executable, str(script), *args],
                           capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print(f"[run_gates] FAIL: {script.name} timed out after 600s")
        return 124
    if r.stdout:
        print(r.stdout, end="" if r.stdout.endswith("\n") else "\n")
    if r.stderr:
        print(r.stderr, end="" if r.stderr.endswith("\n") else "\n")
    print(f"[run_gates] {script.name} exit={r.returncode}")
    return r.returncode


def run_stage(stage: str, wd: Path) -> int:
    """Run all gates for one stage; return nonzero on the FIRST failing gate."""
    for script, required in STAGE_GATES[stage]:
        missing = _missing_inputs(wd, required)
        if missing:
            print(f"\n===== gate: {script.name} =====")
            print(f"[run_gates] FAIL: required input {missing} absent in {wd}")
            return 1
        rc = _run(script, [str(wd)])
        if rc != 0:
            return rc
    return 0


def assert_latex(wd: Path) -> int:
    """DoD latex verdict: parse the most recent assemble JSON if present, else
    re-run assemble_paper.py; require compiled==true && error_count==0."""
    def input_hash() -> str:
        files = []
        for name in ("template.json", "blueprint.json", "refs.bib"):
            path = wd / name
            if path.is_file(): files.append(path)
        for directory in ("sections", "figures"):
            root = wd / directory
            if root.is_dir(): files.extend(path for path in root.rglob("*") if path.is_file() and ".pipeline" not in path.parts)
        payload = [path.relative_to(wd).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest() for path in sorted(files)]
        return hashlib.sha256(b"".join(payload)).hexdigest()

    current_input_hash = input_hash()
    # A cached verdict is valid only for the exact current assembly inputs.
    verdict = None
    for name in ("assemble.json", "latex_verdict.json"):
        p = wd / name
        if p.exists():
            try:
                candidate = json.loads(p.read_text())
                if candidate.get("input_hash") != current_input_hash:
                    print(f"[run_gates] ignoring stale {name}: input hash changed")
                    continue
                verdict = candidate
                print(f"\n===== latex verdict (cached {name}) =====")
                print(json.dumps(verdict, indent=2))
                break
            except (ValueError, OSError):
                verdict = None  # fall through to a fresh run
    if verdict is None:
        if not ASSEMBLE.exists():
            print(f"[run_gates] FAIL: assemble script not found: {ASSEMBLE}")
            return 1
        print(f"\n===== latex verdict: assemble_paper.py {wd} =====")
        try:
            r = subprocess.run([sys.executable, str(ASSEMBLE), str(wd)],
                               capture_output=True, text=True, timeout=1200)
        except subprocess.TimeoutExpired:
            print("[run_gates] FAIL: assemble_paper.py timed out after 1200s")
            return 124
        if r.stderr:
            print(r.stderr.rstrip("\n"))
        out = (r.stdout or "").strip()
        print(out)
        # assemble_paper.py prints a single JSON object on stdout.
        try:
            verdict = json.loads(out.splitlines()[-1]) if out else {}
        except (ValueError, IndexError):
            print("[run_gates] FAIL: could not parse assemble_paper.py JSON")
            return 1
    compiled = bool(verdict.get("compiled"))
    error_count = int(verdict.get("error_count", 1))
    ok = compiled and error_count == 0
    print(f"[run_gates] latex compiled={compiled} error_count={error_count} "
          f"-> {'ok' if ok else 'FAIL'}")
    return 0 if ok else 1


def _resolve_artifact(workdir: Path, value) -> Path:
    if isinstance(value, dict):
        value = value.get("path")
    path = Path(str(value or ""))
    return path if path.is_absolute() else workdir / path


def check_figure_critique(workdir) -> list:
    """Validate each frozen figure route without pretending all figures share one renderer."""
    workdir = Path(workdir)
    figs = workdir / "figures"
    man = figs / "figures.manifest.json"
    problems: list = []
    if not man.is_file():
        state_path = workdir / "research/research_state.json"
        if not state_path.is_file():
            return problems
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            contract_id = state.get("active", {}).get("publication_contract_id")
            contract = json.loads((workdir / f"research/contracts/{contract_id}.json").read_text(encoding="utf-8"))
            required_total = int(contract.get("targets", {}).get("figure_count", -1))
        except (OSError, ValueError, TypeError):
            return ["cannot determine frozen figure target while figures.manifest.json is missing"]
        if required_total > 0:
            return [f"figures.manifest.json is missing but the publication contract requires {required_total} figures"]
        if required_total < 0:
            return ["publication contract lacks an explicit total figure target"]
        return problems
    try:
        data = json.loads(man.read_text())
    except (ValueError, OSError) as e:
        return [f"figures.manifest.json unreadable: {e}"]
    items = data if isinstance(data, list) else data.get("figures", [])
    fact_manifest = workdir / "research/evidence/results/results-manifest.jsonl"
    known_fact_ids: set[str] = set()
    if fact_manifest.is_file():
        try:
            known_fact_ids = {
                json.loads(line)["fact_id"] for line in fact_manifest.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
        except (ValueError, KeyError, TypeError) as exc:
            problems.append(f"canonical result manifest is unreadable while validating figures: {exc}")
    expected_routes = {
        "measured_evidence": "DETERMINISTIC_OR_ORIGINAL_EVIDENCE",
        "original_observation": "ORIGINAL_EVIDENCE",
        "exact_structure": "DOMAIN_NATIVE",
        "explanatory_synthesis": "PAPERBANANA_REQUIRED",
    }
    for f in items:
        if not isinstance(f, dict):
            problems.append("figures.manifest.json contains a non-object entry")
            continue
        label = f.get("figure_id") or f.get("label", "?")
        for key in ("class", "route", "source_of_truth", "renderer"):
            if not f.get(key):
                problems.append(f"figure '{label}': missing {key}")
        if expected_routes.get(f.get("class")) != f.get("route"):
            problems.append(f"figure '{label}': class/route violates source-of-truth routing")
            continue
        published_raster = _resolve_artifact(workdir, f.get("published_raster")) if f.get("published_raster") else None
        vector = _resolve_artifact(workdir, f.get("published_vector")) if f.get("published_vector") else None
        if published_raster is None and vector is None:
            problems.append(f"figure '{label}': no published artifact")
        if published_raster is not None and not published_raster.is_file():
            problems.append(f"figure '{label}': published_raster missing")
        if vector is not None and not vector.is_file():
            problems.append(f"figure '{label}': published_vector missing")
        if f.get("class") == "measured_evidence":
            fact_ids = f.get("fact_ids")
            if not fact_ids:
                problems.append(f"figure '{label}': measured evidence figure missing fact_ids")
            elif not known_fact_ids:
                problems.append(f"figure '{label}': measured evidence figure has no canonical result manifest")
            else:
                unknown = sorted(set(fact_ids) - known_fact_ids)
                if unknown:
                    problems.append(f"figure '{label}': unknown canonical fact_ids {unknown}")
        if f.get("class") == "explanatory_synthesis":
            pipeline = _resolve_artifact(workdir, f.get("pipeline_dir"))
            if not f.get("pipeline_dir") or not pipeline.is_dir():
                problems.append(f"figure '{label}': PaperBanana pipeline_dir missing/unresolvable")
                continue
            try:
                checked = subprocess.run(
                    [sys.executable, str(FIGURE_PIPELINE), str(pipeline)],
                    capture_output=True, text=True, timeout=300,
                )
            except subprocess.TimeoutExpired:
                problems.append(f"figure '{label}': PaperBanana validation timed out")
                continue
            try:
                report = json.loads(checked.stdout)
            except (ValueError, TypeError):
                report = {}
            if checked.returncode != 0 or not report.get("ok"):
                detail = report.get("errors") or checked.stderr.strip() or "pipeline validation failed"
                problems.append(f"figure '{label}': invalid PaperBanana pipeline: {detail}")
                continue
            final_image = Path(str(report.get("final_image") or ""))
            if published_raster is not None and published_raster.is_file() and final_image.is_file() and hashlib.sha256(published_raster.read_bytes()).digest() != hashlib.sha256(final_image.read_bytes()).digest():
                problems.append(f"figure '{label}': published raster differs from reviewed PaperBanana image")
            if report.get("drawai_status") == "AVAILABLE_REQUIRED":
                drawai_pdf = Path(str((report.get("drawai_outputs") or {}).get("pdf") or ""))
                if vector is None:
                    problems.append(f"figure '{label}': available DrawAI route requires published_vector")
                elif drawai_pdf.is_file() and vector.is_file() and hashlib.sha256(drawai_pdf.read_bytes()).digest() != hashlib.sha256(vector.read_bytes()).digest():
                    problems.append(f"figure '{label}': published vector differs from reviewed DrawAI PDF")
        else:
            review_path = _resolve_artifact(workdir, f.get("visual_review"))
            if not f.get("visual_review") or not review_path.is_file():
                problems.append(f"figure '{label}': non-PaperBanana route requires visual_review")
                continue
            try:
                review = json.loads(review_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                problems.append(f"figure '{label}': visual_review is unreadable")
                continue
            reviewed = published_raster if published_raster is not None and published_raster.is_file() else vector
            if reviewed is None or not reviewed.is_file() or review.get("artifact_sha256") != hashlib.sha256(reviewed.read_bytes()).hexdigest():
                problems.append(f"figure '{label}': visual_review is stale or not bound to the published artifact")
            reviewer = review.get("reviewer") or {}
            if reviewer.get("actual_image_review") is not True or review.get("blocking_issues"):
                problems.append(f"figure '{label}': visual review did not inspect and approve the actual artifact")
    return problems


def run_all(wd: Path) -> int:
    """Run final exact gates for citations, manuscript, route-authorized figures, and LaTeX."""
    lifecycle_root = wd / "research"
    if not (lifecycle_root / "research_state.json").exists():
        print("[run_gates] FAIL: final paper requires the single lifecycle at <workdir>/research")
        return 1
    if not LIFECYCLE.exists():
        print(f"[run_gates] FAIL: lifecycle validator missing: {LIFECYCLE}")
        return 1
    rc = _run(LIFECYCLE, ["--root", str(lifecycle_root), "validate"])
    if rc != 0:
        return rc
    state = json.loads((lifecycle_root / "research_state.json").read_text())
    if state.get("phase") not in ("LATEX_COMPILED", "RELEASE_AUDITED", "RELEASED"):
        print(f"[run_gates] FAIL: lifecycle phase is {state.get('phase')!r}; "
              "final paper requires LATEX_COMPILED, RELEASE_AUDITED, or RELEASED")
        return 1
    # citations + draft are REQUIRED at the finish line; a missing artifact here
    # is a failure, not a skip.
    for script, required, label in (
        (CITATIONS_LINT, "refs.bib", "citations"),
        (DRAFT_LINT, "sections", "draft"),
        (MANUSCRIPT_BOUNDARY, "sections", "manuscript boundary"),
    ):
        if not (wd / required).exists():
            print(f"\n===== gate: {script.name} =====")
            print(f"[run_gates] FAIL: required {label} artifact "
                  f"'{required}' absent in {wd} (DoD)")
            return 1
        rc = _run(script, [str(wd)])
        if rc != 0:
            return rc
    if (wd / "research/evidence/results/results-manifest.jsonl").is_file():
        if not (wd / "results_bindings.json").is_file():
            print("[run_gates] FAIL: empirical manuscript requires results_bindings.json")
            return 1
        rc = _run(RESULT_BINDING, [str(wd)])
        if rc != 0:
            return rc
    # Figure gate: validate whichever publication raster/vector artifacts the manifest declares.
    if not SVG_TOOLS.exists():
        print(f"\n===== gate: check_vector_pdf.py =====")
        print(f"[run_gates] FAIL: vector check script not found: {SVG_TOOLS}")
        return 1
    rc = _run(SVG_TOOLS, ["check", "--workdir", str(wd)])
    if rc != 0:
        return rc
    # Figure generation gate: validate the model-selected bounded render plan and actual-image review.
    print(f"\n===== gate: adaptive figure evidence =====")
    crit_problems = check_figure_critique(wd)
    if crit_problems:
        for p in crit_problems:
            print(f"[run_gates] FAIL: {p}")
        return 1
    print("[run_gates] ok (figure provenance + actual-image review + published identity)")
    rc = _run(PUBLICATION_AUDIT, [str(wd)])
    if rc != 0:
        return rc
    return assert_latex(wd)


def main() -> None:
    if len(sys.argv) != 3:
        print(json.dumps({"ok": False,
                          "error": "usage: run_gates.py <workdir> <stage|all>",
                          "stages": sorted(STAGE_GATES) + ["all"]}))
        sys.exit(2)
    wd = Path(sys.argv[1]).resolve()
    stage = sys.argv[2]
    if not wd.is_dir():
        print(json.dumps({"ok": False, "error": f"workdir not a directory: {wd}"}))
        sys.exit(2)
    if stage == "all":
        rc = run_all(wd)
    elif stage in STAGE_GATES:
        rc = run_stage(stage, wd)
    else:
        print(json.dumps({"ok": False,
                          "error": f"unknown stage: {stage}",
                          "stages": sorted(STAGE_GATES) + ["all"]}))
        sys.exit(2)
    print(f"\n[run_gates] {'ALL GATES PASSED' if rc == 0 else 'GATE FAILED'} "
          f"(stage={stage}) exit={rc}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
