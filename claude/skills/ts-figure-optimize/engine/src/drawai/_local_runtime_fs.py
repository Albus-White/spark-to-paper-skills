from __future__ import annotations

import subprocess
from pathlib import Path


def create_windows_junction(link_path: Path, target_path: Path) -> bool:
    try:
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 or link_path.exists()
