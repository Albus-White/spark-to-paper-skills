from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "draft_lint.py"


def test_unicode_and_protocol_numbers_are_not_misclassified_as_results(tmp_path):
    (tmp_path / "sections").mkdir()
    (tmp_path / "template.json").write_text(json.dumps({"results_mode": "proposal"}), encoding="utf-8")
    (tmp_path / "blueprint.json").write_text(json.dumps({
        "section_order": ["protocol"],
        "sections": {"protocol": {"title": "Protocol", "roles": ["methodology"]}},
    }), encoding="utf-8")
    (tmp_path / "sections/abstract.tex").write_text("这是一个预注册研究方案。", encoding="utf-8")
    (tmp_path / "sections/protocol.tex").write_text(
        "We plan 3 seeds, a 95\\% confidence interval, and a threshold of $10^{-3}$. 中文术语保持原义。",
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

