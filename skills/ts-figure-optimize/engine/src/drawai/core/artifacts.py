from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    path: Path
    schema: str | None = None
    media_type: str | None = None
    sha256: str = ""
    size_bytes: int = 0

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def to_manifest(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload


class ArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._artifacts: dict[str, ArtifactRef] = {}

    def resolve(self, relative_path: str | Path) -> Path:
        path = Path(relative_path)
        candidate = path if path.is_absolute() else self.root / path
        resolved = candidate.expanduser().resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"artifact path is outside artifact root: {relative_path}") from exc
        return resolved

    def write_json(
        self,
        artifact_id: str,
        relative_path: str | Path,
        payload: Any,
        *,
        schema: str | None = None,
    ) -> ArtifactRef:
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self.register(artifact_id, relative_path, schema=schema, media_type="application/json")

    def register(
        self,
        artifact_id: str,
        relative_path: str | Path,
        *,
        schema: str | None = None,
        media_type: str | None = None,
    ) -> ArtifactRef:
        path = self.resolve(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"artifact does not exist: {path}")
        ref = ArtifactRef(
            artifact_id=artifact_id,
            path=path,
            schema=schema,
            media_type=media_type,
            sha256=_sha256_file(path),
            size_bytes=path.stat().st_size,
        )
        self._artifacts[artifact_id] = ref
        return ref

    def get(self, artifact_id: str) -> ArtifactRef:
        return self._artifacts[artifact_id]

    def manifest(self) -> dict[str, Any]:
        return {
            "schema": "drawai.artifact_manifest.v1",
            "root": str(self.root),
            "artifacts": {
                artifact_id: ref.to_manifest()
                for artifact_id, ref in sorted(self._artifacts.items())
            },
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
