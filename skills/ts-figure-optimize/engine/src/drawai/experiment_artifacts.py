from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

RUN_METADATA_SCHEMA = "drawai.experiment_run_metadata.v1"
RUN_LAYOUT = "runs/YYYYMMDD/vNNN_HHMMSS_slug"
TIMESTAMPED_RUN_LAYOUT = "runs/YYYYMMDD/HHMMSS_slug"
_VERSIONED_RUN_RE = re.compile(r"^v(?P<version>\d{3})_\d{6}_[A-Za-z0-9][A-Za-z0-9_-]*$")


def safe_run_slug(value: str | None, *, default: str = "run") -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return slug or default


def next_versioned_run_dir(
    run_root: str | Path,
    *,
    slug: str,
    now: datetime | None = None,
) -> Path:
    timestamp = now or datetime.now()
    date_text = timestamp.strftime("%Y%m%d")
    time_text = timestamp.strftime("%H%M%S")
    date_dir = Path(run_root).expanduser().resolve(strict=False) / date_text
    version = _next_version(date_dir)
    return date_dir / f"v{version:03d}_{time_text}_{safe_run_slug(slug)}"


def next_timestamped_run_dir(
    run_root: str | Path,
    *,
    slug: str,
    now: datetime | None = None,
) -> Path:
    timestamp = now or datetime.now()
    date_text = timestamp.strftime("%Y%m%d")
    time_text = timestamp.strftime("%H%M%S")
    date_dir = Path(run_root).expanduser().resolve(strict=False) / date_text
    base_name = f"{time_text}_{safe_run_slug(slug)}"
    candidate = date_dir / base_name
    suffix = 2
    while candidate.exists():
        candidate = date_dir / f"{base_name}_{suffix:02d}"
        suffix += 1
    return candidate


def run_metadata_payload(
    *,
    run_dir: str | Path,
    run_root: str | Path,
    manifest_path: str | Path,
    base_config_path: str | Path,
    script_path: str | Path,
    args: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    timestamp = now or datetime.now()
    run_dir_path = Path(run_dir).expanduser().resolve(strict=False)
    run_root_path = Path(run_root).expanduser().resolve(strict=False)
    return {
        "schema": RUN_METADATA_SCHEMA,
        "layout": RUN_LAYOUT,
        "created_at": timestamp.isoformat(timespec="seconds"),
        "date": timestamp.strftime("%Y%m%d"),
        "run_id": run_dir_path.name,
        "run_dir": str(run_dir_path),
        "run_root": str(run_root_path),
        "manifest": str(Path(manifest_path).expanduser().resolve(strict=False)),
        "base_config": str(Path(base_config_path).expanduser().resolve(strict=False)),
        "script": str(Path(script_path).expanduser().resolve(strict=False)),
        "args": dict(args),
    }


def write_run_metadata(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _next_version(date_dir: Path) -> int:
    if not date_dir.exists():
        return 1
    versions: list[int] = []
    for child in date_dir.iterdir():
        if not child.is_dir():
            continue
        match = _VERSIONED_RUN_RE.fullmatch(child.name)
        if match:
            versions.append(int(match.group("version")))
    return max(versions, default=0) + 1
