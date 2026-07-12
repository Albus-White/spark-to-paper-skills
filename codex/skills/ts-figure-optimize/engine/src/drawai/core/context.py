from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .artifacts import ArtifactStore


@dataclass(frozen=True)
class RunContext:
    config: Mapping[str, Any]
    artifacts: ArtifactStore
    providers: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
