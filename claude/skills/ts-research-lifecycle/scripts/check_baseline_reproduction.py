#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math
from pathlib import Path

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("spec"); ap.add_argument("--out"); a=ap.parse_args(); data=json.loads(Path(a.spec).read_text()); issues=[]; rows=[]
 required=["benchmark","repository_commit","split","metric_implementation","comparisons"]
 for key in required:
  if not data.get(key): issues.append(f"missing {key}")
 for i,item in enumerate(data.get("comparisons",[])):
  try:
   observed=float(item["observed"]); expected=float(item["expected"]); tolerance=float(item["tolerance"]); delta=abs(observed-expected); passed=delta<=tolerance
  except Exception: issues.append(f"comparisons[{i}] invalid numeric fields"); continue
  rows.append({**item,"absolute_delta":delta,"pass":passed})
  if not passed: issues.append(f"{item.get('name',i)} outside tolerance: {delta} > {tolerance}")
 verdict="PASS" if not issues else "FAIL_UNRESOLVED"
 report={"ok":not issues,"verdict":verdict,"issues":issues,"comparisons":rows,"protocol":{"split":data.get("split"),"metric_implementation":data.get("metric_implementation"),"repository_commit":data.get("repository_commit")}}
 if a.out: Path(a.out).write_text(json.dumps(report,indent=2)+"\n")
 print(json.dumps(report,indent=2)); return 0 if not issues else 1
if __name__=="__main__": raise SystemExit(main())
