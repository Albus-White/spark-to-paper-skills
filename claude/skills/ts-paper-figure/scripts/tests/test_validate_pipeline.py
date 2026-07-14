import importlib.util
import json
import pathlib


GATE_TEST = pathlib.Path(__file__).with_name("test_figure_gate.py")
helper_spec = importlib.util.spec_from_file_location("gate_helper", GATE_TEST)
helper = importlib.util.module_from_spec(helper_spec); helper_spec.loader.exec_module(helper)
SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "validate_pipeline.py"
spec = importlib.util.spec_from_file_location("validator", SCRIPT)
validator = importlib.util.module_from_spec(spec); spec.loader.exec_module(validator)


def test_real_upstream_single_candidate_pipeline_passes(tmp_path):
    report = validator.validate_pipeline(helper._valid_paperbanana_pipeline(tmp_path, planned=1))
    assert report["ok"], report["errors"]
    assert report["candidate_count"] == 1


def test_real_upstream_multi_candidate_pipeline_passes(tmp_path):
    report = validator.validate_pipeline(helper._valid_paperbanana_pipeline(tmp_path, planned=3))
    assert report["ok"], report["errors"]
    assert report["candidate_count"] == 3


def test_declared_candidate_budget_must_be_satisfied(tmp_path):
    root = helper._valid_paperbanana_pipeline(tmp_path, planned=2)
    manifest = root / "renders/render_manifest.json"
    payload = json.loads(manifest.read_text()); payload["results"].pop(); manifest.write_text(json.dumps(payload))
    report = validator.validate_pipeline(root)
    assert not report["ok"] and any("requested 2" in item for item in report["errors"])


def test_final_review_must_be_hash_bound_and_fresh(tmp_path):
    root = helper._valid_paperbanana_pipeline(tmp_path, planned=1)
    review = root / "critique/final_vision_review.json"
    payload = json.loads(review.read_text()); payload["artifact_sha256"] = "0" * 64; payload["reviewer"]["independent_from_generation"] = False
    review.write_text(json.dumps(payload))
    report = validator.validate_pipeline(root)
    assert not report["ok"]
    assert any("bound" in item or "independent" in item for item in report["errors"])


def test_manual_stage_claim_cannot_replace_upstream_execution_record(tmp_path):
    root = helper._valid_paperbanana_pipeline(tmp_path, planned=1)
    run = root / "paperbanana/run.json"
    payload = json.loads(run.read_text()); payload["executor"] = "manual_json"; run.write_text(json.dumps(payload))
    report = validator.validate_pipeline(root)
    assert not report["ok"] and any("upstream PaperVizProcessor" in item for item in report["errors"])


def test_civil_regression_direct_image_candidates_cannot_be_relabelled_as_paperbanana(tmp_path):
    root = helper._valid_paperbanana_pipeline(tmp_path, planned=2)
    run = root / "paperbanana/run.json"
    payload = json.loads(run.read_text())
    payload["executor"] = "direct_image_model_candidate_renderer"
    payload["stages"] = ["retriever", "planner", "stylist", "visualizer", "critic"]
    run.write_text(json.dumps(payload))
    report = validator.validate_pipeline(root)
    assert not report["ok"]
    assert any("upstream PaperVizProcessor" in item for item in report["errors"])


def test_civil_regression_visual_precedent_search_cannot_be_skipped(tmp_path):
    root = helper._valid_paperbanana_pipeline(tmp_path, planned=1)
    retrieval = root / "references/retrieval.json"
    payload = json.loads(retrieval.read_text())
    payload["attempted_sources"] = []
    retrieval.write_text(json.dumps(payload))
    report = validator.validate_pipeline(root)
    assert not report["ok"]
    assert any("attempted_sources" in item for item in report["errors"])


def test_every_upstream_candidate_requires_all_five_stage_traces(tmp_path):
    root = helper._valid_paperbanana_pipeline(tmp_path, planned=1)
    run = root / "paperbanana/run.json"
    payload = json.loads(run.read_text()); payload["candidates"][0]["stages"]["critic"]["ran"] = False; run.write_text(json.dumps(payload))
    report = validator.validate_pipeline(root)
    assert not report["ok"] and any("stage trace" in item for item in report["errors"])


def test_critic_rejects_generic_box_flowchart(tmp_path):
    root = helper._valid_paperbanana_pipeline(tmp_path, planned=1)
    review = root / "critique/final_vision_review.json"
    payload = json.loads(review.read_text()); payload["generic_box_flowchart_diagnosis"]["detected"] = True; review.write_text(json.dumps(payload))
    report = validator.validate_pipeline(root)
    assert not report["ok"] and any("generic box-flowchart" in item for item in report["errors"])
