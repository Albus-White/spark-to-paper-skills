from __future__ import annotations
import importlib.util, unittest
from pathlib import Path
P=Path(__file__).parents[1]/"scripts/validate_research_artifacts.py"
s=importlib.util.spec_from_file_location("v",P); v=importlib.util.module_from_spec(s); s.loader.exec_module(v)
class ArtifactValidationTest(unittest.TestCase):
 def test_unverified_grounding_fails(self):
  issues=[]; v.validate_grounding({"design_choices":[{"choice_id":"D1"}]},issues); self.assertTrue(issues)
 def test_grounding_validator_does_not_replace_scientific_judgment(self):
  issues=[]; v.validate_grounding({"design_choices":[{"choice_id":"D1","question":"Which metric?","decision":"Domain score","rationale":"Primary sources define it","evidence":["paper"],"uncertainty":"low"}]},issues); self.assertEqual(issues,[])
 def test_benchmark_candidate_requires_traceable_source(self):
  issues=[]; v.validate_benchmarks({"candidates":[{"name":"B"}],"decision":{"classification":"OFFICIAL_BENCHMARK_FOUND","rationale":"x","search_scope":"official site"}},issues); self.assertTrue(any("source" in x for x in issues))
 def test_no_valid_benchmark_is_structurally_accepted(self):
  issues=[]; v.validate_benchmarks({"candidates":[],"decision":{"classification":"NO_VALID_PUBLIC_BENCHMARK","rationale":"No compatible task was found","search_scope":"official repositories and primary papers"}},issues); self.assertEqual(issues,[])
 def test_test_informed_evolution_requires_new_data(self):
  issues=[]; v.validate_idea_evolution({"source_idea_id":"i","decision":"NARROW_SCOPE","mechanism_verdict":"partial","trigger_evidence":["x"],"old_evidence_impact":{},"independent_revalidation_plan":{},"approval":"APPROVED","revision_level":"L2","test_data_used_for_discovery":True},issues); self.assertTrue(any("new confirmation" in x for x in issues))
 def test_valid_grounding(self):
  issues=[]; v.validate_grounding({"design_choices":[{"choice_id":"D1","question":"metric","decision":"MAE","rationale":"official","evidence":["paper"],"uncertainty":"low"}]},issues); self.assertEqual(issues,[])
 def test_physical_study_contract_uses_domain_neutral_fields(self):
  claims={"claims":[{"claim_id":"C-001"}]}; issues=[]
  contract={"claim_ids":["C-001"],"experiments":[{"experiment_id":"E-001","claim_ids":["C-001"],"why_it_tests_claim":"matched specimens","positive_interpretation":"supports","negative_interpretation":"rejects","confounders":["calibration drift"],"out_of_scope_conclusions":["other temperatures"]}],"study_inputs":["specimen batch"],"protocols":["calibrated impedance protocol"],"outcomes":["conductivity"],"comparators":["untreated specimens"],"replication_plan":{"type":"specimens","identifiers":["S1","S2"],"rationale":"material variability"},"statistical_plan":{"estimand":"matched difference"},"test_set_policy":{"max_access":1},"stop_conditions":["precision reached"],"budget":{"max_runs":4,"max_branches":1,"max_branch_depth":1}}
  v.validate_contract(contract,claims,issues); self.assertEqual(issues,[])
if __name__=="__main__": unittest.main()
