#!/usr/bin/env python3
"""Initialize the ./paper/ directory as an independent Git repo for Overleaf.

This helper supports the "Direct Overleaf Git Workflow":

  1. Read ./paper_config.yaml (relative to the current working directory).
  2. Verify an AI draft is available (./draft_overleaf.zip, files under
     ./input/draft/, or existing files under ./paper/).
  3. Resolve the Overleaf Git URL: ./paper_config.yaml (overleaf.git_url) first,
     then fall back to ./.env (OVERLEAF_GIT_URL).
  4. Create ./paper/, extract the zip and/or copy draft files into it.
  5. Initialize Git inside ./paper/ (an INDEPENDENT repo).
  6. Add the Overleaf remote (named from overleaf.remote_name).
  7. Commit the original draft as "Initial import of AI draft".
  8. Push only when called with --push.

Non-interactive authentication:
  - The token is read from ./.env (OVERLEAF_TOKEN). It is NEVER stored in
    paper_config.yaml, NEVER written into the git remote URL, and NEVER printed.
  - When pushing, if a token is present it is supplied to git through a
    TEMPORARY askpass helper (GIT_ASKPASS). The token is passed to that helper
    via an environment variable, not written into the helper file, and the
    temporary helper is deleted afterwards.
  - Without a token, push falls back to git's normal credential helper / SSH /
    interactive prompt.

Rules:
  - Uses ONLY relative paths from the current working directory.
  - NEVER runs git commands in the parent AutoPaperFactory repository.
  - NEVER commits/pushes data, code, workspace, outputs, or skill files
    (only the contents of ./paper/ are ever touched by git here).

Usage:
    python scripts/init_paper_overleaf.py            # prepare + commit ./paper/
    python scripts/init_paper_overleaf.py --push     # also push to Overleaf
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

# All paths are relative to the current working directory (the project root).
CONFIG_PATH = "paper_config.yaml"
ENV_PATH = ".env"
ZIP_PATH = "draft_overleaf.zip"
DRAFT_DIR = os.path.join("input", "draft")
PAPER_DIR_DEFAULT = "paper"
DRAFT_PLACEHOLDER = "PLACE_DRAFT_HERE.md"
COMMIT_MESSAGE = "Initial import of AI draft"

# Env var used to hand the token to the temporary askpass helper. The token is
# never written into the helper file itself, only passed through the process env.
ASKPASS_ENV_VAR = "OAF_OVERLEAF_PW"

# Temporary askpass helper. Reads the password from the environment (set only for
# the git child process); echoes "git" for username prompts. It never sees or
# writes the token to disk.
ASKPASS_SCRIPT = (
    "#!/usr/bin/env python3\n"
    "import os, sys\n"
    "prompt = sys.argv[1] if len(sys.argv) > 1 else ''\n"
    "if 'username' in prompt.lower():\n"
    "    sys.stdout.write('git')\n"
    "else:\n"
    f"    sys.stdout.write(os.environ.get('{ASKPASS_ENV_VAR}', ''))\n"
)

ERR_MISSING_DRAFT = (
    "Missing AI draft. Put ./draft_overleaf.zip in the project root or place "
    "draft files under ./input/draft/."
)
ERR_MISSING_URL = (
    "Missing Overleaf Git URL. Create a blank Overleaf project, copy its Git "
    "URL, and set overleaf.git_url in ./paper_config.yaml (or set "
    "OVERLEAF_GIT_URL in ./.env)."
)


# --------------------------------------------------------------------------- #
# Config / env loading                                                        #
# --------------------------------------------------------------------------- #
def load_config(path: str) -> dict:
    """Load paper_config.yaml. Use PyYAML if available, else a tiny fallback
    parser that extracts just the keys we need from the `overleaf:` block."""
    if not os.path.isfile(path):
        return {}
    try:
        import yaml  # type: ignore

        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _fallback_parse(path)


def _fallback_parse(path: str) -> dict:
    """Minimal parser for the overleaf block (no PyYAML available)."""
    overleaf: dict = {}
    in_overleaf = False
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            stripped = line.strip()
            if indent == 0:
                in_overleaf = stripped.rstrip().startswith("overleaf:")
                continue
            if in_overleaf and ":" in stripped:
                key, _, val = stripped.partition(":")
                overleaf[key.strip()] = _coerce(val.strip())
    return {"overleaf": overleaf}


def _coerce(val: str):
    if val == "" or val.lower() == "null" or val.lower() == "none":
        return None
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    return val.strip().strip('"').strip("'")


def get_overleaf(config: dict) -> dict:
    ov = config.get("overleaf") if isinstance(config, dict) else None
    return ov if isinstance(ov, dict) else {}


def load_env(path: str) -> dict:
    """Parse a simple KEY=VALUE .env file. Returns {} if absent.

    Values are NOT exported to the global process environment; the token is kept
    local and only passed to the git child process when pushing.
    """
    env: dict = {}
    if not os.path.isfile(path):
        return env
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.lower().startswith("export "):
                line = line[len("export "):].strip()
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                env[key] = val
    return env


# --------------------------------------------------------------------------- #
# Input checks                                                                #
# --------------------------------------------------------------------------- #
def draft_files_in_dir(directory: str) -> list[str]:
    """Non-placeholder files under a directory (recursively)."""
    found: list[str] = []
    if not os.path.isdir(directory):
        return found
    for root, _dirs, files in os.walk(directory):
        for name in files:
            if name == DRAFT_PLACEHOLDER or name == ".gitkeep":
                continue
            found.append(os.path.join(root, name))
    return found


def paper_has_content(paper_dir: str) -> bool:
    for entry in draft_files_in_dir(paper_dir):
        base = os.path.basename(entry)
        if base not in (".gitkeep", "README.md"):
            return True
    return False


def has_draft_input(paper_dir: str) -> bool:
    return (
        os.path.isfile(ZIP_PATH)
        or bool(draft_files_in_dir(DRAFT_DIR))
        or paper_has_content(paper_dir)
    )


# --------------------------------------------------------------------------- #
# Git helpers (ONLY ever run inside paper_dir)                                 #
# --------------------------------------------------------------------------- #
def git(
    paper_dir: str, *args: str, check: bool = True, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=paper_dir,
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


# --------------------------------------------------------------------------- #
# Steps                                                                        #
# --------------------------------------------------------------------------- #
def extract_zip_into_paper(paper_dir: str) -> None:
    if not os.path.isfile(ZIP_PATH):
        return
    print(f"Extracting {ZIP_PATH} -> {paper_dir}/")
    with zipfile.ZipFile(ZIP_PATH) as zf:
        zf.extractall(paper_dir)


def copy_draft_dir_into_paper(paper_dir: str) -> None:
    files = draft_files_in_dir(DRAFT_DIR)
    if not files:
        return
    print(f"Copying draft files from {DRAFT_DIR}/ -> {paper_dir}/")
    for src in files:
        rel = os.path.relpath(src, DRAFT_DIR)
        dst = os.path.join(paper_dir, rel)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copy2(src, dst)


def ensure_git_repo(paper_dir: str) -> None:
    if os.path.isdir(os.path.join(paper_dir, ".git")):
        print(f"{paper_dir}/ is already a Git repository.")
        return
    print(f"Initializing independent Git repository in {paper_dir}/")
    git(paper_dir, "init")
    # Prefer a 'main' branch for a fresh repo; ignore if unsupported.
    git(paper_dir, "branch", "-M", "main", check=False)


def configure_remote(paper_dir: str, remote_name: str, git_url: str) -> None:
    # NOTE: git_url must NOT contain a token; the token is supplied at push time
    # via a temporary askpass helper, never written into the remote URL.
    existing = git(paper_dir, "remote", check=False)
    remotes = existing.stdout.split() if existing.returncode == 0 else []
    if remote_name in remotes:
        print(f"Updating remote '{remote_name}'")
        git(paper_dir, "remote", "set-url", remote_name, git_url)
    else:
        print(f"Adding remote '{remote_name}'")
        git(paper_dir, "remote", "add", remote_name, git_url)


def commit_initial(paper_dir: str) -> bool:
    git(paper_dir, "add", "-A")
    status = git(paper_dir, "status", "--porcelain")
    if not status.stdout.strip():
        print("No changes to commit in paper/.")
        return False
    print(f'Committing: "{COMMIT_MESSAGE}"')
    git(paper_dir, "commit", "-m", COMMIT_MESSAGE)
    return True


def _push_env_with_token(token: str, tmpdir: str) -> dict:
    """Build a child-process env that authenticates non-interactively via a
    temporary askpass helper. The token is passed through the env only."""
    askpass = os.path.join(tmpdir, "askpass.py")
    with open(askpass, "w", encoding="utf-8") as fh:
        fh.write(ASKPASS_SCRIPT)
    os.chmod(askpass, 0o700)
    env = os.environ.copy()
    env["GIT_ASKPASS"] = askpass
    env["GIT_TERMINAL_PROMPT"] = "0"  # never block on an interactive prompt
    env[ASKPASS_ENV_VAR] = token
    return env


def push(paper_dir: str, remote_name: str, token: str | None) -> None:
    branch = git(paper_dir, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    branch_name = branch.stdout.strip() or "main"

    tmpdir = None
    env = None
    try:
        if token:
            print(f"Pushing {paper_dir}/ to '{remote_name}' ({branch_name}) "
                  "using OVERLEAF_TOKEN from .env ...")
            tmpdir = tempfile.mkdtemp(prefix="oaf_askpass_")
            env = _push_env_with_token(token, tmpdir)
        else:
            print(f"Pushing {paper_dir}/ to '{remote_name}' ({branch_name}) "
                  "(no token in .env; using git credential helper / SSH) ...")
        result = git(
            paper_dir, "push", "-u", remote_name, branch_name, check=False, env=env
        )
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        print(
            "Push failed. Check the Overleaf Git URL and your credentials. Set "
            "OVERLEAF_TOKEN in ./.env for non-interactive auth, or use a Git "
            "credential helper / SSH. Never put tokens in prompts, the remote "
            "URL, or paper_config.yaml."
        )
        sys.exit(1)
    print("Push complete.")


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #
def main(argv: list[str]) -> int:
    do_push = "--push" in argv[1:]

    config = load_config(CONFIG_PATH)
    overleaf = get_overleaf(config)
    env = load_env(ENV_PATH)

    paper_dir = overleaf.get("paper_dir") or PAPER_DIR_DEFAULT
    remote_name = overleaf.get("remote_name") or "overleaf"
    # Git URL: paper_config.yaml first, then .env fallback.
    git_url = overleaf.get("git_url") or env.get("OVERLEAF_GIT_URL")
    # Token: from .env only. Never printed, never stored in config or remote URL.
    token = env.get("OVERLEAF_TOKEN")

    # Input check 1: AI draft present?
    if not has_draft_input(paper_dir):
        print(ERR_MISSING_DRAFT)
        return 1

    # Input check 2: Overleaf Git URL present?
    if not git_url:
        print(ERR_MISSING_URL)
        return 1

    if not git_available():
        print("git is not available on PATH. Install Git and retry.")
        return 1

    # Prepare ./paper/
    os.makedirs(paper_dir, exist_ok=True)
    extract_zip_into_paper(paper_dir)
    copy_draft_dir_into_paper(paper_dir)

    if not paper_has_content(paper_dir):
        print(
            f"Warning: no manuscript files ended up in {paper_dir}/. "
            "Check the zip contents or input/draft/ files."
        )

    # Independent git repo + remote + initial commit
    ensure_git_repo(paper_dir)
    configure_remote(paper_dir, remote_name, git_url)
    committed = commit_initial(paper_dir)

    if do_push:
        push(paper_dir, remote_name, token)
    else:
        if committed:
            print("Prepared and committed ./paper/. Re-run with --push to push to Overleaf.")
        else:
            print("Re-run with --push to push ./paper/ to Overleaf.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
