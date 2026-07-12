from __future__ import annotations
import importlib.util,tempfile,unittest,json
from pathlib import Path
def load(name):
 p=Path(__file__).parents[1]/"scripts"/name; s=importlib.util.spec_from_file_location(name,p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
failure=load("classify_failure.py")
class GateToolTest(unittest.TestCase):
 def test_failure_rule_order(self):
  text="RuntimeError: CUDA out of memory".lower(); matches=[c for c,p in failure.RULES if __import__('re').search(p,text,__import__('re').I)]; self.assertEqual(matches[0],"RESOURCE_EXHAUSTED")
 def test_verification_suite_is_model_selected(self):
  verify=load("validate_verification_suite.py"); self.assertFalse(hasattr(verify,"REQUIRED")); self.assertEqual(verify.PASSING,{"PASS","PASS_WITH_EXPLAINED_DEVIATION"})
 def test_domain_specific_verification_suite_passes_without_universal_tests(self):
  verify=load("validate_verification_suite.py")
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); (root/"proof.txt").write_text("matched reference")
   suite={"selection_judgment":{"implementation_summary":"Finite-volume conservation solver","reviewer":"main-model","risks":[{"risk_id":"R1","failure_mode":"flux sign inversion","scientific_consequence":"violates conservation","rationale":"custom boundary stencil","applicable":True,"covered_by":["flux-balance"]},{"risk_id":"R2","failure_mode":"gradient mismatch","scientific_consequence":"invalid optimizer","rationale":"solver is non-differentiable","applicable":False,"covered_by":[],"counterfactual_trigger":"a differentiable solver is introduced"}]},"tests":[{"test_id":"flux-balance","purpose":"check conservation","command":"solver --fixture","oracle":"net flux equals accumulation","observed":"matched reference","status":"PASS","evidence":["proof.txt"]}]}
   self.assertEqual(verify.validate(suite,root),[])
if __name__=="__main__": unittest.main()
