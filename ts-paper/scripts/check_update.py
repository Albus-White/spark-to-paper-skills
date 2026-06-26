#!/usr/bin/env python3
"""Soft update check for spark-to-paper-skills.

Queries the GitHub Releases API for the latest published release,
compares it against the locally installed version, and prints a
one-line notification when a newer version exists.

- Runs silently on success (no output if up-to-date).
- Caches the result for 24 hours so repeated invocations are free.
- Never raises / never blocks the calling skill on failure.
"""

import json, os, sys, time, tempfile, urllib.request

REPO = "Albus-White/spark-to-paper-skills"
FALLBACK_VERSION = "1.0.1"
CACHE_TTL = 86400  # 24 h

_CACHE_DIR = os.path.join(tempfile.gettempdir(), "spark-to-paper-skills")
CACHE_FILE = os.path.join(_CACHE_DIR, "update-check.json")


def _installed_version():
    """Read VERSION from the repo / skill root (walk up from this script)."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        v = os.path.join(d, "VERSION")
        if os.path.isfile(v):
            return open(v).read().strip()
        d = os.path.dirname(d)
    return FALLBACK_VERSION


def _parse(v):
    parts = v.lstrip("v").split(".")
    return tuple(int(x) for x in parts if x.isdigit())


def _read_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(data):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)


def _fetch_latest():
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "spark-to-paper-skills-update-check",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read())
    return data.get("tag_name", "").lstrip("v")


def _notify(installed, latest):
    print(
        f"\n  spark-to-paper-skills v{latest} is available "
        f"(installed: v{installed}).\n"
        f"  Update:  git -C <skills-dir>/spark-to-paper-skills pull && "
        f"cp -r ts-* ~/.claude/skills/\n"
    )


def check_update():
    installed = _installed_version()

    cache = _read_cache()
    if cache and time.time() - cache.get("checked", 0) < CACHE_TTL:
        if cache.get("update_available"):
            _notify(installed, cache["latest"])
        return

    try:
        latest = _fetch_latest()
    except Exception:
        return  # network down — stay silent

    update_available = _parse(latest) > _parse(installed)
    _write_cache({
        "update_available": update_available,
        "installed": installed,
        "latest": latest,
        "checked": time.time(),
    })

    if update_available:
        _notify(installed, latest)


if __name__ == "__main__":
    check_update()
