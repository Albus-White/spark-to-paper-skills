#!/usr/bin/env python3
"""Run and record a bounded DrawAI availability preflight."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


SECRET_PATTERNS = (
    re.compile(r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|PASSWORD|SECRET))=([^\s]+)"),
    re.compile(r"\b(?:sk|ghp|github_pat)-?[A-Za-z0-9_\-]{20,}\b"),
)


def redact(value: str) -> str:
    value = SECRET_PATTERNS[0].sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    return SECRET_PATTERNS[1].sub("[REDACTED_TOKEN]", value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--attempted-configuration", required=True)
    parser.add_argument("--reviewer", default="main-model")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a real DrawAI preflight command is required after --")
    root = Path(args.pipeline).resolve() / "drawai"
    root.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout, check=False)
        returncode = result.returncode
        stdout = redact(result.stdout[-8000:])
        stderr = redact(result.stderr[-8000:])
        timed_out = False
    except (OSError, subprocess.TimeoutExpired) as exc:
        returncode = 124 if isinstance(exc, subprocess.TimeoutExpired) else 127
        stdout = ""
        stderr = redact(str(exc))
        timed_out = isinstance(exc, subprocess.TimeoutExpired)
    available = returncode == 0
    record = {
        "status": "AVAILABLE" if available else "UNAVAILABLE",
        "preflight_command": [redact(item) for item in command],
        "attempted_configuration": args.attempted_configuration,
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout_tail": stdout,
        "observed_error": stderr or ("none" if available else "preflight returned nonzero without stderr"),
        "rationale": "DrawAI is required when this preflight succeeds; only a failed bounded preflight permits skipping it.",
        "reviewer": args.reviewer,
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    destination = root / ("preflight.json" if available else "unavailable.json")
    destination.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": available, "status": record["status"], "record": str(destination)}, ensure_ascii=False, indent=2))
    return 0 if available else 1


if __name__ == "__main__":
    raise SystemExit(main())
