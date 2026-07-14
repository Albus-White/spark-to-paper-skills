#!/usr/bin/env python3
"""Initialize Research Lifecycle Core at the beginning of a ts-paper run."""
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; SKILLS=HERE.parent.parent; LIFE=SKILLS/"ts-research-lifecycle/scripts/lifecycle.py"
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--workdir",required=True); ap.add_argument("--profile",choices=["proposal","exploratory","standard_empirical","high_risk"],default="proposal"); ap.add_argument("--run-id",default=""); ap.add_argument("--resource-envelope",default=""); ap.add_argument("--user-policy",default=""); a=ap.parse_args(); wd=Path(a.workdir).resolve(); wd.mkdir(parents=True,exist_ok=True); root=wd/"research"
 try:
  existing=(root/"research_state.json").exists()
  if not existing:
   cmd=[sys.executable,str(LIFE),"--root",str(root),"init","--profile",a.profile,"--run-id",a.run_id or wd.name]
   rc=subprocess.call(cmd,timeout=120)
   if rc: return rc
  if a.resource_envelope:
   rc=subprocess.call([sys.executable,str(LIFE),"--root",str(root),"register-resource-envelope","--file",str(Path(a.resource_envelope).resolve())],timeout=120)
   if rc: return rc
  if a.user_policy:
   rc=subprocess.call([sys.executable,str(LIFE),"--root",str(root),"register-user-policy","--file",str(Path(a.user_policy).resolve())],timeout=120)
   if rc: return rc
  print(json.dumps({"ok":True,"existing":existing,"root":str(root),"resource_envelope":bool(a.resource_envelope),"user_policy":bool(a.user_policy)})); return 0
 except subprocess.TimeoutExpired: print(json.dumps({"ok":False,"error":"lifecycle initialization timed out"})); return 124
if __name__=="__main__": raise SystemExit(main())
