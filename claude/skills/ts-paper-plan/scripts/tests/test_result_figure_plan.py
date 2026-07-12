import json
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "blueprint_lint.py"


def _base(tmp_path, mode, figures):
    spec = {"name": "test", "results_mode": mode, "title": {"max_words": 20, "max_chars": 200},
            "citations": {"types": ["CORE"]},
            "sections": [{"id": "evaluation", "title": "Evaluation", "roles": ["evaluation", "results"], "words": [10, 20]}]}
    venue = {"official_guidance": [], "representative_papers": [{"title": "Relevant accepted paper", "url": "https://example.org/paper"}], "field_conventions": [], "user_requirements": {}, "design_decisions": {"figures": "model-selected from evidence"}, "limitations": [], "reviewer": {"id": "main-model"}}
    blueprint = {"paper_title": "Test", "venue_study": "venue-study.json", "section_order": ["evaluation"], "sections": {"evaluation": {
        "title": "Evaluation", "roles": ["evaluation", "results"],
        "target_words": [10, 20], "citation_types": [], "tables": [], "figures": figures}}}
    (tmp_path / "template.json").write_text(json.dumps(spec))
    (tmp_path / "venue-study.json").write_text(json.dumps(venue))
    (tmp_path / "blueprint.json").write_text(json.dumps(blueprint))


def _run(tmp_path):
    return subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)


def test_data_aware_accepts_one_sufficient_result_figure(tmp_path):
    _base(tmp_path, "data_aware", [{"id": "main", "renderer": "matplotlib",
                                    "source_of_truth": "measured_data", "claim_role": "main_comparison",
                                    "fact_ids": ["F-001"],
                                    "data_source": "research/evidence/results/results-manifest.jsonl"}])
    assert _run(tmp_path).returncode == 0


def test_data_aware_complete_result_program_passes(tmp_path):
    common = {"renderer": "matplotlib", "source_of_truth": "measured_data", "fact_ids": ["F-001"], "data_source": "research/evidence/results/results-manifest.jsonl"}
    figures = [{"id": "main", **common, "claim_role": "main_comparison"},
               {"id": "abl", **common, "claim_role": "ablation"}]
    _base(tmp_path, "data_aware", figures)
    assert _run(tmp_path).returncode == 0


def test_proposal_rejects_result_figure(tmp_path):
    _base(tmp_path, "proposal", [{"id": "main", "renderer": "matplotlib", "source_of_truth": "measured_data",
                                  "claim_role": "main_comparison", "data_source": "x"}])
    result = _run(tmp_path)
    assert result.returncode == 1 and "cannot plan" in result.stdout
