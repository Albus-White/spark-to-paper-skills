#!/usr/bin/env python3
"""Create a deterministic, content-addressed snapshot of a Paper Wiki workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_identity(root: Path) -> dict[str, Any] | None:
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout.strip()
        head = subprocess.run(
            ["git", "-C", top, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", top, "status", "--porcelain", "--", str(root)],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return {"root": top, "head": head, "dirty": bool(status.strip())}


def included_files(root: Path) -> list[Path]:
    files = [root / "WIKI.md"]
    research = root / "research.md"
    if research.is_file():
        files.append(research)
    sentinel = root / ".paper-wiki"
    if sentinel.is_file():
        files.append(sentinel)
    wiki = root / "wiki"
    if wiki.is_dir():
        files.extend(path for path in wiki.rglob("*.md") if path.is_file() and not path.is_symlink())
    return sorted(set(files), key=lambda path: path.relative_to(root).as_posix())


def build_snapshot(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not (root / "WIKI.md").is_file():
        raise ValueError("Paper Wiki root is missing WIKI.md")
    sentinel = root / ".paper-wiki"
    if not sentinel.exists():
        raise ValueError("Paper Wiki root is missing the .paper-wiki sentinel")
    if not sentinel.is_file() and not sentinel.is_dir():
        raise ValueError(".paper-wiki must be a file or directory")

    records = []
    counts = {"papers": 0, "concepts": 0, "gaps": 0, "other": 0}
    for path in included_files(root):
        relative = path.relative_to(root).as_posix()
        if relative.startswith("wiki/papers/"):
            category = "papers"
        elif relative.startswith("wiki/concepts/"):
            category = "concepts"
        elif relative.startswith("wiki/gaps/"):
            category = "gaps"
        else:
            category = "other"
        counts[category] += 1
        records.append({
            "path": relative,
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "category": category,
        })

    identity_payload = [{"path": item["path"], "sha256": item["sha256"]} for item in records]
    snapshot_hash = hashlib.sha256(
        json.dumps(identity_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "1.0.0",
        "artifact_type": "paper_wiki_snapshot",
        "wiki_root": str(root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_sha256": snapshot_hash,
        "counts": counts,
        "files": records,
        "git": git_identity(root),
        "excluded": ["raw/**", "PDF/media bytes", "runtime ownership markers", "credentials"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wiki-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        snapshot = build_snapshot(Path(args.wiki_root))
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "output": str(output.resolve()), "snapshot_sha256": snapshot["snapshot_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

