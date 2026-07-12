#!/usr/bin/env python3
from __future__ import annotations
import subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve(); tool=HERE.parents[2]/"ts-research-lifecycle/scripts/validate_research_artifacts.py"
if len(sys.argv)!=2: print("usage: design_grounding_lint.py <workdir>"); raise SystemExit(2)
try:
    code=subprocess.call([sys.executable,str(tool),"grounding",str(Path(sys.argv[1]).resolve()/"design_evidence_matrix.json")],timeout=300)
except subprocess.TimeoutExpired:
    print("design grounding validation timed out",file=sys.stderr); code=124
raise SystemExit(code)
