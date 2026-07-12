#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path

def git(repo,*args): return subprocess.check_output(["git","-C",str(repo),*args],stderr=subprocess.STDOUT,text=True,timeout=30).strip()
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("repo"); ap.add_argument("--purpose",required=True); ap.add_argument("--official-status",required=True); ap.add_argument("--license",required=True); ap.add_argument("--out",required=True); a=ap.parse_args(); repo=Path(a.repo).resolve()
 try:
  commit=git(repo,"rev-parse","HEAD"); url=git(repo,"remote","get-url","origin"); branch=git(repo,"rev-parse","--abbrev-ref","HEAD"); dirty=bool(git(repo,"status","--porcelain")); tag=git(repo,"describe","--tags","--exact-match") if not dirty else ""
 except Exception as exc:
  print(json.dumps({"ok":False,"error":str(exc)})); return 1
 payload={"purpose":a.purpose,"url":url,"commit":commit,"branch":branch,"tag":tag,"official_status":a.official_status,"license":a.license,"local_path":str(repo),"dirty":dirty}
 Path(a.out).write_text(json.dumps(payload,indent=2)+"\n"); print(json.dumps({"ok":True,"out":a.out,"commit":commit,"dirty":dirty},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
