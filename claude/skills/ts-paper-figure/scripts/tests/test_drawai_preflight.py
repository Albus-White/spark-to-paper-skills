from __future__ import annotations

import json
import pathlib
import subprocess
import sys


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "record_drawai_preflight.py"


def test_failed_drawai_preflight_records_evidenced_skip_and_redacts_secrets(tmp_path):
    pipeline = tmp_path / "figure.pipeline"
    result = subprocess.run([
        sys.executable, str(SCRIPT), "--pipeline", str(pipeline),
        "--attempted-configuration", "bundled DrawAI runtime", "--",
        sys.executable, "-c", "import sys; print('API_TOKEN=super-secret-token-value', file=sys.stderr); sys.exit(1)",
    ], capture_output=True, text=True)
    assert result.returncode == 1
    record = json.loads((pipeline / "drawai/unavailable.json").read_text())
    assert record["status"] == "UNAVAILABLE"
    assert "super-secret-token-value" not in json.dumps(record)
    assert "[REDACTED]" in record["observed_error"]


def test_passing_drawai_preflight_requires_drawai_tail(tmp_path):
    pipeline = tmp_path / "figure.pipeline"
    result = subprocess.run([
        sys.executable, str(SCRIPT), "--pipeline", str(pipeline),
        "--attempted-configuration", "fixture", "--", sys.executable, "-c", "pass",
    ], capture_output=True, text=True)
    assert result.returncode == 0
    record = json.loads((pipeline / "drawai/preflight.json").read_text())
    assert record["status"] == "AVAILABLE" and record["returncode"] == 0
