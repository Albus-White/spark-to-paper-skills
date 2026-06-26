"""_kg_bootstrap.py — make sure the knowledge-graph dir is extracted before a script reads it.

kg_recall.py / novelty_check.py read plain files from <kg_dir> (nodes_pattern.json,
nodes_paper.json, edges.json, ...). In the repo those files live inside the committed
archive `kg/kg_ai.rar` (tracked via Git LFS); the extracted `kg/kg_ai/` directory is
gitignored, so a fresh checkout has only the archive. `ensure_kg_extracted()` unpacks it
on first use so callers don't have to unrar by hand. It is idempotent: if the kg is
already extracted it is a no-op (the common case on a warm machine).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# A file that kg_recall.py needs; its presence means the kg is already extracted.
SENTINEL = "nodes_pattern.json"
# Git-LFS pointer files start with this line instead of the real archive bytes.
LFS_MAGIC = b"version https://git-lfs.github.com/spec/v1"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _find_rar(kg_dir: Path) -> Path | None:
    """The archive is the sibling of <kg_dir> named <kg_dir>.rar (e.g. kg/kg_ai.rar)."""
    candidates = [
        kg_dir.with_suffix(".rar"),
        kg_dir.parent / (kg_dir.name + ".rar"),
        kg_dir.parent / "kg_ai.rar",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _is_lfs_pointer(rar: Path) -> bool:
    """True if <rar> is an unresolved Git-LFS pointer rather than the real archive."""
    return rar.stat().st_size < 1000 and rar.read_bytes()[:64].startswith(LFS_MAGIC)


def _try_lfs_pull(rar: Path) -> bool:
    """Best-effort `git lfs pull` to materialize <rar>. Returns True if it is now real."""
    if not shutil.which("git"):
        return False
    try:
        root = subprocess.run(
            ["git", "-C", str(rar.parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True).stdout.strip()
        rel = rar.resolve().relative_to(Path(root).resolve()).as_posix()
        _log(f"[kg-bootstrap] {rar.name} is a Git-LFS pointer; fetching via `git lfs pull`...")
        subprocess.run(["git", "-C", root, "lfs", "pull", f"--include={rel}"], check=True)
    except (subprocess.CalledProcessError, ValueError, OSError) as e:
        _log(f"[kg-bootstrap] git lfs pull failed: {e}")
        return False
    return not _is_lfs_pointer(rar)


def _extract(rar: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if shutil.which("unrar"):
        cmd = ["unrar", "x", "-o+", "-idq", str(rar), str(dest) + "/"]
    elif shutil.which("bsdtar"):
        cmd = ["bsdtar", "-xf", str(rar), "-C", str(dest)]
    elif shutil.which("7z"):
        cmd = ["7z", "x", "-y", f"-o{dest}", str(rar)]
    else:
        raise RuntimeError(
            "no rar extractor available — install one of: unrar, bsdtar (libarchive), or 7z")
    subprocess.run(cmd, check=True)


def ensure_kg_extracted(kg_dir) -> Path:
    """Extract kg/kg_ai.rar into place if <kg_dir> is not already populated.

    Returns the (now-ready) kg_dir Path. Raises a clear error if the archive is an
    unresolved Git-LFS pointer or extraction does not produce the expected files.
    """
    kg_dir = Path(kg_dir)
    if (kg_dir / SENTINEL).exists():
        return kg_dir  # already extracted — no-op

    rar = _find_rar(kg_dir)
    if rar is None:
        # Nothing to extract; let the caller fail with its own file-not-found message.
        return kg_dir

    # If the archive is still a Git-LFS pointer, fetch the real bytes first.
    if _is_lfs_pointer(rar) and not _try_lfs_pull(rar):
        raise RuntimeError(
            f"{rar} is an unresolved Git LFS pointer and could not be fetched automatically "
            f"(is git-lfs installed and the remote reachable?). Run "
            f"`git lfs pull --include={rar.as_posix()}` (or drop the real kg_ai.rar in place), "
            f"then retry.")

    _log(f"[kg-bootstrap] extracting {rar.name} -> {kg_dir.parent}/ ...")
    _extract(rar, kg_dir.parent)
    if not (kg_dir / SENTINEL).exists():
        # Fallback: archive may hold the files at top level (no kg_ai/ wrapper).
        _extract(rar, kg_dir)
    if not (kg_dir / SENTINEL).exists():
        raise RuntimeError(
            f"extracted {rar} but {kg_dir / SENTINEL} is still missing — check the archive layout")
    _log(f"[kg-bootstrap] kg ready at {kg_dir}")
    return kg_dir
