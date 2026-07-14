from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "run_paperbanana_pipeline.py"
spec = importlib.util.spec_from_file_location("paperbanana_orchestrator", SCRIPT)
orchestrator = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(orchestrator)


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path: Path, figure_class="explanatory_synthesis"):
    research = tmp_path / "research"
    contract_id = "publication-contract-v-001"
    route_path = "manuscript/figure-routing.json"
    write(research / "research_state.json", {"active": {
        "publication_contract_id": contract_id, "figure_routing": route_path,
    }})
    planned = {"figure_id": "overview", "class": figure_class, "purpose": "explain method",
               "route": "PAPERBANANA_REQUIRED" if figure_class == "explanatory_synthesis" else "DOMAIN_NATIVE"}
    write(research / f"contracts/{contract_id}.json", {"figure_plan": [planned]})
    write(research / route_path, {"figures": [{
        **planned, "section_role": "method", "claim_ids": ["C-001"], "semantic_type": "method_overview",
        "caption": "Method overview", "source_of_truth": "research/program.json", "renderer": "paperbanana",
        "renderer_rationale": "synthesis needs a semantic illustration",
        "required_content": ["mechanism"], "forbidden_content": ["invented result"],
        "venue_figure_type": "method overview", "renderer_policy": "PAPERBANANA_REQUIRED",
        "candidate_budget": {"planned_candidates": 2, "safety_cap": 3,
            "resource_basis": "frozen figure budget", "rationale": "layout uncertainty",
            "stop_conditions": ["faithful readable image selected"]},
        "final_formats": ["png"], "accessibility": {"alt_text": True},
        "typography": {"family": "venue default"}, "drawai_status": "UNAVAILABLE_EVIDENCED_SKIP",
    }]})


def test_orchestrator_initializes_only_from_frozen_route(tmp_path):
    fixture(tmp_path)
    pipeline = orchestrator.initialize(tmp_path, "overview")
    contract = json.loads((pipeline / "figure_contract.json").read_text())
    plan = json.loads((pipeline / "search_plan.json").read_text())
    assert contract["publication_contract_sha256"]
    assert contract["figure_routing_sha256"]
    assert plan["planned_candidates"] == 2
    assert plan["reference_strategy"]["search_required"] is True


def test_orchestrator_rejects_domain_native_route(tmp_path):
    fixture(tmp_path, figure_class="exact_structure")
    try:
        orchestrator.initialize(tmp_path, "overview")
    except ValueError as exc:
        assert "not routed through PaperBanana" in str(exc)
    else:
        raise AssertionError("domain-native route unexpectedly entered PaperBanana")
