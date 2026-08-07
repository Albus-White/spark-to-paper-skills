#!/usr/bin/env python3
"""setup_paperbanana.py — provision the OFFICIAL PaperBanana (dwzhu-pku/PaperBanana) under this skill.

We do not reimplement PaperBanana: its own `skill/run.py` (Retriever → Planner → Stylist → Visualizer →
Critic) is the PNG stage. This script clones/updates it into `engine/PaperBanana/` (gitignored), installs
its requirements, and reports whether a key is configured.

  python3 setup_paperbanana.py                 # clone or fast-forward, install deps
  python3 setup_paperbanana.py --check-only    # doctor: is it runnable right now?
  python3 setup_paperbanana.py --ref <sha>     # pin to a commit
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = "https://github.com/dwzhu-pku/PaperBanana.git"
ENGINE = Path(__file__).resolve().parents[1] / "engine" / "PaperBanana"
KEYS = ("OPENROUTER_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def sh(cmd, **kw):
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def doctor() -> dict:
    run = ENGINE / "skill" / "run.py"
    cfg = ENGINE / "configs" / "model_config.yaml"
    keys = [k for k in KEYS if os.environ.get(k)]
    if not keys and cfg.is_file():
        txt = cfg.read_text(encoding="utf-8", errors="ignore")
        keys = [f"{k}(model_config.yaml)" for k in ("google", "openrouter", "openai", "anthropic")
                if f'{k}_api_key: ""' not in txt and f"{k}_api_key" in txt]
    head = sh(["git", "-C", str(ENGINE), "rev-parse", "--short", "HEAD"]).stdout.strip() if (ENGINE / ".git").is_dir() else ""
    return {
        "engine": str(ENGINE),
        "cloned": run.is_file(),
        "commit": head,
        "config_present": cfg.is_file(),
        "keys_configured": keys,
        "ready": run.is_file() and bool(keys),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--ref", help="commit/tag to check out (default: upstream default branch)")
    ap.add_argument("--no-deps", action="store_true", help="skip the requirements install")
    a = ap.parse_args()

    if a.check_only:
        d = doctor()
        print(json.dumps(d, indent=2))
        return 0 if d["ready"] else 1

    if not shutil.which("git"):
        print("git is required", file=sys.stderr)
        return 2
    ENGINE.parent.mkdir(parents=True, exist_ok=True)
    if (ENGINE / ".git").is_dir():
        print(f"updating {ENGINE}")
        sh(["git", "-C", str(ENGINE), "fetch", "--depth", "1", "origin"])
        r = sh(["git", "-C", str(ENGINE), "checkout", a.ref] if a.ref else
               ["git", "-C", str(ENGINE), "reset", "--hard", "origin/HEAD"])
    else:
        print(f"cloning {REPO} -> {ENGINE}")
        r = sh(["git", "clone", "--depth", "1", REPO, str(ENGINE)])
        if r.returncode == 0 and a.ref:
            sh(["git", "-C", str(ENGINE), "fetch", "--depth", "1", "origin", a.ref])
            r = sh(["git", "-C", str(ENGINE), "checkout", a.ref])
    if r.returncode != 0:
        print(r.stderr.strip() or r.stdout.strip(), file=sys.stderr)
        return 1

    req = ENGINE / "requirements.txt"
    if not a.no_deps and req.is_file():
        pip = ([shutil.which("uv"), "pip"] if shutil.which("uv") else [sys.executable, "-m", "pip"])
        print(f"installing requirements with {' '.join(pip)}")
        p = subprocess.run([*pip, "install", "-r", str(req)], text=True)
        if p.returncode != 0:
            print("dependency install failed — install requirements.txt yourself, then re-run "
                  "--check-only", file=sys.stderr)

    cfg = ENGINE / "configs" / "model_config.yaml"
    tmpl = ENGINE / "configs" / "model_config.template.yaml"
    if tmpl.is_file() and not cfg.is_file():
        shutil.copy2(tmpl, cfg)
        print(f"seeded {cfg} from the template — put your key there or export OPENROUTER_API_KEY")

    d = doctor()
    print(json.dumps(d, indent=2))
    if not d["keys_configured"]:
        print("\nNo API key found. Export one (OPENROUTER_API_KEY recommended — it covers both the VLM "
              "agents and image generation) or fill configs/model_config.yaml.", file=sys.stderr)
    return 0 if d["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
