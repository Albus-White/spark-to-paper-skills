#!/usr/bin/env python3
"""handoff_to_experiments.py — Stage 8 bridge: hand a FINISHED ts-paper draft to the experiment/
repair project (AutoPaperFactory's `sci-paper-repair`).

Runs ONLY after the suite produced a complete first-draft paper (main.pdf exists, gates green).
Copies the LaTeX manuscript (main.tex + sections + refs.bib + figures incl. the ts-figure-optimize
vector PDFs + template .sty/.cls) into the factory's draft-ingest location (`<factory>/input/draft/`),
where `sci-paper-repair` Step 0 picks it up to diagnose, run FEASIBLE experiments (only with real
data/code — never fabricated), rewrite the experiment section, and fill result tables in `<factory>/paper/`.

Does NOT run experiments itself and does NOT touch `<factory>/paper/` (sci-paper-repair owns that,
its source of truth). Idempotent copy.

Usage:
  python handoff_to_experiments.py --workdir ts_paper_run \
      [--factory /mnt/data0/LX_Bench/CS/AutoPaperFactory]   # or $AUTOPAPERFACTORY_ROOT
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

DEFAULT_FACTORY = "/mnt/data0/LX_Bench/CS/AutoPaperFactory"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True, help="the finished ts-paper run dir (holds main.tex, sections/, …)")
    ap.add_argument("--factory", default=os.environ.get("AUTOPAPERFACTORY_ROOT", DEFAULT_FACTORY))
    a = ap.parse_args()

    wd = Path(a.workdir).resolve()
    factory = Path(a.factory).resolve()
    if not (wd / "main.tex").exists():
        print(f"FATAL: {wd}/main.tex not found — run the full ts-paper pipeline first (handoff is Stage 8).", file=sys.stderr)
        return 2
    if not (factory / "paper_config.yaml").exists():
        print(f"FATAL: {factory} is not an AutoPaperFactory project root (no paper_config.yaml). "
              f"Pass --factory or set AUTOPAPERFACTORY_ROOT.", file=sys.stderr)
        return 2

    dst = factory / "input" / "draft"
    dst.mkdir(parents=True, exist_ok=True)
    copied = []
    # core manuscript files
    for name in ("main.tex", "refs.bib", "template.json"):
        if (wd / name).exists():
            shutil.copy2(wd / name, dst / name); copied.append(name)
    # directories (sections, figures incl. vector PDFs, any template assets)
    for d in ("sections", "figures"):
        if (wd / d).is_dir():
            tgt = dst / d
            if tgt.exists():
                shutil.rmtree(tgt)
            shutil.copytree(wd / d, tgt); copied.append(d + "/")
    # template .sty/.cls/.bst sitting at the workdir root
    for p in wd.glob("*.sty"):
        shutil.copy2(p, dst / p.name); copied.append(p.name)
    for ext in ("*.cls", "*.bst"):
        for p in wd.glob(ext):
            shutil.copy2(p, dst / p.name); copied.append(p.name)

    print(f"handoff: copied {len(copied)} item(s) -> {dst}")
    for c in copied:
        print(f"  + {c}")
    print("\nNEXT (Stage 8 — runs in the AutoPaperFactory project, NOT this suite):")
    print(f"  cd {factory}")
    print(f"  # then invoke the sci-paper-repair skill — it ingests input/draft/ into ./paper/,")
    print(f"  # diagnoses logic, runs FEASIBLE experiments (real data/code only), rewrites the")
    print(f"  # experiment section, fills result tables, and keeps claim-evidence consistency.")
    print(f"  # If an experiment cannot be run, it writes a requirements report — never fabricated numbers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
