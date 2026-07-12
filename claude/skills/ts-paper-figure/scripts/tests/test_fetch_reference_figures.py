import importlib.util
import json
import pathlib
import subprocess
import sys


SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("frf", SCRIPTS / "fetch_reference_figures.py")
frf = importlib.util.module_from_spec(spec); spec.loader.exec_module(frf)


def test_arxiv_id_from_url():
    assert frf.arxiv_id("https://arxiv.org/abs/2103.00208") == "2103.00208"
    assert frf.arxiv_id("https://arxiv.org/abs/1810.08462v2") == "1810.08462"
    assert frf.arxiv_id("https://www.example.org/paper") is None


def test_ar5iv_html_url():
    assert frf.ar5iv_url("2103.00208") == "https://ar5iv.labs.arxiv.org/html/2103.00208"


def test_load_papers_preserves_model_selected_order(tmp_path):
    path = tmp_path / "papers.json"
    path.write_text(json.dumps([{"title": "Domain source"}, {"title": "Venue source"}]))
    assert [item["title"] for item in frf.load_papers(str(path))] == ["Domain source", "Venue source"]


def test_missing_candidate_input_does_not_claim_references_are_mandatory(tmp_path):
    result = subprocess.run([
        sys.executable, str(SCRIPTS / "fetch_reference_figures.py"),
        "--papers", str(tmp_path / "missing.json"), "--out-dir", str(tmp_path / "refs"),
        "--label", "domain-figure", "--max-papers", "2", "--max-figures-per-paper", "2",
    ], capture_output=True, text=True)
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["references_optional"] is True
