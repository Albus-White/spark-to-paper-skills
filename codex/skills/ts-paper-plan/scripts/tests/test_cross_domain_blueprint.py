from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "blueprint_lint.py"


def test_domain_specific_sections_are_not_forced_into_ml_names(tmp_path):
    (tmp_path / "main.tex.tmpl").write_text("@@title@@ @@abstract@@ @@sections@@", encoding="utf-8")
    (tmp_path / "template.json").write_text(json.dumps({
        "name": "domain-journal",
        "engine": {"documentclass": "article", "main_template": "main.tex.tmpl"},
        "sections": [{"id": "introduction", "required": True, "roles": ["context"]}],
        "abstract": {},
        "citations": {"style": "numeric", "types": ["CONTEXT", "CORE", "METRIC"]},
        "results_mode": "data_aware",
    }), encoding="utf-8")
    (tmp_path / "venue-study.json").write_text(json.dumps({
        "official_guidance": [],
        "representative_papers": [{"title": "Relevant materials paper", "url": "https://example.org/materials"}],
        "field_conventions": ["report calibrated specimen uncertainty"], "user_requirements": {},
        "design_decisions": {"sections": "materials-specific", "figures": "evidence-driven"},
        "limitations": [], "reviewer": {"id": "main-model"},
    }), encoding="utf-8")
    (tmp_path / "blueprint.json").write_text(json.dumps({
        "paper_title": "Thermal Aging of a Composite Electrolyte",
        "venue_study": "venue-study.json",
        "section_order": ["introduction", "materials_methods", "outcomes"],
        "sections": {
            "introduction": {"title": "Introduction", "roles": ["context"], "citation_types": ["CONTEXT"]},
            "materials_methods": {"title": "Materials and Methods", "roles": ["methodology"], "citation_types": ["CORE"]},
            "outcomes": {"title": "Electrochemical Outcomes", "roles": ["results"], "citation_types": ["METRIC"]},
        },
    }), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_venue_study_preserves_explicit_user_artifact_requirements(tmp_path):
    (tmp_path / "main.tex.tmpl").write_text("@@title@@ @@abstract@@ @@sections@@", encoding="utf-8")
    (tmp_path / "template.json").write_text(json.dumps({
        "name": "target-venue", "sections": [], "citations": {"types": []}, "results_mode": "proposal",
    }), encoding="utf-8")
    requirements = {"figure_count": 4, "table_count": 2, "source": "USER_PROVIDED"}
    (tmp_path / "venue-study.json").write_text(json.dumps({
        "official_guidance": [{"url": "https://venue.example/guidance", "observation": "format rule"}],
        "representative_papers": [{"title": "Accepted domain paper", "doi": "10.1000/example"}],
        "field_conventions": [], "user_requirements": requirements,
        "design_decisions": {"artifact_plan": "follow explicit counts when scientifically honest"},
        "limitations": [], "reviewer": {"id": "main-model"},
    }), encoding="utf-8")
    (tmp_path / "blueprint.json").write_text(json.dumps({
        "paper_title": "Venue Grounded Proposal", "venue_study": "venue-study.json",
        "section_order": ["body"], "sections": {"body": {"title": "Study", "roles": ["methods"]}},
    }), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path), "--fix"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((tmp_path / "venue-study.json").read_text())["user_requirements"] == requirements


def test_venue_study_rejects_unsourced_representative_paper(tmp_path):
    (tmp_path / "template.json").write_text(json.dumps({
        "name": "target-venue", "sections": [], "citations": {"types": []}, "results_mode": "proposal",
    }), encoding="utf-8")
    (tmp_path / "venue-study.json").write_text(json.dumps({
        "official_guidance": [], "representative_papers": [{"title": "Untraceable paper"}],
        "field_conventions": [], "user_requirements": {}, "design_decisions": {},
        "limitations": [], "reviewer": {"id": "main-model"},
    }), encoding="utf-8")
    (tmp_path / "blueprint.json").write_text(json.dumps({
        "paper_title": "Proposal", "venue_study": "venue-study.json",
        "section_order": ["body"], "sections": {"body": {"title": "Study", "roles": ["methods"]}},
    }), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "needs url, doi, or path" in result.stdout
