#!/usr/bin/env python3
from __future__ import annotations
import subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve(); tool=HERE.parents[2]/"ts-research-lifecycle/scripts/validate_research_artifacts.py"
if len(sys.argv)!=2: print("usage: research_contract_lint.py <workdir>"); raise SystemExit(2)
wd=Path(sys.argv[1]).resolve()
try:
    code = subprocess.call([sys.executable,str(tool),"contract",str(wd/"research_contract.json"),
                            "--claims",str(wd/"claim_registry.json")], timeout=300)
except subprocess.TimeoutExpired:
    print("research contract validation timed out", file=sys.stderr); code = 124
raise SystemExit(code)
