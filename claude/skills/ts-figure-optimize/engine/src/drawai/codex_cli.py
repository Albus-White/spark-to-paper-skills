from __future__ import annotations

import os
import shutil
from pathlib import Path


def codex_executable_candidates(runtime_root: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    if runtime_root is not None:
        roots.append(Path(runtime_root).expanduser().resolve(strict=False))
    env_root = os.environ.get("DRAWAI_LOCAL_RUNTIME_ROOT")
    if env_root:
        roots.append(Path(env_root).expanduser().resolve(strict=False))
    default_root = Path(".local/drawai_runtime").resolve(strict=False)
    roots.append(default_root)

    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        candidates.extend(
            [
                root / ".venv" / "bin" / "codex",
                root / ".venv" / "Scripts" / "codex.exe",
                root / ".venv" / "Lib" / "site-packages" / "codex_cli_bin" / "bin" / "codex.exe",
                root / ".venv" / "Lib" / "site-packages" / "codex_cli_bin" / "bin" / "codex",
            ]
        )
        site_packages_root = root / ".venv" / "lib"
        candidates.extend(site_packages_root.glob("python*/site-packages/codex_cli_bin/bin/codex"))
        candidates.extend(site_packages_root.glob("python*/site-packages/codex_cli_bin/bin/codex.exe"))

    return candidates


def resolve_codex_executable(runtime_root: Path | None = None) -> Path | None:
    for path in codex_executable_candidates(runtime_root):
        if path.is_file():
            return path
    path_candidate = shutil.which("codex")
    if path_candidate:
        return Path(path_candidate).expanduser().resolve(strict=False)
    try:
        import codex_cli_bin
    except ImportError:
        return None
    package_candidate = Path(codex_cli_bin.__file__).resolve(strict=True).parent / "bin" / "codex"
    if package_candidate.is_file():
        return package_candidate
    return None
