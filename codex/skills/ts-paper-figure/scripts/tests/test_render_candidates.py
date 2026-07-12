import importlib.util
import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("batch", SCRIPTS / "render_candidates.py")
batch = importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)


def test_adaptive_retry_and_resume(monkeypatch, tmp_path):
    source = tmp_path / "candidate_prompts.json"
    source.write_text(json.dumps({"candidates": [
        {"id": "c01", "composition_strategy": "a", "prompt": "one"},
        {"id": "c02", "composition_strategy": "b", "prompt": "two"},
        {"id": "c03", "composition_strategy": "c", "prompt": "three"},
    ]}))
    out = tmp_path / "renders"
    calls = {"c01": 0, "c02": 0, "c03": 0}

    def fake_render(prompt, output, retries, references, require_reference):
        candidate_id = output.stem
        calls[candidate_id] += 1
        if candidate_id == "c02" and calls[candidate_id] == 1:
            return {"ok": False, "error": "temporary timeout"}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes((candidate_id + prompt).encode())
        return {"ok": True, "path": "generations", "size": [1536, 1024]}

    monkeypatch.setattr(batch.gen_image, "render", fake_render)
    monkeypatch.setattr(sys, "argv", ["render_candidates.py", "--candidates", str(source),
                                      "--out-dir", str(out), "--max-workers", "3", "--safety-cap", "3",
                                      "--retries", "2", "--batch-retry-rounds", "2",
                                      "--batch-backoff", "0"])
    assert batch.main() == 0
    manifest = json.loads((out / "render_manifest.json").read_text())
    c02 = next(item for item in manifest["results"] if item["id"] == "c02")
    assert len(c02["attempt_history"]) == 2
    assert c02["attempt_history"][0]["batch_workers"] == 3
    assert c02["attempt_history"][1]["batch_workers"] == 1

    before = dict(calls)
    assert batch.main() == 0
    assert calls == before  # valid successful artifacts were resumed, not regenerated


def test_unbounded_candidate_retry_policy_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", [
        "render_candidates.py", "--candidates", str(tmp_path / "missing.json"),
        "--out-dir", str(tmp_path / "renders"), "--max-workers", "100", "--safety-cap", "1",
        "--retries", "99", "--batch-retry-rounds", "99", "--batch-backoff", "0",
    ])
    assert batch.main() == 2
