#!/usr/bin/env python3
"""Check lifecycle-critical Codex/Claude resources for unintended drift."""
from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
CODEX = ROOT / "codex" / "skills"
CLAUDE = ROOT / "claude" / "skills"

SHARED_TREES = sorted(path.name for path in CODEX.glob("ts-*") if path.is_dir())


def digest(path: Path) -> bytes:
    return hashlib.sha256(path.read_bytes()).digest()


def files_under(base: Path, rel: str) -> dict[str, Path]:
    root = base / rel
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and "agents" not in path.parts
        and path.suffix != ".pyc"
    }


errors: list[str] = []
for tree in SHARED_TREES:
    codex_files = files_under(CODEX, tree)
    claude_files = files_under(CLAUDE, tree)
    if set(codex_files) != set(claude_files):
        errors.append(
            f"{tree} resource set differs: codex-only={sorted(set(codex_files)-set(claude_files))}, "
            f"claude-only={sorted(set(claude_files)-set(codex_files))}"
        )
    for rel in sorted(set(codex_files) & set(claude_files)):
        if digest(codex_files[rel]) != digest(claude_files[rel]):
            errors.append(f"{tree}/{rel} differs")

if errors:
    print("\n".join(errors))
    sys.exit(1)
print("Lifecycle-critical Codex/Claude resources are byte-identical.")
