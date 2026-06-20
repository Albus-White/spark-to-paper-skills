from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .artifacts import ArtifactRef

if TYPE_CHECKING:
    from .context import RunContext


StageCallable = Callable[["RunContext"], "StageResult"]
StageValidator = Callable[["RunContext", "StageResult"], None]


@dataclass(frozen=True)
class ProviderRef:
    name: str
    protocol: str
    required: bool = True


@dataclass(frozen=True)
class StageResult:
    stage_id: str
    status: str
    artifacts: dict[str, ArtifactRef] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        stage_id: str,
        *,
        artifacts: dict[str, ArtifactRef] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "StageResult":
        return cls(
            stage_id=stage_id,
            status="ok",
            artifacts=dict(artifacts or {}),
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    run: StageCallable
    depends_on: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    providers: tuple[ProviderRef, ...] = ()
    validate: StageValidator | None = None
