#!/usr/bin/env python3
"""Dependency-free test runner for unittest and the repository's simple pytest-style tests."""
from __future__ import annotations
import argparse,importlib.util,inspect,os,sys,tempfile,traceback
from pathlib import Path

class MonkeyPatch:
 def __init__(self): self.undo=[]
 def setenv(self,key,value):
  old=os.environ.get(key); existed=key in os.environ; os.environ[key]=value
  self.undo.append(lambda: os.environ.__setitem__(key,old) if existed else os.environ.pop(key,None))
 def setattr(self,obj,name,value):
  old=getattr(obj,name); setattr(obj,name,value); self.undo.append(lambda:setattr(obj,name,old))
 def close(self):
  for fn in reversed(self.undo): fn()

def load(path):
 name="repo_test_"+str(abs(hash(path))); spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module); return module

def run_pytest_style(paths):
 passed=failed=0
 for path in paths:
  module=load(path)
  for name,fn in inspect.getmembers(module,inspect.isfunction):
   if not name.startswith("test_"): continue
   temp=None; mp=None; kwargs={}
   try:
    sig=inspect.signature(fn)
    if "tmp_path" in sig.parameters: temp=tempfile.TemporaryDirectory(); kwargs["tmp_path"]=Path(temp.name)
    if "monkeypatch" in sig.parameters: mp=MonkeyPatch(); kwargs["monkeypatch"]=mp
    unsupported=set(sig.parameters)-set(kwargs)
    if unsupported: raise RuntimeError(f"unsupported fixtures: {sorted(unsupported)}")
    fn(**kwargs); print(f"PASS {path}:{name}"); passed+=1
   except Exception:
    print(f"FAIL {path}:{name}"); traceback.print_exc(); failed+=1
   finally:
    if mp: mp.close()
    if temp: temp.cleanup()
 return passed,failed

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("paths",nargs="*"); a=ap.parse_args(); paths=[Path(x) for x in a.paths] if a.paths else sorted(Path('codex/skills/ts-paper-figure/scripts/tests').glob('test_*.py'))
 passed,failed=run_pytest_style(paths); print(f"pytest-style: {passed} passed, {failed} failed"); return 1 if failed else 0
if __name__=="__main__": raise SystemExit(main())
