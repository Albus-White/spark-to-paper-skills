#!/usr/bin/env python3
"""Import stage artifacts into the Research Lifecycle Core without granting scientific verdicts."""
from __future__ import annotations
import argparse, importlib.util, json, shutil, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("rlc",HERE/"lifecycle.py"); rlc=importlib.util.module_from_spec(spec); spec.loader.exec_module(rlc)

def load(path): return json.loads(Path(path).read_text())
def ensure_copy(src,dst): dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst); return str(dst)
def same_file(left,right): return left.exists() and right.exists() and rlc.sha256_file(left)==rlc.sha256_file(right)
def advance(root,target):
 state=rlc.load_state(root)
 sequence=rlc.phase_sequence(state["profile"])
 while state["phase"]!=target:
  current=sequence.index(state["phase"]); goal=sequence.index(target)
  if current>=goal: break
  rlc.transition(root,sequence[current+1]); state=rlc.load_state(root)
def sync_idea(root,source,target,payload):
 state=rlc.load_state(root)
 if same_file(source,target) and state["active"].get("idea_id"):
  return state["active"]["idea_id"]
 idea_id=rlc.register_idea(root,payload,state["active"].get("idea_id"),"L0",None)
 ensure_copy(source,target)
 return idea_id

def sync_story(root,workdir):
 story_src=workdir/"story.json"; story=load(story_src); hp=story["research_hypothesis"]
 idea={**hp,"claims":story.get("innovation_claims",[])}
 target=root/"grounding/story.json"; idea_id=sync_idea(root,story_src,target,idea)
 if "G0" not in rlc.load_state(root)["gates"]:
  rlc.set_gate(root,"G0","PASS",[str(target.relative_to(root))],"Story intake and assumptions recorded","pipeline-sync")
 advance(root,"IDEA_DRAFTED")
 return {"idea_id":idea_id}
def sync_proposal(root,workdir):
 idea_src=workdir/"research_idea.json"; hp=load(idea_src); target=root/"grounding/research_idea.json"
 idea_id=sync_idea(root,idea_src,target,hp)
 if "G0" not in rlc.load_state(root)["gates"]:
  rlc.set_gate(root,"G0","PASS",[str(target.relative_to(root))],"Proposal normalized into a falsifiable research Idea","pipeline-sync")
 advance(root,"IDEA_DRAFTED")
 return {"idea_id":idea_id}
def sync_cite(root,workdir):
 bench=workdir/"benchmark_candidates.json"; refs=workdir/"refs.bib"
 copied=[Path(ensure_copy(bench,root/"grounding/benchmark_candidates.json"))]
 if refs.exists(): copied.append(Path(ensure_copy(refs,root/"grounding/refs.bib")))
 idea_evidence=next((path for path in (root/"grounding/story.json",root/"grounding/research_idea.json") if path.exists()),None)
 if not idea_evidence: raise ValueError("cite sync requires a synchronized story or research_idea")
 return {"benchmark":str(copied[0]),"pending_gates":["G1","G2"]}
def rewrite_claim_refs(value,mapping):
 if isinstance(value,dict):
  return {key:([mapping.get(item,item) for item in item_value] if key=="claim_ids" and isinstance(item_value,list) else mapping.get(item_value,item_value) if key=="claim_id" and isinstance(item_value,str) else rewrite_claim_refs(item_value,mapping)) for key,item_value in value.items()}
 if isinstance(value,list): return [rewrite_claim_refs(item,mapping) for item in value]
 return value
def sync_plan(root,workdir):
 claim_src=workdir/"claim_registry.json"; contract_src=workdir/"research_contract.json"; design_src=workdir/"design_evidence_matrix.json"
 normalized_target=root/"grounding/research_contract.candidate.json"
 state=rlc.load_state(root)
 if same_file(contract_src,root/"grounding/research_contract.source.json"):
  return {"contract_candidate":str(normalized_target),"pending_gate":"G3"}
 claims=load(claim_src); registry_path=root/"claims/claim-registry.json"; registry=load(registry_path)
 by_text={item["claim_text"]:item["claim_id"] for item in registry.get("claims",[])}; mapping={}
 for claim in claims.get("claims",[]):
  claim_text=claim.get("claim_text")
  claim_id=by_text.get(claim_text)
  if not claim_id:
   claim_id=rlc.register_claim(root,{key:claim[key] for key in ("claim_text","claim_type","essential","strength","scope","required_evidence")})
   by_text[claim_text]=claim_id
  if claim.get("claim_id"): mapping[claim["claim_id"]]=claim_id
 contract=rewrite_claim_refs(load(contract_src),mapping)
 rlc.write_json(normalized_target,contract)
 targets=[Path(ensure_copy(contract_src,root/"grounding/research_contract.source.json")),Path(ensure_copy(claim_src,root/"grounding/claim_registry.source.json")),normalized_target]
 if design_src.exists(): targets.append(Path(ensure_copy(design_src,root/"grounding/design_evidence_matrix.json")))
 return {"contract_candidate":str(normalized_target),"claim_id_map":mapping,"pending_gate":"G3"}
def sync_manuscript(root,workdir):
 manuscript_id=rlc.register_manuscript(root,workdir)
 return {"manuscript_id":manuscript_id}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--root",required=True); ap.add_argument("--workdir",required=True); ap.add_argument("stage",choices=["story","proposal","cite","plan","manuscript"]); a=ap.parse_args(); root=Path(a.root).resolve(); wd=Path(a.workdir).resolve()
 try:
  result={"story":sync_story,"proposal":sync_proposal,"cite":sync_cite,"plan":sync_plan,"manuscript":sync_manuscript}[a.stage](root,wd); print(json.dumps({"ok":True,**result},indent=2)); return 0
 except Exception as exc: print(json.dumps({"ok":False,"error":str(exc)},indent=2),file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())
