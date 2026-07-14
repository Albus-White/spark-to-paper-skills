from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "manuscript_boundary_lint.py"
spec = importlib.util.spec_from_file_location("manuscript_boundary", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def fixture(tmp_path, text):
    contract_id = "publication-contract-v-001"
    (tmp_path / "research/contracts").mkdir(parents=True)
    (tmp_path / "research/research_state.json").write_text(json.dumps({"active": {"publication_contract_id": contract_id}}))
    (tmp_path / f"research/contracts/{contract_id}.json").write_text(json.dumps({
        "manuscript_content_policy": {"internal_provenance_location": "artifact_package", "reader_relevant_reproducibility_only": True,
                                      "forbid_page_filler": True, "allowed_internal_identifiers": []}
    }))
    (tmp_path / "sections").mkdir()
    (tmp_path / "sections/appendix.tex").write_text(text)


def test_raw_hash_table_and_gate_ledger_are_rejected(tmp_path):
    fixture(tmp_path, "Artifact SHA-256: " + "a" * 64 + "\\nSee research/reports/gates/G3.json and Gate G3.")
    report = module.scan(tmp_path)
    assert not report["ok"]
    assert {item["rule"] for item in report["issues"]} >= {"raw_internal_hash", "internal_artifact_path", "internal_gate_identifier"}


def test_reader_relevant_reproducibility_text_is_allowed(tmp_path):
    fixture(tmp_path, "We used chronological splitting and report the preprocessing and evaluation protocol in full.")
    assert module.scan(tmp_path)["ok"]
