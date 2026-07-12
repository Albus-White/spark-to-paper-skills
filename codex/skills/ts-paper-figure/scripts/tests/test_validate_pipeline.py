import importlib.util
import json
import pathlib

GATE_TEST = pathlib.Path(__file__).with_name("test_figure_gate.py")
helper_spec = importlib.util.spec_from_file_location("gate_helper", GATE_TEST)
helper = importlib.util.module_from_spec(helper_spec); helper_spec.loader.exec_module(helper)
SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "validate_pipeline.py"
spec = importlib.util.spec_from_file_location("validator", SCRIPT)
validator = importlib.util.module_from_spec(spec); spec.loader.exec_module(validator)


def test_direct_single_candidate_pipeline_passes(tmp_path):
    report = validator.validate_pipeline(helper._valid_pipeline(tmp_path, planned=1))
    assert report["ok"], report["errors"]
    assert report["candidate_count"] == 1


def test_model_selected_three_candidate_pipeline_passes(tmp_path):
    report = validator.validate_pipeline(helper._valid_pipeline(tmp_path, planned=3))
    assert report["ok"], report["errors"]
    assert report["candidate_count"] == 3


def test_declared_budget_must_be_satisfied(tmp_path):
    root = helper._valid_pipeline(tmp_path, planned=2)
    manifest = root / "renders/render_manifest.json"
    payload = json.loads(manifest.read_text()); payload["results"].pop(); manifest.write_text(json.dumps(payload))
    report = validator.validate_pipeline(root)
    assert not report["ok"] and any("requested 2" in item for item in report["errors"])


def test_final_review_must_be_hash_bound(tmp_path):
    root = helper._valid_pipeline(tmp_path, planned=1)
    review = root / "critique/final_vision_review.json"
    payload = json.loads(review.read_text()); payload["artifact_sha256"] = "0" * 64; review.write_text(json.dumps(payload))
    report = validator.validate_pipeline(root)
    assert not report["ok"] and any("hash-bound" in item for item in report["errors"])
