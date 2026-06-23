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

A gate whose REQUIRED input file is genuinely absent is skipped with a printed
"skipped: <reason>"; but a missing REQUIRED artifact for the requested stage is
itself a nonzero failure. stdlib-only (json, sys, subprocess, pathlib).
"""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS_ROOT = HERE.parent.parent  # .../skills (the suite root holding ts-paper-*)

# Gate scripts, resolved relative to the skills root (workdir-independent).
TEMPLATE_LINT  = SKILLS_ROOT / "ts-paper-plan" / "scripts" / "template_lint.py"
BLUEPRINT_LINT = SKILLS_ROOT / "ts-paper-plan" / "scripts" / "blueprint_lint.py"
CITATIONS_LINT = SKILLS_ROOT / "ts-paper-cite" / "scripts" / "citations_lint.py"
DRAFT_LINT     = SKILLS_ROOT / "ts-paper-write" / "scripts" / "draft_lint.py"
ASSEMBLE       = SKILLS_ROOT / "ts-paper-latex" / "scripts" / "assemble_paper.py"
SVG_TOOLS      = SKILLS_ROOT / "ts-figure-optimize" / "scripts" / "check_vector_pdf.py"  # sole figure gate (DrawAI hybrid is the only vectorizer; ts-paper-vector removed)

# stage -> ordered list of (gate_script, [required_workdir_inputs])
# Each required input is a workdir-relative path; if ALL listed inputs for a gate
# are absent the gate is skipped, else the gate runs (the linter reports its own
# fine-grained missing-input issues and exit code).
STAGE_GATES = {
    "plan":   [(TEMPLATE_LINT, ["template.json"]),
               (BLUEPRINT_LINT, ["blueprint.json"])],
    "cite":   [(CITATIONS_LINT, ["refs.bib"])],
    "write":  [(DRAFT_LINT, ["sections"])],
    "refine": [(DRAFT_LINT, ["sections"]),
               (CITATIONS_LINT, ["refs.bib"])],
    "data":   [(DRAFT_LINT, ["sections"])],
}


def _has_input(wd: Path, rels) -> bool:
    """True if at least one of the required workdir inputs exists."""
    return any((wd / r).exists() for r in rels)


def _run(script: Path, args) -> int:
    """Run a gate via subprocess, stream its output, return its exit code."""
    if not script.exists():
        print(f"[run_gates] FAIL: gate script not found: {script}")
        return 1
    print(f"\n===== gate: {script.name} {' '.join(args)} =====")
    r = subprocess.run([sys.executable, str(script), *args],
                       capture_output=True, text=True)
    if r.stdout:
        print(r.stdout, end="" if r.stdout.endswith("\n") else "\n")
    if r.stderr:
        print(r.stderr, end="" if r.stderr.endswith("\n") else "\n")
    print(f"[run_gates] {script.name} exit={r.returncode}")
    return r.returncode


def run_stage(stage: str, wd: Path) -> int:
    """Run all gates for one stage; return nonzero on the FIRST failing gate."""
    for script, required in STAGE_GATES[stage]:
        if not _has_input(wd, required):
            print(f"\n===== gate: {script.name} =====")
            print(f"[run_gates] skipped: required input "
                  f"{required} absent in {wd}")
            continue
        rc = _run(script, [str(wd)])
        if rc != 0:
            return rc
    return 0


def assert_latex(wd: Path) -> int:
    """DoD latex verdict: parse the most recent assemble JSON if present, else
    re-run assemble_paper.py; require compiled==true && error_count==0."""
    # A workdir may cache the assemble verdict as JSON; prefer it if present.
    verdict = None
    for name in ("assemble.json", "latex_verdict.json"):
        p = wd / name
        if p.exists():
            try:
                verdict = json.loads(p.read_text())
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
        r = subprocess.run([sys.executable, str(ASSEMBLE), str(wd)],
                           capture_output=True, text=True)
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


# Free-form schematic types MUST be GENERATED by the image model (rich + grounded + critiqued),
# never hand-authored as a flat SVG. Only matplotlib (data/concept plots) may be code-drawn.
_SCHEMATIC_TYPES = {"architecture", "pipeline", "framework", "schematic", "overview",
                    "diagram", "flow", "qualitative"}
_ALLOWED_ENGINES = {"image-model", "matplotlib"}


def check_figure_critique(workdir) -> list:
    """Guard the figure stage against the 'hand-authored flat SVG' regression and enforce grounded
    critique. Returns a list of problem strings (empty == ok). No figures.manifest.json yet => no
    problems (the figure stage hasn't run). Rules:
      1. engine must be in {image-model, matplotlib} — a free-form figure drawn as a flat 'svg-native'
         SVG (skipping the image-model GROUND + critique flow) is the regression this blocks;
      2. a free-form SCHEMATIC type must be engine 'image-model' (only matplotlib data/concept plots
         may be code-drawn);
      3. every image-model figure carries a non-empty critique trace + critic_rounds>=2 + grounding fields."""
    figs = Path(workdir) / "figures"
    man = figs / "figures.manifest.json"
    problems: list = []
    if not man.is_file():
        return problems  # no figures stage yet -> nothing to enforce
    try:
        data = json.loads(man.read_text())
    except (ValueError, OSError) as e:
        return [f"figures.manifest.json unreadable: {e}"]
    for f in data.get("figures", []):
        if not isinstance(f, dict):
            continue
        label = f.get("label", "?")
        ftype = str(f.get("type", "")).lower()
        engine = f.get("engine", "")
        # (1) no escape-hatch engines: a free-form figure hand-authored as flat SVG bypasses the
        #     whole rich-generation flow (the carbon-paper regression). Forbid it.
        if engine not in _ALLOWED_ENGINES:
            problems.append(f"figure '{label}': engine '{engine}' not allowed — a free-form figure must be "
                            f"image-model (rendered + GROUNDED on a top-journal MAIN figure + critiqued); only "
                            f"matplotlib may be code-drawn. Hand-authored flat SVG is the regression this blocks.")
            continue
        # (2) a free-form SCHEMATIC must be image-model, not a code-drawn flat diagram
        if ftype in _SCHEMATIC_TYPES and engine != "image-model":
            problems.append(f"figure '{label}': type '{ftype}' is a free-form schematic but engine='{engine}' "
                            f"— it must be image-model (rendered + grounded), not code-drawn/flat")
            continue
        # (3) matplotlib (data/concept plot): exempt from the image-model critique/grounding gate
        if engine != "image-model":
            continue
        # (4) image-model figure: enforce critique trace + grounding
        log = figs / "repair_logs" / f"{label}.log"
        if not (log.is_file() and log.stat().st_size > 0):
            problems.append(f"figure '{label}': empty/missing repair_logs/{label}.log "
                            f"(enforced critique loop did not run)")
        try:
            rounds = int(f.get("critic_rounds", 0) or 0)
        except (TypeError, ValueError):
            rounds = 0
        if rounds < 2:
            problems.append(f"figure '{label}': critic_rounds < 2 (got {f.get('critic_rounds')!r})")
        for key in ("grounding", "reference_used"):
            if not f.get(key):
                problems.append(f"figure '{label}': manifest missing '{key}'")
    return problems


def run_all(wd: Path) -> int:
    """Definition of Done: re-run citations_lint + draft_lint against the final
    workdir, assert every figure is embedded as a vector PDF, then assert the latex
    verdict. Nonzero on the first failure."""
    # citations + draft are REQUIRED at the finish line; a missing artifact here
    # is a failure, not a skip.
    for script, required, label in (
        (CITATIONS_LINT, "refs.bib", "citations"),
        (DRAFT_LINT, "sections", "draft"),
    ):
        if not (wd / required).exists():
            print(f"\n===== gate: {script.name} =====")
            print(f"[run_gates] FAIL: required {label} artifact "
                  f"'{required}' absent in {wd} (DoD)")
            return 1
        rc = _run(script, [str(wd)])
        if rc != 0:
            return rc
    # figure gate: every figure has an embedded artifact; a converted figure's .svg must be a valid
    # hybrid (editable text over the render). Trivially passes when the paper has no figures.
    if not SVG_TOOLS.exists():
        print(f"\n===== gate: check_vector_pdf.py =====")
        print(f"[run_gates] FAIL: vector check script not found: {SVG_TOOLS}")
        return 1
    rc = _run(SVG_TOOLS, ["check", "--workdir", str(wd)])
    if rc != 0:
        return rc
    # figure critique-trace gate: image-model figures must have run the enforced vision-critique
    # loop (non-empty repair_logs, critic_rounds>=2, grounding fields). No-ops when no figures stage.
    print(f"\n===== gate: figure critique trace =====")
    crit_problems = check_figure_critique(wd)
    if crit_problems:
        for p in crit_problems:
            print(f"[run_gates] FAIL: {p}")
        return 1
    print("[run_gates] ok (image-model figures: non-empty critique trace + grounding fields)")
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
