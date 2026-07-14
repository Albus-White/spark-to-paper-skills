from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
BIB = "\n".join(
    f"@article{{ref{i:03d},\n  author = {{A. Author}},\n  title = {{Relevant Study {i}}},\n  journal = {{Example Journal}},\n  year = {{2025}},\n  doi = {{10.1000/example{i}}}\n}}"
    for i in range(12)
)


def test_prewrite_integrity_is_separate_but_final_draft_enforces_contract_floor(tmp_path):
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    pre = subprocess.run([sys.executable, str(SCRIPTS / "bib_integrity_lint.py"), str(tmp_path)], capture_output=True, text=True)
    assert pre.returncode == 0, pre.stdout + pre.stderr
    research = tmp_path / "research"
    (research / "contracts").mkdir(parents=True)
    (research / "manuscript").mkdir()
    (research / "research_state.json").write_text(json.dumps({"active": {"publication_contract_id": "publication-contract-v-001"}}))
    (research / "contracts/publication-contract-v-001.json").write_text(json.dumps({"targets": {"minimum_unique_cited_references": 12}}))
    keys = [f"ref{i:03d}" for i in range(12)]
    (research / "manuscript/bibliography-coverage.json").write_text(json.dumps({"planned_citation_keys": keys}))
    (tmp_path / "sections").mkdir()
    (tmp_path / "sections/introduction.tex").write_text("A self-contained protocol description.", encoding="utf-8")
    post = subprocess.run([sys.executable, str(SCRIPTS / "citations_lint.py"), str(tmp_path)], capture_output=True, text=True)
    report = json.loads(post.stdout)
    assert post.returncode == 1
    assert report["n_entries"] == 12
    assert any(item["rule"] == "no_citations_in_current_draft" for item in report["warnings"])
    assert any(item["rule"] == "unique_cited_reference_floor" for item in report["issues"])
    (tmp_path / "sections/introduction.tex").write_text("Evidence~\\cite{" + ",".join(keys) + "}.", encoding="utf-8")
    final = subprocess.run([sys.executable, str(SCRIPTS / "citations_lint.py"), str(tmp_path)], capture_output=True, text=True)
    assert final.returncode == 0, final.stdout + final.stderr
