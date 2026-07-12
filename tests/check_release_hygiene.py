#!/usr/bin/env python3
"""Reject generated environments, caches, and obvious credentials from the release tree."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DIRS = {".venv", "venv", "__pycache__", ".pytest_cache"}
FORBIDDEN_FILES = {".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "private_key"}
TOKEN = re.compile(
    rb"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"
)
errors: list[str] = []

for path in ROOT.rglob("*"):
    relative = path.relative_to(ROOT)
    if path.resolve() == Path(__file__).resolve():
        continue
    if path.is_dir() and path.name in FORBIDDEN_DIRS:
        errors.append(f"generated directory in release tree: {relative}")
        continue
    if not path.is_file() or any(part in FORBIDDEN_DIRS for part in relative.parts):
        continue
    if path.name in FORBIDDEN_FILES or path.suffix.lower() in {".p12", ".pfx"}:
        errors.append(f"credential-like file in release tree: {relative}")
        continue
    if path.stat().st_size <= 1_000_000:
        prefix = path.read_bytes()[:8192]
        if b"-----BEGIN " in prefix and b"PRIVATE KEY-----" in prefix:
            errors.append(f"private key material in release tree: {relative}")
        if TOKEN.search(prefix):
            errors.append(f"credential-like token in release tree: {relative}")

if errors:
    raise SystemExit("\n".join(errors))
print("Release tree contains no generated environments, caches, or obvious credentials.")
