import hashlib
import importlib.util
import json
import pathlib
import shutil

from PIL import Image

RUN_GATES = pathlib.Path(__file__).resolve().parents[3] / "ts-paper" / "scripts" / "run_gates.py"
spec = importlib.util.spec_from_file_location("rg", RUN_GATES)
rg = importlib.util.module_from_spec(spec); spec.loader.exec_module(rg)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def _image(path, colour):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 700), colour).save(path)


def _valid_pipeline(workdir, label="arch", planned=2, renderer="graphviz", source="code_model"):
    root = workdir / "figures" / f"{label}.pipeline"
    _write_json(root / "figure_contract.json", {
        "figure_id": label, "semantic_type": "dependency_graph", "source_of_truth": source,
        "renderer": renderer, "renderer_rationale": "The renderer preserves exact graph semantics.",
        "caption": "Dependency graph", "required_content": ["A", "B"], "forbidden_content": ["invented edge"],
        **({"fact_ids": ["F-001"], "data_sources": ["data.json"]} if source == "measured_data" else {}),
    })
    if source == "measured_data":
        (root / "data.json").write_text("{}")
    _write_json(root / "search_plan.json", {
        "strategy": "direct" if planned == 1 else "candidate_search", "planned_candidates": planned,
        "safety_cap": planned, "resource_basis": "The user-confirmed figure allocation permits this render set.",
        "rationale": "Use the smallest budget that can resolve the layout uncertainty.",
        "stop_conditions": ["a faithful readable image exists"],
        "reference_strategy": {"required": False, "rationale": "The graph is defined by code, not visual precedent."},
    })
    renders = []
    for index in range(planned):
        candidate = root / "renders" / f"c{index + 1}.png"
        _image(candidate, (40 + index * 40, 90, 140))
        renders.append({"id": f"c{index + 1}", "ok": True, "output": f"renders/c{index + 1}.png", "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()})
    _write_json(root / "renders/render_manifest.json", {"results": renders})
    final = root / "final/final.png"; final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "renders/c1.png", final)
    _write_json(root / "selection.json", {
        "selected_candidate_id": "c1", "compared_candidates": [item["id"] for item in renders],
        "rationale": "c1 best preserves the declared graph.", "final_image": "final/final.png",
        "final_sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
    })
    _write_json(root / "critique/final_vision_review.json", {
        "artifact_sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
        "reviewer": {"id": "vision-review", "model_or_human": "main-model", "actual_image_review": True},
        "checks": [{"question": "Does the image preserve A to B?", "verdict": "PASS", "rationale": "The rendered edge and labels are visible."}],
        "blocking_issues": [],
    })
    shutil.copy2(final, workdir / "figures" / f"{label}.png")
    return root


def _manifest(workdir, label="arch", **updates):
    entry = {"label": label, "source_of_truth": "code_model", "renderer": "graphviz",
             "pipeline_dir": f"figures/{label}.pipeline", "published_raster": f"figures/{label}.png"}
    entry.update(updates)
    _write_json(workdir / "figures/figures.manifest.json", {"figures": [entry]})


def test_figure_gate_accepts_domain_native_renderer_and_adaptive_budget(tmp_path):
    _valid_pipeline(tmp_path, planned=1); _manifest(tmp_path)
    assert rg.check_figure_critique(tmp_path) == []


def test_figure_gate_rejects_self_report_without_pipeline(tmp_path):
    (tmp_path / "figures").mkdir(); _manifest(tmp_path)
    assert any("pipeline_dir" in item for item in rg.check_figure_critique(tmp_path))


def test_measured_figure_requires_fact_ids(tmp_path):
    _valid_pipeline(tmp_path, source="measured_data")
    _manifest(tmp_path, source_of_truth="measured_data")
    assert any("fact_ids" in item for item in rg.check_figure_critique(tmp_path))


def test_measured_figure_rejects_unknown_canonical_fact(tmp_path):
    _valid_pipeline(tmp_path, source="measured_data")
    _manifest(tmp_path, source_of_truth="measured_data", fact_ids=["F-999"])
    facts = tmp_path / "research/evidence/results/results-manifest.jsonl"
    facts.parent.mkdir(parents=True)
    facts.write_text(json.dumps({"fact_id": "F-001"}) + "\n")
    assert any("unknown canonical fact_ids" in item for item in rg.check_figure_critique(tmp_path))


def test_figure_gate_noop_without_manifest(tmp_path):
    assert rg.check_figure_critique(tmp_path) == []
