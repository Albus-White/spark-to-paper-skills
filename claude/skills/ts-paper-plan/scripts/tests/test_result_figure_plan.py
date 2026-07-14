import json
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "blueprint_lint.py"


def _base(tmp_path, mode, figures):
    spec = {"name": "test", "results_mode": mode, "title": {"max_words": 20, "max_chars": 200},
            "citations": {"types": ["CORE"]},
            "sections": [{"id": "evaluation", "title": "Evaluation", "roles": ["evaluation", "results"], "words": [10, 20]}]}
    planned = [{"figure_id": item["id"], "class": item["class"], "route": item["route"],
                "purpose": item.get("claim_role", "evidence"), "source_of_truth": item["source_of_truth"],
                "claim_ids": ["C-001"], "section_role": "evaluation"} for item in figures]
    venue = {"papers": [{"title": "Relevant accepted paper", "source": {"url": "https://example.org/paper"},
                         "pdf": {"path": "accepted.pdf", "sha256": "a" * 64},
                         "metrics": {"page_count": 8, "unique_cited_references": 40, "total_figures": len(figures),
                                     "table_count": 0, "evaluation_count": 1,
                                     "figure_roles": {"evidence": len(figures)}, "evaluation_kinds": {"benchmark": 1},
                                     "evidence_dimensions": {"datasets": 1},
                                     "evaluation_difficulty": {"rating": "moderate", "drivers": ["fixture"], "rationale": "fixture"}}}],
             "aggregates": {"means": {}, "evidence_dimension_means": {}}, "sample_sufficiency": {"verdict": "SUFFICIENT"}}
    publication = {"targets": {"page_range": [7, 9], "minimum_unique_cited_references": 12,
                                "figure_count": len(figures), "table_count": 0}, "figure_plan": planned,
                   "table_plan": [], "section_plan": [{"section_id": "evaluation"}], "claim_ids": ["C-001"]}
    blueprint = {"paper_title": "Test", "venue_profile": "venue-profile.json", "publication_contract": "publication-contract.json", "section_order": ["evaluation"], "sections": {"evaluation": {
        "title": "Evaluation", "roles": ["evaluation", "results"],
        "target_words": [10, 20], "citation_types": [], "tables": [], "figures": figures}}}
    (tmp_path / "template.json").write_text(json.dumps(spec))
    (tmp_path / "accepted.pdf").write_bytes(b"fixture")
    (tmp_path / "venue-profile.json").write_text(json.dumps(venue))
    (tmp_path / "publication-contract.json").write_text(json.dumps(publication))
    (tmp_path / "blueprint.json").write_text(json.dumps(blueprint))


def _run(tmp_path):
    return subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)


def test_data_aware_accepts_one_sufficient_result_figure(tmp_path):
    _base(tmp_path, "data_aware", [{"id": "main", "class": "measured_evidence", "route": "DETERMINISTIC_OR_ORIGINAL_EVIDENCE", "renderer": "matplotlib",
                                    "source_of_truth": "canonical_result_facts", "claim_role": "main_comparison",
                                    "fact_ids": ["F-001"],
                                    "data_source": "research/evidence/results/results-manifest.jsonl"}])
    assert _run(tmp_path).returncode == 0


def test_data_aware_complete_result_program_passes(tmp_path):
    common = {"class": "measured_evidence", "route": "DETERMINISTIC_OR_ORIGINAL_EVIDENCE", "renderer": "matplotlib", "source_of_truth": "canonical_result_facts", "fact_ids": ["F-001"], "data_source": "research/evidence/results/results-manifest.jsonl"}
    figures = [{"id": "main", **common, "claim_role": "main_comparison"},
               {"id": "abl", **common, "claim_role": "ablation"}]
    _base(tmp_path, "data_aware", figures)
    assert _run(tmp_path).returncode == 0


def test_proposal_rejects_result_figure(tmp_path):
    _base(tmp_path, "proposal", [{"id": "main", "class": "measured_evidence", "route": "DETERMINISTIC_OR_ORIGINAL_EVIDENCE", "renderer": "matplotlib", "source_of_truth": "canonical_result_facts",
                                  "claim_role": "main_comparison", "data_source": "x"}])
    result = _run(tmp_path)
    assert result.returncode == 1 and "cannot plan" in result.stdout
