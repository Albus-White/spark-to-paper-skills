#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
RULES=[
 ("RESOURCE_EXHAUSTED",r"out of memory|oom|no space left|quota exceeded"),
 ("DEPENDENCY_FAILURE",r"modulenotfounderror|importerror|undefined symbol|version conflict|cannot import"),
 ("INFRASTRUCTURE_FAILURE",r"cuda driver|connection timed out|permission denied|network is unreachable|device unavailable"),
 ("DATA_FAILURE",r"corrupt|checksum mismatch|file not found.*dataset|invalid label|license"),
 ("PROTOCOL_FAILURE",r"data leakage|test leakage|split mismatch|metric mismatch|unfair baseline"),
 ("IMPLEMENTATION_FAILURE",r"traceback|runtimeerror|valueerror|assertionerror|nan|inf"),
]
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("log"); ap.add_argument("--exit-code",type=int,default=1); a=ap.parse_args(); text=Path(a.log).read_text(errors="replace").lower(); label="NONE" if a.exit_code==0 else "INCONCLUSIVE"
 matches=[]
 for candidate,pattern in RULES:
  if re.search(pattern,text,re.I): matches.append(candidate)
 if matches: label=matches[0]
 print(json.dumps({"failure_class":label,"candidates":matches,"exit_code":a.exit_code},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
