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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _image(path, colour=(60, 110, 150)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 700), colour).save(path)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_paperbanana_pipeline(workdir, label="overview", planned=2):
    root = workdir / "figures" / f"{label}.pipeline"
    _write_json(root / "figure_contract.json", {
        "figure_id": label, "figure_class": "explanatory_synthesis", "route": "PAPERBANANA_REQUIRED",
        "drawai_status": "UNAVAILABLE_EVIDENCED_SKIP", "semantic_type": "method_overview",
        "source_of_truth": "research program", "renderer": "paperbanana",
        "renderer_rationale": "The figure synthesizes several relations into one explanatory view.",
        "caption": "Method overview", "required_content": ["A", "B"], "forbidden_content": ["invented result"],
    })
    _write_json(root / "search_plan.json", {
        "strategy": "direct" if planned == 1 else "candidate_search", "planned_candidates": planned,
        "safety_cap": planned, "resource_basis": "frozen resource plan", "rationale": "resolve layout uncertainty",
        "stop_conditions": ["faithful readable image exists"],
        "reference_strategy": {"search_required": True, "selection_required": False, "rationale": "inspect field precedent"},
    })
    _write_json(root / "references/retrieval.json", {
        "search_queries": ["accepted domain method overview figure"], "attempted_sources": ["official venue papers"],
        "candidates": [],
        "decision": {"status": "NO_SUITABLE_REFERENCE", "selected_reference_ids": [], "rationale": "fixture has no external image", "rejection_summary": "synthetic fixture", "reviewer": "fixture"},
    })
    retrieval_hash = _hash(root / "references/retrieval.json")
    semantic_path = root / "paperbanana/semantic_plan.json"
    _write_json(semantic_path, {
        "figure_id": label, "communication_goal": "Explain the dependency", "visual_story": "Concrete A transforms into B",
        "visual_blueprint": ["domain A", "transformation", "domain B"], "semantic_edges": ["A -> B"],
        "concrete_visual_elements": ["domain A", "transformation surface", "domain B"],
        "field_visual_conventions": ["accepted-paper hierarchy"], "anti_generic_strategy": "depict domain objects",
        "text_strategy": "short labels", "required_content": ["A", "B"], "forbidden_content": ["invented result"],
        "reference_decision": "NO_SUITABLE_REFERENCE", "retrieval_sha256": retrieval_hash,
        "minimalism_decision": "RICH_DOMAIN_SPECIFIC",
    })
    style = root / "paperbanana/style_guide.md"; style.parent.mkdir(parents=True, exist_ok=True); style.write_text("Field-specific style.\n")
    run_input = root / "paperbanana/input.json"
    _write_json(run_input, {"content": "A transforms into B.", "content_derivation": "faithful rendering of the reviewed semantic plan",
                            "caption": "Method overview", "candidate_count": planned,
                            "max_critic_rounds": 2, "main_model_name": "fixture-main", "image_gen_model_name": "fixture-image",
                            "style_guide": "paperbanana/style_guide.md", "semantic_plan_sha256": _hash(semantic_path),
                            "retrieval_sha256": retrieval_hash})
    worker = root / "paperbanana/worker-report.json"; _write_json(worker, {"fixture": True})
    results = []
    candidates = []
    for index in range(planned):
        candidate_id = f"pb-{index + 1:03d}"
        image = root / "renders" / candidate_id / "final.png"; _image(image, (60 + index * 30, 100, 150))
        relative = image.relative_to(root).as_posix()
        results.append({"id": candidate_id, "ok": True, "output": relative, "sha256": _hash(image), "producer": "PaperBanana"})
        candidates.append({
            "candidate_id": candidate_id,
            "stages": {stage: {"ran": True} for stage in ("retriever", "planner", "stylist", "visualizer", "critic")},
            "final_image": relative, "final_sha256": _hash(image), "selected_upstream_key": "target_diagram_critic_desc0_base64_jpg",
        })
    _write_json(root / "renders/render_manifest.json", {"results": results})
    final = root / results[0]["output"]
    selection = {
        "selected_candidate_id": results[0]["id"], "compared_candidates": [item["id"] for item in results],
        "rationale": "first candidate best preserves the method", "final_image": results[0]["output"], "final_sha256": _hash(final),
    }
    if planned > 1:
        selection["quality_comparison"] = {"semantic_fidelity": "all checked", "visual_specificity": "first is concrete",
                                           "information_hierarchy": "first is clearer", "reference_alignment": "no suitable reference",
                                           "why_selected": "best actual image"}
    _write_json(root / "selection.json", selection)
    _write_json(root / "paperbanana/run.json", {
        "workflow": "PaperBanana", "executor": "upstream_papervizprocessor_adapter",
        "upstream": {"root": "/fixture/PaperBanana", "origin": "https://example.org/PaperBanana", "commit": "a" * 40, "dirty": False, "dirty_status_sha256": None},
        "returncode": 0, "stages": ["retriever", "planner", "stylist", "visualizer", "critic"],
        "input": {"path": "paperbanana/input.json", "sha256": _hash(run_input)},
        "semantic_plan": {"path": "paperbanana/semantic_plan.json", "sha256": _hash(semantic_path)},
        "reference_search": {"path": "references/retrieval.json", "sha256": retrieval_hash},
        "style_guide": {"path": "paperbanana/style_guide.md", "sha256": _hash(style)},
        "worker_report": {"path": "paperbanana/worker-report.json", "sha256": _hash(worker)},
        "candidate_count": planned, "candidates": candidates,
    })
    _write_json(root / "critique/final_vision_review.json", {
        "artifact_sha256": _hash(final),
        "reviewer": {"id": "fresh-vision-review", "actual_image_review": True, "independent_from_generation": True,
                     "context_artifacts": [results[0]["output"], "paperbanana/semantic_plan.json"]},
        "checks": [{"question": "faithful?", "verdict": "PASS", "rationale": "visible A to B"}],
        "dimensions": {name: {"verdict": "PASS", "rationale": "passes", "visual_evidence": "visible domain objects"}
                       for name in ("semantic_fidelity", "visual_specificity", "information_hierarchy", "field_convention_alignment", "anti_genericness", "legibility", "integrity")},
        "generic_box_flowchart_diagnosis": {"detected": False, "rationale": "uses domain depictions", "visual_evidence": "A and B are concrete"},
        "publication_readiness": "PASS", "blocking_issues": [],
    })
    _write_json(root / "drawai/unavailable.json", {"status": "UNAVAILABLE", "preflight_command": ["drawai", "--check"],
                "observed_error": "runtime unavailable", "attempted_configuration": "preflight", "rationale": "not configured", "reviewer": "fixture"})
    return root


def _native_manifest(workdir, label="structure", figure_class="exact_structure", route="DOMAIN_NATIVE", source="registered geometry", fact_ids=None):
    artifact = workdir / "figures" / f"{label}.pdf"; artifact.parent.mkdir(parents=True, exist_ok=True); artifact.write_bytes(b"%PDF fixture")
    review = workdir / "figures" / f"{label}.review.json"
    _write_json(review, {"artifact_sha256": _hash(artifact), "reviewer": {"actual_image_review": True}, "blocking_issues": []})
    entry = {"figure_id": label, "class": figure_class, "route": route, "source_of_truth": source,
             "renderer": "domain-tool", "published_vector": f"figures/{label}.pdf", "visual_review": f"figures/{label}.review.json"}
    if fact_ids is not None:
        entry["fact_ids"] = fact_ids
    _write_json(workdir / "figures/figures.manifest.json", {"figures": [entry]})


def _paperbanana_manifest(workdir, root, label="overview"):
    final = json.loads((root / "selection.json").read_text())["final_image"]
    published = workdir / "figures" / f"{label}.png"; shutil.copy2(root / final, published)
    _write_json(workdir / "figures/figures.manifest.json", {"figures": [{
        "figure_id": label, "class": "explanatory_synthesis", "route": "PAPERBANANA_REQUIRED",
        "source_of_truth": "research program", "renderer": "paperbanana", "pipeline_dir": root.relative_to(workdir).as_posix(),
        "published_raster": published.relative_to(workdir).as_posix(), "drawai_status": "UNAVAILABLE_EVIDENCED_SKIP",
    }]})


def test_figure_gate_accepts_domain_native_exact_structure(tmp_path):
    _native_manifest(tmp_path)
    assert rg.check_figure_critique(tmp_path) == []


def test_measured_figure_requires_known_fact_ids(tmp_path):
    _native_manifest(tmp_path, label="result", figure_class="measured_evidence", route="DETERMINISTIC_OR_ORIGINAL_EVIDENCE", source="canonical facts", fact_ids=[])
    assert any("fact_ids" in item for item in rg.check_figure_critique(tmp_path))
    _native_manifest(tmp_path, label="result", figure_class="measured_evidence", route="DETERMINISTIC_OR_ORIGINAL_EVIDENCE", source="canonical facts", fact_ids=["F-999"])
    facts = tmp_path / "research/evidence/results/results-manifest.jsonl"; facts.parent.mkdir(parents=True); facts.write_text(json.dumps({"fact_id": "F-001"}) + "\n")
    assert any("unknown canonical fact_ids" in item for item in rg.check_figure_critique(tmp_path))


def test_missing_manifest_uses_dynamic_contract_target(tmp_path):
    _write_json(tmp_path / "research/research_state.json", {"active": {"publication_contract_id": "publication-contract-v-001"}})
    _write_json(tmp_path / "research/contracts/publication-contract-v-001.json", {"targets": {"figure_count": 1}})
    assert any("requires 1 figures" in item for item in rg.check_figure_critique(tmp_path))


def test_paperbanana_route_passes_only_with_real_upstream_execution_record(tmp_path):
    root = _valid_paperbanana_pipeline(tmp_path, planned=1); _paperbanana_manifest(tmp_path, root)
    assert rg.check_figure_critique(tmp_path) == []
    (root / "paperbanana/run.json").unlink()
    assert any("PaperBanana" in item for item in rg.check_figure_critique(tmp_path))


def test_civil_regression_drawai_skip_cannot_authorize_replacement_schematic(tmp_path):
    root = _valid_paperbanana_pipeline(tmp_path, planned=1)
    _paperbanana_manifest(tmp_path, root)
    published = tmp_path / "figures/overview.png"
    Image.new("RGB", (64, 40), (180, 40, 40)).save(published)
    problems = rg.check_figure_critique(tmp_path)
    assert any("published raster differs from reviewed PaperBanana image" in item for item in problems)
