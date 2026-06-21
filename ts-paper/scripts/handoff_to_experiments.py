#!/usr/bin/env python3
"""handoff_to_experiments.py — Stage 8 bridge: hand a FINISHED ts-paper draft to the IN-REPO
experiment/repair skill `sci-paper-repair` (now part of this same suite — no separate project).

Runs ONLY after the suite produced a complete first-draft paper (main.pdf exists, gates green).
It creates a local EXPERIMENT WORKSPACE (default `<workdir>/experiments/`), seeds it with the
`sci-paper-repair` paper_config.yaml template, and copies the LaTeX manuscript (main.tex + sections +
refs.bib + figures incl. the ts-figure-optimize vector PDFs + template .sty/.cls) into
`<workspace>/input/draft/`. Then you invoke the in-repo `sci-paper-repair` skill from that workspace:
it ingests input/draft/ into ./paper/, diagnoses logic, runs FEASIBLE experiments (real data/code only —
never fabricated), rewrites the experiment section, and fills result tables.

Does NOT run experiments itself and does NOT touch `<workspace>/paper/` (sci-paper-repair owns that).
Idempotent copy.

Usage:
  python handoff_to_experiments.py --workdir <ts_paper_run> [--workspace <dir>]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _repo_root() -> Path:
    for p in HERE.parents:
        if (p / "sci-paper-repair").is_dir():
            return p
    return HERE.parents[1]  # fall back to the suite root (…/<repo>), never the grandparent outside it


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True, help="the finished ts-paper run dir (holds main.tex, sections/, …)")
    ap.add_argument("--workspace", default="", help="experiment workspace dir (default: <workdir>/experiments)")
    a = ap.parse_args()

    wd = Path(a.workdir).resolve()
    if not (wd / "main.tex").exists():
        print(f"FATAL: {wd}/main.tex not found — run the full ts-paper pipeline first (handoff is Stage 8).", file=sys.stderr)
        return 2

    repo = _repo_root()
    skill = repo / "sci-paper-repair"
    workspace = Path(a.workspace).resolve() if a.workspace else (wd / "experiments")
    workspace.mkdir(parents=True, exist_ok=True)

    # seed the workspace config from the in-repo skill template (don't overwrite an existing one)
    cfg_tmpl = skill / "paper_config.yaml"
    if cfg_tmpl.exists() and not (workspace / "paper_config.yaml").exists():
        shutil.copy2(cfg_tmpl, workspace / "paper_config.yaml")

    dst = workspace / "input" / "draft"
    dst.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in ("main.tex", "refs.bib", "template.json"):
        if (wd / name).exists():
            shutil.copy2(wd / name, dst / name); copied.append(name)
    for d in ("sections", "figures"):
        if (wd / d).is_dir():
            tgt = dst / d
            if tgt.exists():
                shutil.rmtree(tgt)
            shutil.copytree(wd / d, tgt); copied.append(d + "/")
    for ext in ("*.sty", "*.cls", "*.bst"):
        for p in wd.glob(ext):
            shutil.copy2(p, dst / p.name); copied.append(p.name)

    print(f"handoff: workspace = {workspace}")
    print(f"handoff: copied {len(copied)} item(s) -> {dst}")
    for c in copied:
        print(f"  + {c}")
    print("\nNEXT (Stage 8 — IN-REPO sci-paper-repair skill):")
    print(f"  cd {workspace}")
    print(f"  # invoke the `sci-paper-repair` skill ({skill}); it ingests input/draft/ into ./paper/,")
    print(f"  # diagnoses logic, runs FEASIBLE experiments (real data/code only), rewrites the experiment")
    print(f"  # section, fills result tables, keeps claim-evidence consistency. Overleaf is OFF by default")
    print(f"  # (paper_config.yaml: require_overleaf_url=false); enable it there + provide OVERLEAF_* in ./.env.")
    print(f"  # If an experiment cannot be run, it writes a requirements report — never fabricated numbers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
