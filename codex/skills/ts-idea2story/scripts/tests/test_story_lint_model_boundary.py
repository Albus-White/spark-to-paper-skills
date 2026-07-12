from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "story_lint.py"


def test_protocol_numbers_are_semantic_warnings_not_fabrication_failures(tmp_path):
    story = {
        "title": "A Registered Materials Study",
        "abstract": "We plan a 95% interval and three temperatures.",
        "problem_framing": "Conductivity varies under aging.",
        "gap_pattern": "The bounded condition is understudied.",
        "solution": "A registered comparison with calibrated instruments.",
        "method_skeleton": "Measure matched samples and compare uncertainty.",
        "innovation_claims": ["A condition-specific empirical characterization"],
        "experiments_plan": "Use 3 temperatures and a threshold of 10^-3.",
        "benchmark_queries": ["composite electrolyte aging benchmark"],
        "research_hypothesis": {
            "problem": "aging", "hypothesis": "conductivity changes", "proposed_mechanism": "ion mobility",
            "scope": "registered temperatures", "assumptions": ["calibration"], "falsifiers": ["no change"],
            "alternative_explanations": ["sensor drift"], "minimum_validation_path": "matched measurements",
        },
    }
    (tmp_path / "story.json").write_text(json.dumps(story), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    report = json.loads(result.stdout)
    assert result.returncode == 0
    assert any("contains numbers" in warning for warning in report["warnings"])
