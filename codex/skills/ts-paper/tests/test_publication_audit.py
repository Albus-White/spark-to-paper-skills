from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/publication_audit.py"
spec = importlib.util.spec_from_file_location("publication_audit", SCRIPT)
audit_module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(audit_module)


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path: Path):
    contract_id = "publication-contract-v-001"
    write(tmp_path / "research/research_state.json", {"active": {"publication_contract_id": contract_id}})
    planned = {"figure_id": "overview", "class": "explanatory_synthesis", "route": "PAPERBANANA_REQUIRED",
               "drawai_policy": "USE_IF_AVAILABLE_AFTER_RASTER_APPROVAL", "purpose": "explain method",
               "source_of_truth": "frozen method semantics", "claim_ids": ["C-001"], "section_role": "method"}
    write(tmp_path / f"research/contracts/{contract_id}.json", {
        "section_plan": [{"section_id": "method"}], "table_plan": [],
        "figure_plan": [planned],
        "targets": {"figure_count": 1, "table_count": 0},
    })
    write(tmp_path / "blueprint.json", {"sections": {"method": {"figures": [planned], "tables": []}}})
    route = {**planned, "drawai_status": "UNAVAILABLE_EVIDENCED_SKIP", "drawai_preflight": "reports/drawai.json"}
    write(tmp_path / "research/manuscript/figure-routing.json", {"figures": [route]})
    write(tmp_path / "figures/figures.manifest.json", {"figures": [{**route, "label": "overview"}]})
    (tmp_path / "sections").mkdir(); (tmp_path / "sections/method.tex").write_text("\\begin{figure}\\label{fig:overview}\\end{figure}")
    (tmp_path / "main.tex").write_text("\\input{sections/method}")


def test_publication_audit_accepts_exact_contract_sets_and_evidenced_drawai_skip(tmp_path):
    fixture(tmp_path)
    report = audit_module.audit(tmp_path)
    assert report["ok"], report["issues"]


def test_publication_audit_rejects_missing_latex_figure(tmp_path):
    fixture(tmp_path)
    (tmp_path / "sections/method.tex").write_text("No figure here.")
    report = audit_module.audit(tmp_path)
    assert not report["ok"]
    assert any("figure ID set mismatch for latex" in issue for issue in report["issues"])


def test_publication_audit_rejects_drawai_status_drift(tmp_path):
    fixture(tmp_path)
    manifest = json.loads((tmp_path / "figures/figures.manifest.json").read_text())
    manifest["figures"][0]["drawai_status"] = "AVAILABLE_REQUIRED"
    write(tmp_path / "figures/figures.manifest.json", manifest)
    report = audit_module.audit(tmp_path)
    assert not report["ok"]
    assert any("DrawAI status differs" in issue for issue in report["issues"])


def test_publication_audit_rejects_unincluded_section(tmp_path):
    fixture(tmp_path)
    (tmp_path / "main.tex").write_text("No section input.")
    report = audit_module.audit(tmp_path)
    assert not report["ok"]
    assert any("section ID set mismatch for main.tex includes" in issue for issue in report["issues"])


def test_publication_audit_rejects_blueprint_with_too_few_figures(tmp_path):
    fixture(tmp_path)
    write(tmp_path / "blueprint.json", {"sections": {"method": {"figures": [], "tables": []}}})
    report = audit_module.audit(tmp_path)
    assert not report["ok"]
    assert any("figure ID set mismatch for blueprint" in issue for issue in report["issues"])


def test_civil_regression_late_figure_addition_cannot_bypass_frozen_program(tmp_path):
    fixture(tmp_path)
    manifest = json.loads((tmp_path / "figures/figures.manifest.json").read_text())
    manifest["figures"].append({
        **manifest["figures"][0],
        "figure_id": "late-padding-figure",
        "label": "late-padding-figure",
    })
    write(tmp_path / "figures/figures.manifest.json", manifest)
    report = audit_module.audit(tmp_path)
    assert not report["ok"]
    assert any("figure ID set mismatch for manifest" in issue for issue in report["issues"])
