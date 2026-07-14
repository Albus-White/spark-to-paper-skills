"""Auto-load a UNIFIED .env into os.environ (zero dependencies).

Imported for its side effect by skill scripts that read API keys. It first walks up from the current
workspace, then from this file, to find the nearest `.env`. Uses os.environ.setdefault, so a real
exported variable always wins and the file is never required. Comments and blank lines are ignored;
surrounding quotes are stripped.

Keys used across the suite (see .env.example at the repo root):
  OPENAI_API_KEY / VISION_MODEL / VISION_BASE_URL   — ts-figure-optimize GPT text/vision (else ~/.codex/auth.json)
  TS_EMBED_API_KEY / TS_EMBED_BASE_URL / TS_EMBED_MODEL  — optional semantic retrieval helpers
  PAPERBANANA_CACHE_ROOT                                  — optional reference cache
  GOOGLE_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY / OPENROUTER_API_KEY — PaperBanana providers
  DRAWAI_REMOTE_*                                          — external SAM3/PaddleOCR/RMBG service
"""
from __future__ import annotations

import os
from pathlib import Path


def load_unified_env() -> str | None:
    starts = [Path.cwd().resolve(), *Path(__file__).resolve().parents]
    directories = []
    seen = set()
    for start in starts:
        for directory in (start, *start.parents):
            if directory not in seen:
                directories.append(directory)
                seen.add(directory)
    for d in directories:
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
