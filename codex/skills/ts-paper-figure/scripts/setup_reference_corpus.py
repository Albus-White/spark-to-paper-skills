#!/usr/bin/env python3
"""Install official PaperBananaBench into a skill-owned cache, without PaperBanana source coupling."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _dotenv  # noqa: E402,F401  -- load PAPERBANANA_CACHE_ROOT from the unified .env

REPO_ID = "dwzhu/PaperBananaBench"
FILENAME = "PaperBananaBench.zip"
REVISION = "a876264bcd1e826a0320f805f8fb1cd705cf510f"
SIZE = 265_846_711
SHA256 = "a980d23954c0cb47017cdaa8a9029dbea3598791fd269a457482033821927e37"
URL = f"https://huggingface.co/datasets/{REPO_ID}/resolve/{REVISION}/{FILENAME}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_corpus(root: Path) -> tuple[bool, list[str]]:
    issues = []
    for task in ("diagram", "plot"):
        task_root = root / task
        ref = task_root / "ref.json"
        images = task_root / "images"
        if not ref.is_file():
            issues.append(f"missing {task}/ref.json")
        else:
            try:
                payload = json.loads(ref.read_text(encoding="utf-8"))
                if not isinstance(payload, list) or len(payload) < 10:
                    issues.append(f"{task}/ref.json has fewer than 10 examples")
                elif isinstance(payload, list):
                    missing = []
                    for item in payload:
                        if not isinstance(item, dict):
                            continue
                        rel = item.get("path_to_gt_image") or item.get("image")
                        if rel and not (task_root / str(rel)).is_file():
                            missing.append(str(rel))
                    if missing:
                        preview = ", ".join(missing[:3])
                        issues.append(
                            f"{task}/ref.json references {len(missing)} missing images"
                            + (f": {preview}" if preview else "")
                        )
            except (OSError, ValueError) as exc:
                issues.append(f"invalid {task}/ref.json: {exc}")
        if not images.is_dir() or not any(images.iterdir()):
            issues.append(f"missing/empty {task}/images")
    return not issues, issues


def _repair_mojibake_filenames(root: Path) -> list[dict[str, str]]:
    """Repair UTF-8 bytes that the upstream archive stored as CP437-looking names.

    PaperBananaBench currently contains a small number of filenames such as ``ΓÇæ`` where
    ``ref.json`` correctly contains U+2011.  The archive itself already carries the mojibake, so
    normal ZIP extraction cannot fix it.  This reversible byte round-trip repairs those entries
    without guessing arbitrary Unicode names.
    """
    repairs: list[dict[str, str]] = []
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: len(p.parts), reverse=True):
        try:
            repaired_name = path.name.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if repaired_name == path.name:
            continue
        repaired = path.with_name(repaired_name)
        if repaired.exists():
            if repaired.read_bytes() != path.read_bytes():
                raise RuntimeError(f"filename repair collision: {path} -> {repaired}")
            path.unlink()
        else:
            path.rename(repaired)
        repairs.append({"from": str(path.relative_to(root)), "to": str(repaired.relative_to(root))})
    return repairs


def _download_hf_xet(download_dir: Path) -> Path | None:
    """Prefer huggingface_hub/hf_xet; use uvx so the skill need not own a permanent dependency."""
    try:
        from huggingface_hub import hf_hub_download
        return Path(hf_hub_download(REPO_ID, FILENAME, repo_type="dataset", revision=REVISION,
                                    local_dir=str(download_dir)))
    except ImportError:
        pass
    uvx = shutil.which("uvx")
    if not uvx:
        return None
    command = [uvx, "--from", "huggingface_hub[hf_xet]", "hf", "download", REPO_ID, FILENAME,
               "--repo-type", "dataset", "--revision", REVISION, "--local-dir", str(download_dir)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return None
    candidate = download_dir / FILENAME
    return candidate if result.returncode == 0 and candidate.is_file() else None


def _download_resume(destination: Path, retries: int = 12) -> Path:
    if not 1 <= retries <= 12:
        raise ValueError("reference download retries must be between 1 and 12")
    part = destination.with_suffix(destination.suffix + ".part")
    deadline = time.monotonic() + 7_200
    for attempt in range(1, retries + 1):
        if time.monotonic() >= deadline:
            break
        offset = part.stat().st_size if part.is_file() else 0
        request = urllib.request.Request(URL, headers={"Range": f"bytes={offset}-"} if offset else {})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                # Some mirrors ignore Range and return 200/full content. Never append that response
                # to a partial archive: restart it instead, otherwise a plausible-size corrupt ZIP
                # survives until the final checksum and wastes every retry.
                resumed = offset > 0 and response.status == 206 and str(response.headers.get("Content-Range", "")).startswith(f"bytes {offset}-")
                mode = "ab" if resumed else "wb"
                with part.open(mode) as out:
                    while out.tell() < SIZE:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("reference download wall-clock budget exhausted")
                        chunk = response.read(min(1024 * 1024, SIZE - out.tell()))
                        if not chunk:
                            break
                        out.write(chunk)
            if part.stat().st_size == SIZE:
                part.replace(destination)
                return destination
        except (OSError, urllib.error.URLError, TimeoutError):
            pass
        time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"download incomplete after {retries} attempts: {part.stat().st_size if part.exists() else 0}/{SIZE}")


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError(f"unsafe archive member: {member.filename}")
        bundle.extractall(destination)


def install_archive(archive: Path, cache_root: Path) -> Path:
    staging = cache_root / ".PaperBananaBench.extracting"
    target = cache_root / "PaperBananaBench"
    if staging.exists():
        shutil.rmtree(staging)
    _safe_extract(archive, staging)
    extracted = staging / "PaperBananaBench"
    source = extracted if extracted.is_dir() else staging
    repairs = _repair_mojibake_filenames(source)
    ok, issues = valid_corpus(source)
    if not ok:
        raise RuntimeError("invalid extracted PaperBananaBench: " + "; ".join(issues))
    if target.exists():
        shutil.rmtree(target)
    if source == staging:
        staging.replace(target)
    else:
        extracted.replace(target)
        shutil.rmtree(staging)
    (target / "FILENAME_REPAIRS.json").write_text(
        json.dumps({"schema": "ts.figure.filename_repairs.v1", "repairs": repairs},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", default=os.environ.get("PAPERBANANA_CACHE_ROOT",
                                                               str(Path.home() / ".cache" / "ts-paper-figure")))
    parser.add_argument("--archive", default="", help="use an already-downloaded official ZIP")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    cache_root = Path(os.path.expandvars(args.cache_root)).expanduser().resolve()
    target = cache_root / "PaperBananaBench"
    ok, issues = valid_corpus(target)
    if args.check_only:
        print(json.dumps({"ok": ok, "corpus": str(target), "issues": issues}, ensure_ascii=False))
        return 0 if ok else 1
    if ok:
        print(json.dumps({"ok": True, "corpus": str(target), "status": "already-installed"}))
        return 0

    cache_root.mkdir(parents=True, exist_ok=True)
    downloads = cache_root / "downloads"; downloads.mkdir(parents=True, exist_ok=True)
    archive = Path(args.archive).expanduser().resolve() if args.archive else _download_hf_xet(downloads)
    if archive is None:
        archive = _download_resume(downloads / FILENAME)
    if archive.stat().st_size != SIZE or sha256(archive) != SHA256:
        print(json.dumps({"ok": False, "error": "official archive size/SHA-256 mismatch",
                          "archive": str(archive)}))
        return 2
    target = install_archive(archive, cache_root)
    manifest = {"schema": "ts.figure.reference_corpus.v1", "repo_id": REPO_ID,
                "revision": REVISION, "archive_sha256": SHA256, "corpus": str(target)}
    (target / "CORPUS_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "status": "installed", **manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
