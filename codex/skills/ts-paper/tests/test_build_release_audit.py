from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/build_release_audit.py"
spec = importlib.util.spec_from_file_location("build_release_audit", SCRIPT)
builder = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(builder)


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_release_audit_builder_binds_current_contract_manuscript_and_exact_verdicts(tmp_path, monkeypatch):
    research = tmp_path / "research"
    contract_id = "publication-contract-v-001"; manuscript_id = "manuscript-v001"; judgment_id = "publication-judgment-v-001"
    write(research / "research_state.json", {"active": {"publication_contract_id": contract_id, "manuscript_id": manuscript_id,
          "publication_judgment_id": judgment_id}})
    write(research / f"contracts/{contract_id}.json", {"section_plan": [{"section_id": "body"}], "table_plan": [],
        "figure_plan": [], "targets": {
        "page_range": [7, 9], "minimum_unique_cited_references": 12,
        "figure_count": 0, "table_count": 0}})
    write(research / f"manuscript/{manuscript_id}.json", {"content_hash": "fixture"})
    contract_path = research / f"contracts/{contract_id}.json"
    manuscript_path = research / f"manuscript/{manuscript_id}.json"
    write(research / f"reports/manuscript/{judgment_id}.json", {
        "publication_contract_id": contract_id, "publication_contract_hash": builder.sha256(contract_path),
        "manuscript_id": manuscript_id, "manuscript_hash": builder.sha256(manuscript_path), "verdict": "PASS",
        "page_scale": {"actual_pages": 8, "target_range": [7, 9],
                       "verdict": "WITHIN_TARGET", "rationale": "fixture"},
    })
    write(research / "claims/claim-registry.json", {"claims": [{"claim_id": "C-001", "active": True, "support_status": "SUPPORTED"}]})
    pdf = research / f"manuscript/compiled/{manuscript_id}.pdf"; pdf.parent.mkdir(parents=True); pdf.write_bytes(b"pdf")
    write(research / "reports/manuscript/latex-verdict.json", {"compiled": True, "error_count": 0,
          "pdf": f"manuscript/compiled/{manuscript_id}.pdf", "pdf_sha256": builder.sha256(pdf), "page_count": 8})
    judgment_path = research / f"reports/manuscript/{judgment_id}.json"
    judgment = json.loads(judgment_path.read_text())
    judgment["rendered_pdf_review"] = {
        "pdf_sha256": builder.sha256(pdf), "actual_pdf_reviewed": True,
        "layout_findings": [], "blocking_issues": [],
    }
    write(judgment_path, judgment)
    write(research / "manuscript/figure-routing.json", {"figures": []})
    write(tmp_path / "blueprint.json", {"sections": {"body": {"figures": [], "tables": []}}})
    write(tmp_path / "figures/figures.manifest.json", {"figures": []})
    (tmp_path / "sections").mkdir(); (tmp_path / "sections/body.tex").write_text("body")
    (tmp_path / "main.tex").write_text("\\input{sections/body}")

    def fake_run_json(script, args):
        if script == builder.CITATIONS_LINT:
            return True, {"n_cited": 12, "required_unique_cited_references": 12}, ""
        return True, {"ok": True}, ""

    monkeypatch.setattr(builder, "run_json", fake_run_json)
    monkeypatch.setattr(builder, "check_figure_critique", lambda workdir: [])
    monkeypatch.setattr(builder.subprocess, "run", lambda *args, **kwargs: type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    payload, blockers = builder.build(tmp_path)
    assert blockers == []
    assert payload["publication_contract_id"] == contract_id
    assert payload["manuscript_id"] == manuscript_id
    assert payload["publication_judgment_id"] == judgment_id
    assert all(payload[key] == "PASS" for key in ("citation_verdict", "figure_verdict", "latex_verdict", "claim_verdict"))
