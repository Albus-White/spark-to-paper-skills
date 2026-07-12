from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
VALIDATOR = SCRIPTS / "validate_results_binding.py"
LIFECYCLE_PATH = SCRIPTS.parents[1] / "ts-research-lifecycle" / "scripts" / "lifecycle.py"
spec = importlib.util.spec_from_file_location("lifecycle_fixture", LIFECYCLE_PATH)
lifecycle = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(lifecycle)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manuscript_value_is_hash_bound_to_canonical_fact(tmp_path):
    research = tmp_path / "research"
    lifecycle.init_layout(research, "standard_empirical", "binding-test")
    idea_id = lifecycle.register_idea(research, {
        "problem": "Estimate conductivity", "hypothesis": "Treatment changes conductivity",
        "proposed_mechanism": "Ion mobility changes", "scope": "fixed temperature",
        "assumptions": ["calibrated sensor"], "falsifiers": ["no matched difference"],
        "claims": ["conductivity changes"], "alternative_explanations": ["sensor drift"],
    }, None, "L0", None)
    lifecycle.register_claim(research, {
        "claim_text": "Conductivity changes", "claim_type": "empirical result claim",
        "essential": True, "strength": "bounded", "scope": "fixed temperature",
        "required_evidence": ["registered run"],
    })
    state = lifecycle.load_state(research)
    state["active"]["contract_id"] = "contract-v-001"
    lifecycle.write_json(research / "contracts/contract-v-001.json", {
        "contract_id": "contract-v-001",
        "experiments": [{"experiment_id": "E-001", "claim_ids": ["C-001"]}],
    })
    lifecycle.save_state(research, state, "fixture")
    lifecycle.write_json(research / "experiments/runs/run-0001/run_manifest.json", {
        "run_id": "run-0001", "idea_id": idea_id, "contract_id": "contract-v-001",
        "experiment_ids": ["E-001"], "status": "completed",
    })
    raw = research / "evidence/results/raw.json"; raw.parent.mkdir(parents=True, exist_ok=True); raw.write_text("{\"value\": 0.42}")
    code = research / "code/integration/aggregate.py"; code.parent.mkdir(parents=True, exist_ok=True); code.write_text("print(0.42)")
    manifest = research / "evidence/results/results-manifest.jsonl"
    fact = {
        "fact_id": "F-001", "claim_ids": ["C-001"], "value": 0.42, "unit": "S/m",
        "run_ids": ["run-0001"], "source_artifacts": ["evidence/results/raw.json"],
        "source_hashes": {"evidence/results/raw.json": digest(raw)},
        "aggregation": {"method": "direct", "code_artifact": "code/integration/aggregate.py", "code_hash": digest(code)},
    }
    manifest.write_text(json.dumps(fact) + "\n", encoding="utf-8")
    section = tmp_path / "sections/results.tex"; section.parent.mkdir(); section.write_text("Conductivity was 0.42 S/m.\n")
    binding = {
        "research_manifest_sha256": digest(manifest),
        "bindings": [{"fact_id": "F-001", "artifact": "sections/results.tex", "line": 1,
                      "rendered_value": "0.42", "artifact_sha256": digest(section)}],
    }
    (tmp_path / "results_bindings.json").write_text(json.dumps(binding), encoding="utf-8")
    valid = subprocess.run([sys.executable, str(VALIDATOR), str(tmp_path)], capture_output=True, text=True)
    assert valid.returncode == 0, valid.stdout + valid.stderr
    section.write_text("Conductivity was 0.41 S/m.\n")
    stale = subprocess.run([sys.executable, str(VALIDATOR), str(tmp_path)], capture_output=True, text=True)
    assert stale.returncode == 1
    assert "artifact hash mismatch" in stale.stdout
