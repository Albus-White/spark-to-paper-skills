import importlib.util
import json
import pathlib
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pool", SCRIPTS / "prepare_reference_pool.py")
pool = importlib.util.module_from_spec(spec); spec.loader.exec_module(pool)


def test_prefilter_prefers_matching_visual_intent_and_domain():
    query = {"figure_type": "architecture", "visual_intent": "dual stream architecture overview",
             "domain": "remote sensing", "content": "change detection encoder fusion"}
    matching = {"visual_intent": "overall network architecture", "content": "remote sensing change detection fusion"}
    conflict = {"visual_intent": "accuracy bar plot", "content": "remote sensing change detection"}
    matching_score, _ = pool.score_item(matching, query)
    conflict_score, _ = pool.score_item(conflict, query)
    assert matching_score > conflict_score


def test_model_selected_reference_inspection_budget_is_respected(tmp_path):
    ref = tmp_path / "ref.json"
    ref.write_text(json.dumps([{"id": f"r{i}", "content": f"method {i}",
                                "visual_intent": "architecture", "path_to_gt_image": f"images/{i}.png"}
                               for i in range(250)]))
    query = tmp_path / "query.json"; query.write_text(json.dumps({"figure_type": "architecture"}))
    out = tmp_path / "pool.json"
    result = subprocess.run([sys.executable, str(SCRIPTS / "prepare_reference_pool.py"),
                             "--query", str(query), "--ref-json", str(ref), "--limit", "250",
                             "--out", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0
    payload = json.loads(out.read_text())
    assert payload["schema"] == "ts.figure.reference_pool.v1"
    assert len(payload["candidate_pool"]) == 250
