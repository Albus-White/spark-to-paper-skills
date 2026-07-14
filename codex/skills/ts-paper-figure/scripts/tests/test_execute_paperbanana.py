from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import sys
from pathlib import Path

from PIL import Image


SCRIPT = Path(__file__).parents[1] / "execute_paperbanana.py"
spec = importlib.util.spec_from_file_location("execute_paperbanana", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def image_b64():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 40), (40, 90, 140)).save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_runtime_uses_selected_field_references_without_copying_credentials(tmp_path):
    pipeline = tmp_path / "figure.pipeline"
    reference = pipeline / "references/ref.png"; reference.parent.mkdir(parents=True); Image.new("RGB", (64, 40)).save(reference)
    write(pipeline / "references/retrieval.json", {
        "attempted_sources": ["official venue"],
        "candidates": [{"reference_id": "R1", "source": {"url": "https://example.org"}, "image": "references/ref.png",
                        "reason_selected": "matching purpose", "content": "method", "visual_intent": "overview"}],
        "decision": {"status": "SELECTED", "selected_reference_ids": ["R1"]},
    })
    style = pipeline / "paperbanana/style.md"; style.parent.mkdir(parents=True); style.write_text("style")
    runtime, references = module.prepare_runtime(pipeline, tmp_path, {"style_guide": "paperbanana/style.md"})
    assert len(references) == 1
    assert (runtime / "data/PaperBananaBench/diagram/ref.json").is_file()
    assert not (runtime / "configs/model_config.yaml").exists()


def test_candidate_trace_requires_all_real_paperbanana_stages(tmp_path):
    result = {
        "top10_references": [], "target_diagram_desc0": "plan", "target_diagram_stylist_desc0": "style",
        "target_diagram_stylist_desc0_base64_jpg": image_b64(),
        "target_diagram_critic_suggestions0": "No changes needed.", "target_diagram_critic_desc0": "style",
        "eval_image_field": "target_diagram_stylist_desc0_base64_jpg",
    }
    trace = module.trace_candidate(result, "pb-001", tmp_path)
    assert all(trace["stages"][stage]["ran"] for stage in module.STAGE_KEYS)
    result.pop("target_diagram_critic_suggestions0")
    try:
        module.trace_candidate(result, "pb-002", tmp_path / "missing")
    except ValueError as exc:
        assert "critic" in str(exc)
    else:
        raise AssertionError("missing upstream Critic trace was accepted")


def test_execution_input_must_bind_reviewed_semantics_and_frozen_caption(tmp_path):
    pipeline = tmp_path / "figure.pipeline"
    write(pipeline / "search_plan.json", {"planned_candidates": 1, "safety_cap": 1})
    write(pipeline / "figure_contract.json", {"caption": "Frozen caption"})
    semantic = pipeline / "paperbanana/semantic_plan.json"
    retrieval = pipeline / "references/retrieval.json"
    write(semantic, {"plan": "reviewed"})
    write(retrieval, {"decision": {"status": "NO_SUITABLE_REFERENCE"}})
    style = pipeline / "paperbanana/style.md"
    style.write_text("style", encoding="utf-8")
    payload = {
        "content": "domain-specific semantic content", "content_derivation": "from reviewed plan",
        "caption": "Frozen caption", "candidate_count": 1, "max_critic_rounds": 2,
        "main_model_name": "fixture", "image_gen_model_name": "fixture-image",
        "style_guide": "paperbanana/style.md", "semantic_plan_sha256": module.sha256(semantic),
        "retrieval_sha256": module.sha256(retrieval),
    }
    module.validate_input(pipeline, payload)
    payload["semantic_plan_sha256"] = "0" * 64
    try:
        module.validate_input(pipeline, payload)
    except ValueError as exc:
        assert "reviewed semantic plan" in str(exc)
    else:
        raise AssertionError("stale PaperBanana semantic input was accepted")


def test_choose_python_preserves_virtualenv_launcher_path(tmp_path):
    launcher = tmp_path / ".venv/bin/python"
    launcher.parent.mkdir(parents=True)
    launcher.symlink_to(Path(sys.executable))
    selected = module.choose_python(tmp_path, None)
    assert selected == launcher.absolute()
    assert ".venv/bin/python" in selected.as_posix()


def test_provider_preflight_matches_upstream_text_and_image_routing():
    module.validate_provider_routing("gpt-5", "gpt-image-1", {"OpenAI"})
    module.validate_provider_routing(
        "openrouter/google/gemini-3.1-pro-preview",
        "google/gemini-3.1-flash-image-preview",
        {"OpenRouter"},
    )
    try:
        module.validate_provider_routing("gpt-5", "gpt-image-1", {"Gemini"})
    except ValueError as exc:
        assert "OpenAI provider" in str(exc)
    else:
        raise AssertionError("incompatible PaperBanana provider configuration was accepted")


def test_workspace_dotenv_is_discovered_without_overriding_exported_values(tmp_path, monkeypatch):
    workspace = tmp_path / "research/run"
    workspace.mkdir(parents=True)
    (tmp_path / ".env").write_text("PB_TEST_WORKSPACE_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("PB_TEST_WORKSPACE_KEY", "exported")
    previous = Path.cwd()
    try:
        os.chdir(workspace)
        loaded = module._dotenv.load_unified_env()
    finally:
        os.chdir(previous)
    assert loaded == str(tmp_path / ".env")
    assert os.environ["PB_TEST_WORKSPACE_KEY"] == "exported"
