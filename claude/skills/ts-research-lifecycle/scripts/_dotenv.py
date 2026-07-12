"""Load the nearest suite-level .env without overriding exported variables."""
from __future__ import annotations

import os
from pathlib import Path


def load_unified_env() -> str | None:
    for directory in Path(__file__).resolve().parents:
        path = directory / ".env"
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                value = line.strip()
                if not value or value.startswith("#") or "=" not in value:
                    continue
                key, _, raw = value.partition("=")
                key = key.strip()
                raw = raw.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, raw)
        except OSError:
            return None
        return str(path)
    return None


LOADED = load_unified_env()
