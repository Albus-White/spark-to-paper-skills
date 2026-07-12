#!/usr/bin/env python3
"""Static project audit: every Skill declares finite progress and every child process is bounded."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "codex" / "skills"
errors: list[str] = []

for skill_file in sorted(SKILLS.glob("*/SKILL.md")):
    text = skill_file.read_text(encoding="utf-8")
    if "bounded-execution-contract.md" not in text:
        errors.append(f"{skill_file.relative_to(ROOT)} lacks the project-wide bounded-execution contract")

for path in sorted(SKILLS.rglob("*.py")):
    relative = path.relative_to(ROOT).as_posix()
    if "ts-figure-optimize/engine/" in relative or "/tests/" in relative:
        continue
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        errors.append(f"{relative}: syntax error: {exc}")
        continue
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id == "subprocess":
                if node.func.attr in {"run", "call", "check_call", "check_output"}:
                    keywords = {item.arg for item in node.keywords if item.arg}
                    wrapper = relative.endswith("ts-figure-optimize/scripts/run_reconstruction.py")
                    if "timeout" not in keywords and not wrapper:
                        errors.append(f"{relative}:{node.lineno}: subprocess.{node.func.attr} lacks timeout")
                if node.func.attr == "Popen":
                    if not relative.endswith("ts-research-lifecycle/scripts/execution_backend.py"):
                        errors.append(f"{relative}:{node.lineno}: unmanaged subprocess.Popen")
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    errors.append(f"{relative}:{node.lineno}: shell=True bypasses bounded process control")
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            errors.append(f"{relative}:{node.lineno}: open-ended while True")

backend_source = (SKILLS / "ts-research-lifecycle/scripts/execution_backend.py").read_text(encoding="utf-8")
for required in ("communicate(timeout=timeout_seconds)", "os.killpg", "outcome_unknown"):
    if required not in backend_source:
        errors.append(f"execution_backend.py lacks process-control invariant: {required}")

wrapper_source = (SKILLS / "ts-figure-optimize/scripts/run_reconstruction.py").read_text(encoding="utf-8")
if "result = sh(cmd, cwd=str(cwd), timeout=timeout_seconds)" not in wrapper_source:
    errors.append("run_reconstruction subprocess wrapper no longer proves a timeout")

if errors:
    print("\n".join(errors))
    raise SystemExit(1)
print("All Skills declare bounded progress and all non-engine child processes are time-bounded.")
