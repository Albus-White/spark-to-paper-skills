from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
BIB = """@article{one,
  author = {A. Author},
  title = {One Relevant Primary Study},
  journal = {Example Journal},
  year = {2025},
  doi = {10.1000/example}
}
"""


def test_prewrite_bibliography_has_no_count_floor_and_postwrite_usage_is_separate(tmp_path):
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    pre = subprocess.run([sys.executable, str(SCRIPTS / "bib_integrity_lint.py"), str(tmp_path)], capture_output=True, text=True)
    assert pre.returncode == 0, pre.stdout + pre.stderr
    (tmp_path / "sections").mkdir()
    (tmp_path / "sections/introduction.tex").write_text("A self-contained protocol description.", encoding="utf-8")
    post = subprocess.run([sys.executable, str(SCRIPTS / "citations_lint.py"), str(tmp_path)], capture_output=True, text=True)
    report = json.loads(post.stdout)
    assert post.returncode == 0
    assert report["n_entries"] == 1
    assert any(item["rule"] == "no_citations_in_current_draft" for item in report["warnings"])

