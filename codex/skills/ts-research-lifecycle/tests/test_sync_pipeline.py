from __future__ import annotations
import importlib.util,json,tempfile,unittest
from pathlib import Path
P=Path(__file__).parents[1]/"scripts"
def mod(name): s=importlib.util.spec_from_file_location(name,P/name); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
rlc=mod("lifecycle.py"); sync=mod("sync_pipeline.py")
class SyncTest(unittest.TestCase):
 def test_direct_proposal_sync(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/"research"; wd=Path(td)/"wd"; wd.mkdir(); rlc.init_layout(root,"proposal","x")
   idea={"problem":"p","hypothesis":"h","proposed_mechanism":"m","scope":"s","assumptions":["a"],"falsifiers":["f"],"claims":["c"],"alternative_explanations":["x"],"minimum_validation_path":"v"}
   (wd/"research_idea.json").write_text(json.dumps(idea)); sync.sync_proposal(root,wd)
   self.assertEqual(rlc.load_state(root)["phase"],"IDEA_DRAFTED")
   self.assertTrue((root/"grounding/research_idea.json").exists())
 def test_story_cite_plan_sync(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/"research"; wd=Path(td)/"wd"; wd.mkdir(); rlc.init_layout(root,"proposal","x")
   story={"research_hypothesis":{"problem":"p","hypothesis":"h","proposed_mechanism":"m","scope":"s","assumptions":["a"],"falsifiers":["f"],"alternative_explanations":["x"],"minimum_validation_path":"v"},"innovation_claims":["c"]}
   (wd/"story.json").write_text(json.dumps(story)); sync.sync_story(root,wd); self.assertEqual(rlc.load_state(root)["phase"],"IDEA_DRAFTED")
   (wd/"benchmark_candidates.json").write_text(json.dumps({"candidates":[],"decision":{"classification":"NO_PUBLIC_BENCHMARK","rationale":"searched"}})); (wd/"refs.bib").write_text("@x{}")
   result=sync.sync_cite(root,wd); self.assertEqual(rlc.load_state(root)["phase"],"IDEA_DRAFTED")
   self.assertEqual(result["pending_gates"],["G1","G2"]); self.assertNotIn("G2",rlc.load_state(root)["gates"])
   (wd/"claim_registry.json").write_text(json.dumps({"claims":[{"claim_id":"C-001","claim_text":"c","claim_type":"method","essential":True,"strength":"bounded","scope":"s","required_evidence":["e"],"support_status":"UNVERIFIED"}]}))
   contract={"claim_ids":["C-001"],"experiments":["e"],"study_inputs":["d"],"protocols":["s"],"outcomes":["m"],"comparators":["b"],"replication_plan":{"type":"case","identifiers":["r1"]},"statistical_plan":{"x":1},"test_set_policy":{"x":1},"stop_conditions":["stop"],"budget":{"runs":1}}
   (wd/"research_contract.json").write_text(json.dumps(contract)); (wd/"design_evidence_matrix.json").write_text("{}")
   result=sync.sync_plan(root,wd); self.assertEqual(rlc.load_state(root)["phase"],"IDEA_DRAFTED")
   self.assertEqual(result["pending_gate"],"G3"); self.assertIsNone(rlc.load_state(root)["active"]["contract_id"])
   candidate=(root/"grounding/research_contract.candidate.json").read_text()
   sync.sync_story(root,wd); sync.sync_cite(root,wd); sync.sync_plan(root,wd)
   self.assertEqual((root/"grounding/research_contract.candidate.json").read_text(),candidate)
 def test_plan_remaps_external_claim_ids(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/"research"; wd=Path(td)/"wd"; wd.mkdir(); rlc.init_layout(root,"proposal","x")
   story={"research_hypothesis":{"problem":"p","hypothesis":"h","proposed_mechanism":"m","scope":"s","assumptions":["a"],"falsifiers":["f"],"alternative_explanations":["x"],"minimum_validation_path":"v"},"innovation_claims":["c"]}
   (wd/"story.json").write_text(json.dumps(story)); sync.sync_story(root,wd)
   (wd/"benchmark_candidates.json").write_text(json.dumps({"candidates":[],"decision":{"classification":"NO_PUBLIC_BENCHMARK","rationale":"searched"}})); sync.sync_cite(root,wd)
   (wd/"claim_registry.json").write_text(json.dumps({"claims":[{"claim_id":"external-alpha","claim_text":"c","claim_type":"method","essential":True,"strength":"bounded","scope":"s","required_evidence":["e"],"support_status":"UNVERIFIED"}]}))
   contract={"claim_ids":["external-alpha"],"experiments":[{"experiment_id":"E-1","claim_ids":["external-alpha"],"why_it_tests_claim":"x","positive_interpretation":"x","negative_interpretation":"x","confounders":["x"],"out_of_scope_conclusions":["x"]}],"study_inputs":["d"],"protocols":["s"],"outcomes":["m"],"comparators":["b"],"replication_plan":{"type":"case","identifiers":["r1"]},"statistical_plan":{"x":1},"test_set_policy":{"x":1},"stop_conditions":["stop"],"budget":{"runs":1}}
   (wd/"research_contract.json").write_text(json.dumps(contract)); (wd/"design_evidence_matrix.json").write_text("{}")
   sync.sync_plan(root,wd); candidate=rlc.read_json(root/"grounding/research_contract.candidate.json")
   self.assertEqual(candidate["claim_ids"],["C-001"]); self.assertEqual(candidate["experiments"][0]["claim_ids"],["C-001"])
if __name__=="__main__": unittest.main()
