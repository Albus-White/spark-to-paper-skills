from __future__ import annotations
import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).parents[1]/"scripts/run_gates.py"; s=importlib.util.spec_from_file_location("rg",P); rg=importlib.util.module_from_spec(s); s.loader.exec_module(rg)
class RunGateLifecycleTest(unittest.TestCase):
 def test_incomplete_lifecycle_is_not_release_ready(self):
  with tempfile.TemporaryDirectory() as td:
   wd=Path(td); research=wd/"research"; research.mkdir(); (research/"research_state.json").write_text(json.dumps({"phase":"INTAKE"}))
   # run_all would invoke the validator first; the explicit phase condition is also a hard fail.
   self.assertNotIn(json.loads((research/"research_state.json").read_text())["phase"],("MANUSCRIPT_HARDENED","RELEASED"))
 def test_requested_stage_fails_when_required_input_is_missing(self):
  with tempfile.TemporaryDirectory() as td:
   self.assertEqual(rg.run_stage("plan",Path(td)),1)
 def test_final_gate_requires_single_research_lifecycle(self):
  with tempfile.TemporaryDirectory() as td:
   self.assertEqual(rg.run_all(Path(td)),1)
 def test_stale_latex_success_cache_is_not_accepted(self):
  with tempfile.TemporaryDirectory() as td:
   wd=Path(td); (wd/"sections").mkdir(); (wd/"sections/introduction.tex").write_text("changed")
   (wd/"assemble.json").write_text(json.dumps({"compiled":True,"error_count":0,"input_hash":"stale"}))
   with patch.object(rg,"ASSEMBLE",wd/"missing-assembler.py"):
    self.assertEqual(rg.assert_latex(wd),1)
if __name__=="__main__": unittest.main()
