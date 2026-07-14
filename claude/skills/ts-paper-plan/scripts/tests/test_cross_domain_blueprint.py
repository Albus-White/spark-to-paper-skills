from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "blueprint_lint.py"


def _canonical_contracts(tmp_path, figures=None, sourced=True, user_requirements=None, section_ids=None):
    figures = figures or []
    section_ids = section_ids or ["body"]
    source = {"url": "https://example.org/accepted"} if sourced else {}
    (tmp_path / "accepted.pdf").write_bytes(b"fixture")
    (tmp_path / "venue-profile.json").write_text(json.dumps({
        "papers": [{"title": "Accepted paper", "source": source,
                    "pdf": {"path": "accepted.pdf", "sha256": "a" * 64},
                    "metrics": {"page_count": 8, "unique_cited_references": 40,
                                "total_figures": len(figures),
                                "table_count": 0, "evaluation_count": 1,
                                "figure_roles": {"planned roles": len(figures)},
                                "evaluation_kinds": {"domain evaluation": 1},
                                "evidence_dimensions": {"conditions": 1},
                                "evaluation_difficulty": {"rating": "moderate", "drivers": ["fixture"], "rationale": "fixture"}}}],
        "aggregates": {"means": {}, "evidence_dimension_means": {"datasets": 1}},
        "sample_sufficiency": {"verdict": "SUFFICIENT"},
    }), encoding="utf-8")
    (tmp_path / "publication-contract.json").write_text(json.dumps({
        "targets": {"page_range": [7, 9], "minimum_unique_cited_references": 12,
                    "figure_count": len(figures), "table_count": 0}, "figure_plan": figures,
        "table_plan": [], "section_plan": [{"section_id": item} for item in section_ids], "claim_ids": ["C-001"],
        "user_requirements": user_requirements or {},
    }), encoding="utf-8")


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
    _canonical_contracts(tmp_path, section_ids=["introduction", "materials_methods", "outcomes"])
    (tmp_path / "blueprint.json").write_text(json.dumps({
        "paper_title": "Thermal Aging of a Composite Electrolyte",
        "venue_profile": "venue-profile.json", "publication_contract": "publication-contract.json",
        "section_order": ["introduction", "materials_methods", "outcomes"],
        "sections": {
            "introduction": {"title": "Introduction", "roles": ["context"], "citation_types": ["CONTEXT"]},
            "materials_methods": {"title": "Materials and Methods", "roles": ["methodology"], "citation_types": ["CORE"]},
            "outcomes": {"title": "Electrochemical Outcomes", "roles": ["results"], "citation_types": ["METRIC"]},
        },
    }), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_publication_contract_preserves_explicit_user_artifact_requirements(tmp_path):
    (tmp_path / "main.tex.tmpl").write_text("@@title@@ @@abstract@@ @@sections@@", encoding="utf-8")
    (tmp_path / "template.json").write_text(json.dumps({
        "name": "target-venue", "sections": [], "citations": {"types": []}, "results_mode": "proposal",
    }), encoding="utf-8")
    requirements = {"figure_count": 4, "table_count": 2, "source": "USER_PROVIDED"}
    _canonical_contracts(tmp_path, user_requirements=requirements)
    (tmp_path / "blueprint.json").write_text(json.dumps({
        "paper_title": "Venue Grounded Proposal", "venue_profile": "venue-profile.json",
        "publication_contract": "publication-contract.json",
        "section_order": ["body"], "sections": {"body": {"title": "Study", "roles": ["methods"]}},
    }), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path), "--fix"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((tmp_path / "publication-contract.json").read_text())["user_requirements"] == requirements


def test_venue_profile_rejects_unsourced_accepted_paper(tmp_path):
    (tmp_path / "template.json").write_text(json.dumps({
        "name": "target-venue", "sections": [], "citations": {"types": []}, "results_mode": "proposal",
    }), encoding="utf-8")
    _canonical_contracts(tmp_path, sourced=False)
    (tmp_path / "blueprint.json").write_text(json.dumps({
        "paper_title": "Proposal", "venue_profile": "venue-profile.json",
        "publication_contract": "publication-contract.json",
        "section_order": ["body"], "sections": {"body": {"title": "Study", "roles": ["methods"]}},
    }), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "needs url, doi, or official_path" in result.stdout
