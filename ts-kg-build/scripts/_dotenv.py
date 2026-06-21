"""Auto-load a UNIFIED .env into os.environ (zero dependencies).

Imported for its side effect by every skill script that reads API keys. It walks UP from this file to
the nearest `.env` (so one `.env` at the spark-to-paper-skills root serves all skills) and loads
KEY=VALUE lines. Uses os.environ.setdefault, so a real exported env var ALWAYS wins over the file and
the file is never required. Comments (#) and blank lines are ignored; surrounding quotes are stripped.

Keys used across the suite (see .env.example at the repo root):
  OPENAI_API_KEY / VISION_MODEL / VISION_BASE_URL   — ts-figure-optimize GPT text/vision (else ~/.codex/auth.json)
  TS_EMBED_API_KEY / TS_EMBED_BASE_URL / TS_EMBED_MODEL  — ts-kg-build, ts-idea2story
  TS_FIG_API_KEY / TS_FIG_BASE_URL / TS_FIG_MODEL        — ts-paper-figure
"""
from __future__ import annotations

import os
from pathlib import Path


def load_unified_env() -> str | None:
    for d in Path(__file__).resolve().parents:
        f = d / ".env"
        if f.is_file():
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, _, v = s.partition("=")
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k:
                        os.environ.setdefault(k, v)
            except Exception:  # noqa: BLE001 - never let env loading break a tool
                return None
            return str(f)
    return None


LOADED = load_unified_env()
